"""量化回测引擎：指标、策略注册表、撮合与统计。

设计：
  - 策略 = 一个注册过的函数 `fn(bars, ctx) -> list[Signal | None]`，长度与 K 线相同；
    某根 K 线收盘时想开仓就返回 Signal（方向 + 止盈/止损距离），否则返回 None。
  - 引擎负责：同一时刻只持一个仓位、逐根 K 线检查止盈止损、结算盈亏、统计胜率/盈亏比/净值曲线。
  - 新增策略：在本文件里写一个函数并加上 `@register(...)` 即可，前端首页会自动出现新卡片。

K 线 bars 是 dict 列表：{time, open, high, low, close, volume}，time 为 'YYYY-MM-DD HH:MM:SS'。
所有金额的单位是「元」，不含手续费和滑点。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# 品种参数：最小变动价位 / 合约乘数
# ---------------------------------------------------------------------------
INSTRUMENT_CONFIG: dict[str, dict] = {
    "IF": {"tickSize": 0.2, "multiplier": 300},
    "IC": {"tickSize": 0.2, "multiplier": 200},
    "IH": {"tickSize": 0.2, "multiplier": 300},
    "AU": {"tickSize": 0.02, "multiplier": 1000},
    "AG": {"tickSize": 1, "multiplier": 15},
    "CU": {"tickSize": 10, "multiplier": 5},
    "RB": {"tickSize": 1, "multiplier": 10},
    "I": {"tickSize": 0.5, "multiplier": 100},
    "MA": {"tickSize": 1, "multiplier": 10},
    "SA": {"tickSize": 1, "multiplier": 20},
    "FG": {"tickSize": 1, "multiplier": 20},
    "CF": {"tickSize": 5, "multiplier": 5},
    "SR": {"tickSize": 1, "multiplier": 10},
    "TA": {"tickSize": 2, "multiplier": 5},
    "M": {"tickSize": 1, "multiplier": 10},
    "Y": {"tickSize": 2, "multiplier": 10},
    "P": {"tickSize": 2, "multiplier": 10},
    "AP": {"tickSize": 1, "multiplier": 10},
    "LH": {"tickSize": 5, "multiplier": 16},
    "JD": {"tickSize": 1, "multiplier": 10},
    "SC": {"tickSize": 0.1, "multiplier": 1000},
    "FU": {"tickSize": 1, "multiplier": 10},
    "RU": {"tickSize": 5, "multiplier": 10},
    "SP": {"tickSize": 2, "multiplier": 10},
}
DEFAULT_INSTRUMENT = {"tickSize": 1, "multiplier": 10}

INITIAL_CAPITAL = 10000.0
DEFAULT_LOTS = 5


def get_instrument_config(symbol: str) -> dict:
    code = re.sub(r"\d+", "", str(symbol)).upper()
    return INSTRUMENT_CONFIG.get(code, DEFAULT_INSTRUMENT)


# ---------------------------------------------------------------------------
# 指标（同花顺公式的 Python 版本，和旧版前端实现逐行对应）
# ---------------------------------------------------------------------------
def _isnan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def sma(data: list, period: int, weight: int = 1) -> list:
    """同花顺 SMA(X, N, M)：Y = (M*X + (N-M)*Y') / N。遇到 NaN 重置。"""
    out: list = []
    prev = None
    for v in data:
        if _isnan(v):
            out.append(float("nan"))
            prev = None
            continue
        prev = v if prev is None else (weight * v + (period - weight) * prev) / period
        out.append(prev)
    return out


def ema(data: list, period: int) -> list:
    k = 2 / (period + 1)
    out: list = []
    for i, v in enumerate(data):
        out.append(v if i == 0 else (v - out[i - 1]) * k + out[i - 1])
    return out


def ref(data: list, n: int) -> list:
    return [data[i] if i < n else data[i - n] for i in range(len(data))]


def hhv(data: list, period: int) -> list:
    return [
        data[i] if i < period - 1 else max(data[i - period + 1 : i + 1])
        for i in range(len(data))
    ]


def llv(data: list, period: int) -> list:
    return [
        data[i] if i < period - 1 else min(data[i - period + 1 : i + 1])
        for i in range(len(data))
    ]


def ma(data: list, period: int) -> list:
    return [
        data[i] if i < period - 1 else sum(data[i - period + 1 : i + 1]) / period
        for i in range(len(data))
    ]


def rsi(close: list, period: int = 14) -> list:
    """Wilder RSI，数据不足时返回 50。"""
    out = [50.0] * len(close)
    if len(close) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = close[i] - close[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_g, avg_l = gains / period, losses / period
    out[period] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(period + 1, len(close)):
        d = close[i] - close[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0)) / period
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def reversal_indicator(bars: list[dict]) -> tuple[list, list]:
    """「反转信号」指标，返回 (VAR9 绿柱, VAR9L 红柱)。

    VAR9 > 0 表示出现绿柱（做空信号），VAR9L > 0 表示出现红柱（做多信号）。
    """
    high = [b["high"] for b in bars]
    low = [b["low"] for b in bars]
    close = [b["close"] for b in bars]
    n = len(bars)
    close_ref = ref(close, 1)

    def safe_div(a, b):
        return (a / b) * 100 if b != 0 and not _isnan(b) else 0

    # --- 上轨（绿柱）---
    var2 = ref(high, 1)
    t1 = sma([abs(h - v) for h, v in zip(high, var2)], 3, 1)
    t2 = sma([max(v - h, 0) for h, v in zip(high, var2)], 3, 1)
    var3 = [safe_div(a, b) for a, b in zip(t1, t2)]
    var4 = ema(
        [
            var3[i] * 10 if (i > 0 and close[i] / close_ref[i] < 0.7) else var3[i] / 10
            for i in range(n)
        ],
        3,
    )
    var5 = hhv(high, 50)
    var6 = llv(var4, 50)
    var7 = [1 if v > 0 else 0 for v in ma(close, 58)]
    var8 = [
        v / 1000 * var7[i]
        for i, v in enumerate(
            ema(
                [(var4[i] + var6[i] * 2) / 2 if high[i] >= var5[i] else 0 for i in range(n)],
                3,
            )
        )
    ]
    var9 = [min(v, 100) for v in var8]

    # --- 下轨（红柱）---
    var2l = ref(low, 1)
    t1l = sma([abs(l - v) for l, v in zip(low, var2l)], 3, 1)
    t2l = sma([max(l - v, 0) for l, v in zip(low, var2l)], 3, 1)
    var3l = [safe_div(a, b) for a, b in zip(t1l, t2l)]
    var4l = ema(
        [
            var3l[i] * 10 if (i > 0 and close[i] / close_ref[i] > 1.3) else var3l[i] / 10
            for i in range(n)
        ],
        3,
    )
    var5l = llv(low, 50)
    var6l = hhv(var4l, 50)
    var8l = [
        v / 1000 * var7[i]
        for i, v in enumerate(
            ema(
                [(var4l[i] + var6l[i] * 2) / 2 if low[i] <= var5l[i] else 0 for i in range(n)],
                3,
            )
        )
    ]
    var9l = [min(v, 100) for v in var8l]
    return var9, var9l


# ---------------------------------------------------------------------------
# 信号 / 策略注册表
# ---------------------------------------------------------------------------
@dataclass
class Signal:
    side: str  # 'long' | 'short'
    take_profit: float  # 止盈距离（价格）
    stop_loss: float  # 止损距离（价格）
    reason: str = ""  # 触发原因，展示在成交明细里


@dataclass
class StrategyContext:
    symbol: str
    tick_size: float
    multiplier: float


@dataclass
class StrategyDef:
    id: str
    name: str
    description: str
    category: str
    func: Callable[[list, StrategyContext], list]
    period: str = "5"  # 该策略设计时使用的 K 线周期（分钟）
    params: Optional[dict] = None  # 展示用的参数说明


STRATEGIES: dict[str, StrategyDef] = {}


def register(id: str, name: str, description: str, category: str = "趋势", period: str = "5", params: Optional[dict] = None):
    """策略注册装饰器。"""

    def deco(fn):
        STRATEGIES[id] = StrategyDef(id, name, description, category, fn, period, params)
        return fn

    return deco


def _session_key(time_str: str) -> Optional[str]:
    """09:00-09:15 -> morning，21:00-21:15 -> night，其余 None。"""
    parts = time_str.split(" ")
    if len(parts) < 2:
        return None
    hh, mm = (int(x) for x in parts[1].split(":")[:2])
    if hh == 9 and 0 <= mm <= 15:
        return "morning"
    if hh == 21 and 0 <= mm <= 15:
        return "night"
    return None


@register(
    id="reversal",
    name="反转信号",
    description="开盘（日盘 09:00-09:15 / 夜盘 21:00-21:15）出现指标红柱做多、绿柱做空，每个时段最多开一单，固定 10 跳止盈止损。",
    category="反转",
    period="5",
    params={"开仓窗口": "09:00-09:15 / 21:00-21:15", "止盈止损": "各 10 跳", "指标": "同花顺反转指标"},
)
def strategy_reversal(bars: list[dict], ctx: StrategyContext) -> list:
    var9, var9l = reversal_indicator(bars)
    jump = ctx.tick_size * 10
    used: set = set()
    signals: list = [None] * len(bars)
    for i, b in enumerate(bars):
        key = _session_key(b["time"])
        if not key:
            continue
        slot = (b["time"].split(" ")[0], key)
        if slot in used:
            continue
        # 旧前端的绿柱判据写成 var9 < -0.1，而 VAR9 恒 >= 0，导致永远不会做空；
        # 图上绿柱画的是 -VAR9，意图是 VAR9 > 0.1，这里按意图修正。
        green = not _isnan(var9[i]) and var9[i] > 0.1
        red = not _isnan(var9l[i]) and var9l[i] > 0.1
        if green and red:
            continue
        if red:
            signals[i] = Signal("long", jump, jump, "反转信号·红柱")
        elif green:
            signals[i] = Signal("short", jump, jump, "反转信号·绿柱")
        else:
            continue
        used.add(slot)
    return signals


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------
def _round(v: float, n: int = 2) -> float:
    return round(float(v), n)


def run_backtest(
    bars: list[dict],
    strategy_id: str,
    symbol: str,
    lots: int = DEFAULT_LOTS,
    initial_capital: float = INITIAL_CAPITAL,
) -> dict:
    """在 bars 上回测一个策略，返回统计、成交明细、净值曲线。"""
    if strategy_id not in STRATEGIES:
        raise KeyError(f"未知策略: {strategy_id}")
    sdef = STRATEGIES[strategy_id]
    cfg = get_instrument_config(symbol)
    tick_size, multiplier = cfg["tickSize"], cfg["multiplier"]
    ctx = StrategyContext(symbol, tick_size, multiplier)

    if not bars:
        return _build_result(sdef, symbol, lots, initial_capital, [], [], bars)

    signals = sdef.func(bars, ctx)
    capital = initial_capital
    trades: list[dict] = []
    position: Optional[dict] = None

    def pnl_of(side: str, entry: float, exit_: float) -> float:
        diff = exit_ - entry if side == "long" else entry - exit_
        return diff * multiplier * lots

    def close_position(idx: int, price: float, reason: str):
        nonlocal capital, position
        profit = pnl_of(position["side"], position["entryPrice"], price)
        capital += profit
        trades.append(
            {
                "no": len(trades) + 1,
                "side": position["side"],
                "entryTime": position["entryTime"],
                "entryIndex": position["entryIndex"],
                "entryPrice": _round(position["entryPrice"], 4),
                "exitTime": bars[idx]["time"],
                "exitIndex": idx,
                "exitPrice": _round(price, 4),
                "lots": lots,
                "reason": reason,
                "signal": position["signal"],
                "takeProfit": _round(position["takeProfit"], 4),
                "stopLoss": _round(position["stopLoss"], 4),
                "profit": _round(profit),
                "capital": _round(capital),
                "holdBars": idx - position["entryIndex"],
            }
        )
        position = None

    for i, b in enumerate(bars):
        # 1) 先处理已有仓位的止盈止损（开仓当根不检查，开仓价就是该根收盘）
        if position is not None:
            hit_price = hit_reason = None
            if position["side"] == "long":
                # 同一根 K 线内无法判断先后，按保守原则先判止损
                if b["low"] <= position["stopLoss"]:
                    hit_price, hit_reason = position["stopLoss"], "止损"
                elif b["high"] >= position["takeProfit"]:
                    hit_price, hit_reason = position["takeProfit"], "止盈"
            else:
                if b["high"] >= position["stopLoss"]:
                    hit_price, hit_reason = position["stopLoss"], "止损"
                elif b["low"] <= position["takeProfit"]:
                    hit_price, hit_reason = position["takeProfit"], "止盈"
            if hit_price is not None:
                close_position(i, hit_price, hit_reason)

        # 2) 空仓时才接收新信号，以收盘价开仓
        if position is None and signals[i] is not None:
            s: Signal = signals[i]
            entry = b["close"]
            if s.side == "long":
                tp, sl = entry + s.take_profit, entry - s.stop_loss
            else:
                tp, sl = entry - s.take_profit, entry + s.stop_loss
            position = {
                "side": s.side,
                "entryPrice": entry,
                "entryTime": b["time"],
                "entryIndex": i,
                "takeProfit": tp,
                "stopLoss": sl,
                "signal": s.reason,
            }

    # 3) 数据结束仍有持仓：按最后收盘价强平
    if position is not None:
        close_position(len(bars) - 1, bars[-1]["close"], "强制平仓")

    return _build_result(sdef, symbol, lots, initial_capital, trades, signals, bars)


def _build_result(sdef, symbol, lots, initial_capital, trades, signals, bars) -> dict:
    stats = compute_stats(trades, initial_capital)
    equity = build_equity_curve(trades, initial_capital, bars)
    stats["maxDrawdown"], stats["maxDrawdownPct"] = _max_drawdown([p["equity"] for p in equity])
    stats["timeSpan"] = (
        f"{bars[0]['time'][:10].replace('-', '/')} ~ {bars[-1]['time'][:10].replace('-', '/')}" if bars else "--"
    )
    return {
        "strategy": {
            "id": sdef.id,
            "name": sdef.name,
            "description": sdef.description,
            "category": sdef.category,
            "period": sdef.period,
            "params": sdef.params or {},
        },
        "symbol": symbol,
        "lots": lots,
        "initialCapital": initial_capital,
        "stats": stats,
        "trades": trades,
        "equity": equity,
    }


def compute_stats(trades: list[dict], initial_capital: float) -> dict:
    n = len(trades)
    wins = [t["profit"] for t in trades if t["profit"] > 0]
    losses = [t["profit"] for t in trades if t["profit"] < 0]
    total = sum(t["profit"] for t in trades)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    # 盈亏比 = 平均盈利 / 平均亏损；没有亏损单时无法计算，返回 None（前端显示 "--"/"∞"）
    if avg_loss > 0:
        pl_ratio = avg_win / avg_loss
    else:
        pl_ratio = None
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else None

    max_win_streak = max_loss_streak = cur_w = cur_l = 0
    for t in trades:
        if t["profit"] > 0:
            cur_w, cur_l = cur_w + 1, 0
        elif t["profit"] < 0:
            cur_l, cur_w = cur_l + 1, 0
        else:
            cur_w = cur_l = 0
        max_win_streak, max_loss_streak = max(max_win_streak, cur_w), max(max_loss_streak, cur_l)

    longs = [t for t in trades if t["side"] == "long"]
    shorts = [t for t in trades if t["side"] == "short"]

    def win_rate(ts):
        return _round(len([t for t in ts if t["profit"] > 0]) / len(ts) * 100) if ts else 0.0

    return {
        "tradeCount": n,
        "winCount": len(wins),
        "lossCount": len(losses),
        "winRate": _round(len(wins) / n * 100) if n else 0.0,
        "totalProfit": _round(total),
        "returnPct": _round(total / initial_capital * 100) if initial_capital else 0.0,
        "avgProfit": _round(total / n) if n else 0.0,
        "avgWin": _round(avg_win),
        "avgLoss": _round(avg_loss),
        "plRatio": _round(pl_ratio) if pl_ratio is not None else None,
        "profitFactor": _round(profit_factor) if profit_factor is not None else None,
        "maxWin": _round(max(wins)) if wins else 0.0,
        "maxLoss": _round(min(losses)) if losses else 0.0,
        "maxWinStreak": max_win_streak,
        "maxLossStreak": max_loss_streak,
        "longCount": len(longs),
        "shortCount": len(shorts),
        "longWinRate": win_rate(longs),
        "shortWinRate": win_rate(shorts),
        "longProfit": _round(sum(t["profit"] for t in longs)),
        "shortProfit": _round(sum(t["profit"] for t in shorts)),
        "avgHoldBars": _round(sum(t["holdBars"] for t in trades) / n, 1) if n else 0.0,
    }


def build_equity_curve(trades: list[dict], initial_capital: float, bars: list[dict]) -> list[dict]:
    """按成交（平仓）时间生成净值曲线，起点为第一根 K 线。"""
    if not bars:
        return []
    curve = [{"time": bars[0]["time"], "equity": _round(initial_capital), "tradeNo": 0}]
    for t in trades:
        curve.append({"time": t["exitTime"], "equity": t["capital"], "tradeNo": t["no"]})
    return curve


def _max_drawdown(equity: list[float]) -> tuple[float, float]:
    peak = None
    max_dd = max_dd_pct = 0.0
    for v in equity:
        peak = v if peak is None else max(peak, v)
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd / peak * 100 if peak > 0 else 0.0
    return _round(max_dd), _round(max_dd_pct)


def list_strategies() -> list[dict]:
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "period": s.period,
            "params": s.params or {},
        }
        for s in STRATEGIES.values()
    ]


def slice_recent_days(bars: list[dict], days: int) -> list[dict]:
    """取数据中最后 days 个自然日的 K 线（以数据最后一根的日期为基准，而不是今天）。"""
    if not bars or days <= 0:
        return bars
    from datetime import datetime, timedelta

    last = datetime.strptime(bars[-1]["time"], "%Y-%m-%d %H:%M:%S")
    start = (last - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    return [b for b in bars if b["time"] >= start]
