"""量化回测引擎：指标、策略注册表、撮合与统计。

设计：
  - 策略 = 一个注册过的函数 `fn(bars, ctx) -> list[Signal | None]`，长度与 K 线相同；
    某根 K 线收盘时想开仓就返回 Signal（方向 + 止盈/止损距离），否则返回 None。
    Signal 默认按该根收盘价市价开仓；填了 entry_price 则改为限价挂单（下一根起触价成交），
    填了 stop_price 用绝对止损价，take_profit=None 表示不设止盈（只靠止损出局）。
  - 引擎负责：同一时刻只持一个仓位（或一张挂单）、逐根 K 线检查止盈止损、结算盈亏、统计胜率/盈亏比/净值曲线。
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
# 品种目录：按合约代码里的品种字母（fu2611 -> FU）取最小变动价位和合约乘数
# ---------------------------------------------------------------------------
# (品种代码, 名称, 交易所, 最小变动价位, 合约乘数)。
# 回测对象是本地行情库里已导入的具体合约；目录只提供结算用的合约参数和显示名。
# 最小变动价位 / 合约乘数以交易所合约规则为准，乘数 = 每手交易单位（吨/手、克/手、桶/手、元/点）。
_CATALOG = [
    # 上期所 SHFE
    ("CU", "沪铜", "SHFE", 10, 5), ("AL", "沪铝", "SHFE", 5, 5), ("ZN", "沪锌", "SHFE", 5, 5),
    ("PB", "沪铅", "SHFE", 5, 5), ("NI", "沪镍", "SHFE", 10, 1), ("SN", "沪锡", "SHFE", 10, 1),
    ("AU", "沪金", "SHFE", 0.02, 1000), ("AG", "沪银", "SHFE", 1, 15),
    ("RB", "螺纹钢", "SHFE", 1, 10), ("HC", "热卷", "SHFE", 1, 10), ("SS", "不锈钢", "SHFE", 5, 5),
    ("FU", "燃料油", "SHFE", 1, 10), ("BU", "沥青", "SHFE", 1, 10), ("RU", "橡胶", "SHFE", 5, 10),
    ("SP", "纸浆", "SHFE", 2, 10), ("AO", "氧化铝", "SHFE", 1, 20),
    # 能源中心 INE
    ("SC", "原油", "INE", 0.1, 1000), ("LU", "低硫燃料油", "INE", 1, 10),
    ("NR", "20号胶", "INE", 5, 10), ("BC", "国际铜", "INE", 10, 5),
    # 大商所 DCE
    ("A", "豆一", "DCE", 1, 10), ("B", "豆二", "DCE", 1, 10), ("M", "豆粕", "DCE", 1, 10),
    # 豆油 / 棕榈油：行情价格里奇偶数都出现，按 1 元/吨处理（以价格数据实测为准）
    ("Y", "豆油", "DCE", 1, 10), ("P", "棕榈油", "DCE", 1, 10), ("C", "玉米", "DCE", 1, 10),
    ("CS", "玉米淀粉", "DCE", 1, 10), ("JD", "鸡蛋", "DCE", 1, 5), ("L", "塑料", "DCE", 1, 5),
    ("V", "PVC", "DCE", 1, 5), ("PP", "聚丙烯", "DCE", 1, 5), ("EB", "苯乙烯", "DCE", 1, 5),
    ("EG", "乙二醇", "DCE", 1, 10), ("PG", "液化石油气", "DCE", 1, 20),
    ("I", "铁矿石", "DCE", 0.5, 100), ("J", "焦炭", "DCE", 0.5, 100), ("JM", "焦煤", "DCE", 0.5, 60),
    ("LH", "生猪", "DCE", 5, 16), ("RR", "粳米", "DCE", 1, 10), ("FB", "纤维板", "DCE", 0.5, 10),
    # 郑商所 CZCE
    ("CF", "棉花", "CZCE", 5, 5), ("SR", "白糖", "CZCE", 1, 10), ("TA", "PTA", "CZCE", 2, 5),
    ("MA", "甲醇", "CZCE", 1, 10), ("FG", "玻璃", "CZCE", 1, 20), ("RM", "菜粕", "CZCE", 1, 10),
    ("OI", "菜油", "CZCE", 1, 10), ("SA", "纯碱", "CZCE", 1, 20), ("UR", "尿素", "CZCE", 1, 20),
    ("PF", "短纤", "CZCE", 2, 5), ("AP", "苹果", "CZCE", 1, 10), ("CJ", "红枣", "CZCE", 5, 5),
    ("PK", "花生", "CZCE", 2, 5), ("SF", "硅铁", "CZCE", 2, 5), ("SM", "锰硅", "CZCE", 2, 5),
    ("PX", "对二甲苯", "CZCE", 2, 5), ("SH", "烧碱", "CZCE", 1, 30),
    # 中金所 CFFEX（乘数为每点元数）
    ("IF", "沪深300", "CFFEX", 0.2, 300), ("IH", "上证50", "CFFEX", 0.2, 300),
    ("IC", "中证500", "CFFEX", 0.2, 200), ("IM", "中证1000", "CFFEX", 0.2, 200),
    ("T", "10年国债", "CFFEX", 0.005, 10000), ("TF", "5年国债", "CFFEX", 0.005, 10000),
    ("TS", "2年国债", "CFFEX", 0.002, 20000), ("TL", "30年国债", "CFFEX", 0.01, 10000),
]
# 交易保证金率（一般持仓），杠杆 = 1 / 保证金率。用于「按保证金收益率」触发的策略（如反马丁）。
# 保证金率由交易所随行情和合约临近交割不断调整，没有固定值；这里是投机持仓的近期水平，
# 回测只用它把价格涨跌换算成保证金收益率，不影响普通策略的盈亏结算。
# 燃料油 FU 取 20%（5 倍杠杆，上期所 2026-11-03 起 FU2612 / FU2701 一般持仓 20%）。
# 品种不在这里的走 DEFAULT_MARGIN_RATE。需要调整某个品种时改这一张表即可。
MARGIN_RATES: dict[str, float] = {
    "FU": 0.20,
    "BU": 0.16, "RB": 0.12, "HC": 0.12, "SS": 0.11, "RU": 0.16, "SP": 0.12,
    "CU": 0.14, "AL": 0.13, "ZN": 0.13, "PB": 0.13, "NI": 0.15, "SN": 0.18, "AO": 0.14,
    "AU": 0.23, "AG": 0.25,
    "SC": 0.23, "LU": 0.23, "NR": 0.16, "BC": 0.14,
    "IF": 0.14, "IH": 0.14, "IC": 0.14, "IM": 0.14,
    "TS": 0.01, "TF": 0.02, "T": 0.03, "TL": 0.045,
}
DEFAULT_MARGIN_RATE = 0.11   # 大商所 / 郑商所多数品种的一般水平
INSTRUMENT_CONFIG: dict[str, dict] = {
    code: {"tickSize": tick, "multiplier": mult, "marginRate": MARGIN_RATES.get(code, DEFAULT_MARGIN_RATE)}
    for code, _n, _e, tick, mult in _CATALOG
}
DEFAULT_INSTRUMENT = {"tickSize": 1, "multiplier": 10, "marginRate": DEFAULT_MARGIN_RATE}

INITIAL_CAPITAL = 10000.0
DEFAULT_LOTS = 5


def product_code(symbol: str) -> str:
    """FU2611 / fu2611 / fu -> FU。"""
    return re.sub(r"\d+", "", str(symbol).split(".")[-1]).upper()


def get_instrument_config(symbol: str) -> dict:
    return INSTRUMENT_CONFIG.get(product_code(symbol), DEFAULT_INSTRUMENT)


def contract_name(symbol: str) -> str:
    """具体合约的显示名：fu2611 -> 燃料油 FU2611；品种不在目录里时只返回大写合约代码。"""
    code = product_code(symbol)
    sym = str(symbol).split(".")[-1].upper()   # SHFE.fu2611 -> FU2611
    for c, name, *_ in _CATALOG:
        if c == code:
            return f"{name} {sym}"
    return sym


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
    take_profit: Optional[float]  # 止盈距离（价格）；None = 不设止盈，只靠止损出局
    stop_loss: float  # 止损距离（价格）；给了 stop_price 时被忽略
    reason: str = ""  # 触发原因，展示在成交明细里
    # ---- 以下为可选扩展：限价挂单 / 绝对价止损。都不填时行为与旧版完全一致（收盘价开仓、距离止损） ----
    entry_price: Optional[float] = None  # 限价挂单价：本根收盘后挂出，之后的 K 线触价才成交；None = 按本根收盘价立即开仓
    stop_price: Optional[float] = None  # 绝对止损价；None = 用 stop_loss 距离相对成交价计算
    expire_bars: Optional[int] = None  # 挂单有效根数（从下一根起算）；None = 一直有效，直到成交 / 止损位被破 / 数据结束


@dataclass
class StrategyContext:
    symbol: str
    tick_size: float
    multiplier: float
    margin_rate: float = DEFAULT_MARGIN_RATE   # 交易保证金率；杠杆 = 1 / margin_rate


@dataclass
class StrategyDef:
    id: str
    name: str
    description: str
    category: str
    func: Callable[[list, StrategyContext], list]
    period: str = "5"  # 该策略设计时使用的 K 线周期（分钟）
    params: Optional[dict] = None  # 展示用的参数说明
    # 自管仓位策略：为 True 时 func 不是返回信号，而是 func(bars, ctx, lots) -> list[dict]，
    # 直接返回已完成的成交（字段见 _managed_trade）。用于一轮里分批加仓、一次性全平这类
    # 「同一时刻一个仓位、固定手数」的信号撮合表达不了的策略
    managed: bool = False


STRATEGIES: dict[str, StrategyDef] = {}


def register(id: str, name: str, description: str, category: str = "趋势", period: str = "5",
             params: Optional[dict] = None, managed: bool = False):
    """策略注册装饰器。"""

    def deco(fn):
        STRATEGIES[id] = StrategyDef(id, name, description, category, fn, period, params, managed)
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
# 趋势跟随：三波段回踩建仓
# ---------------------------------------------------------------------------
TREND_SWING_TICKS = 15  # ZigZag 阈值（跳）：价格从极值反向运动超过它才确认一个转折点
TREND_ENTRY_RATIO = 1 / 3  # 建仓位置 = 前一波段低点 + 波段高度 × 此比例（从低点往上量）
TREND_PENDING_BARS = 30  # 挂单有效根数；超过未成交就撤单
TREND_LEVELS = 3  # 趋势确认级数：连续 N 个低点 + N 个高点逐级抬高（做空相反）才算趋势


def zigzag_pivots(bars: list[dict], threshold: float) -> list[dict]:
    """ZigZag 转折点，逐根确认、不使用未来数据。

    价格从当前极值反向运动 >= threshold 时，才确认该极值是一个转折点。
    返回按确认时间升序的列表，每项：
      {"kind": "high"|"low", "price", "index": 极值所在 K 线, "confirm": 确认它的那根 K 线}
    相邻转折点一定高低交替；最后一个还在延伸中的极值没有被确认，不在列表里。
    """
    pivots: list[dict] = []
    if not bars:
        return pivots
    # 先观察方向：第一根的高 / 低作为双向候选极值，哪边先运动够 threshold 就定方向
    hi_p, hi_i = bars[0]["high"], 0
    lo_p, lo_i = bars[0]["low"], 0
    direction = 0  # 0 未定；1 = 正在找高点（向上段）；-1 = 正在找低点（向下段）
    for i in range(1, len(bars)):
        h, l = bars[i]["high"], bars[i]["low"]
        if direction == 0:
            if h > hi_p:
                hi_p, hi_i = h, i
            if l < lo_p:
                lo_p, lo_i = l, i
            up, down = hi_p - lo_p >= threshold and hi_i > lo_i, hi_p - lo_p >= threshold and lo_i > hi_i
            if up:
                pivots.append({"kind": "low", "price": lo_p, "index": lo_i, "confirm": i})
                direction = 1
            elif down:
                pivots.append({"kind": "high", "price": hi_p, "index": hi_i, "confirm": i})
                direction = -1
            continue
        if direction == 1:  # 向上段：跟踪高点，回落够 threshold 就确认高点
            if h > hi_p:
                hi_p, hi_i = h, i
            elif hi_p - l >= threshold:
                pivots.append({"kind": "high", "price": hi_p, "index": hi_i, "confirm": i})
                direction = -1
                lo_p, lo_i = l, i
        else:  # 向下段：跟踪低点，反弹够 threshold 就确认低点
            if l < lo_p:
                lo_p, lo_i = l, i
            elif h - lo_p >= threshold:
                pivots.append({"kind": "low", "price": lo_p, "index": lo_i, "confirm": i})
                direction = 1
                hi_p, hi_i = h, i
    return pivots


def split_sessions(bars: list[dict], gap_minutes: float = 5) -> list[tuple[int, int]]:
    """按时间缺口切分交易时段，返回 [(起始下标, 结束下标含)]。

    1 分钟线里连续交易时 K 线间隔是 1 分钟；相邻两根间隔超过 gap_minutes 就说明跨了时段
    （午间休市、10:15 小歇、日盘→夜盘、夜盘→次日日盘、周末）。时段之间有跳空，波段不能跨时段连。"""
    from datetime import datetime

    if not bars:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    prev = datetime.strptime(bars[0]["time"], "%Y-%m-%d %H:%M:%S")
    for i in range(1, len(bars)):
        cur = datetime.strptime(bars[i]["time"], "%Y-%m-%d %H:%M:%S")
        if (cur - prev).total_seconds() > gap_minutes * 60:
            spans.append((start, i - 1))
            start = i
        prev = cur
    spans.append((start, len(bars) - 1))
    return spans


def _strictly(seq: list[float], rising: bool) -> bool:
    return all((b > a) if rising else (b < a) for a, b in zip(seq, seq[1:]))


@register(
    id="trend_swing",
    name="三波段趋势跟随",
    description=(
        f"1 分钟线 ZigZag 在同一交易时段内，连续 {TREND_LEVELS} 个低点和 {TREND_LEVELS} 个高点逐级抬高（上升趋势）后，"
        "在前一个波段（低点→高点）从低点往上 1/3 处挂限价单顺势建仓，止损放在该波段底部，不设止盈，只靠止损出局。"
        "做空规则镜像（高点、低点逐级降低）。每个交易时段独立识别，不跨时段连接波段。"
    ),
    category="趋势",
    period="1",
    params={
        "波段识别": f"ZigZag，反向 {TREND_SWING_TICKS} 跳确认；每个交易时段独立",
        "趋势确认": f"连续 {TREND_LEVELS} 个低点 + {TREND_LEVELS} 个高点逐级抬高（做空相反）",
        "建仓位置": "前一波段低点 + 1/3 波段高度（做空为高点 - 1/3）",
        "止损": "前一波段底部（做空为顶部）",
        "止盈": "不设",
        "挂单有效": f"{TREND_PENDING_BARS} 根 K 线，且不跨时段",
    },
)
def strategy_trend_swing(bars: list[dict], ctx: StrategyContext) -> list:
    """做多（做空镜像）：同一交易时段内确认的转折点序列 L1 H1 L2 H2 ... Ln Hn，
    低点 L1<L2<...<Ln 且高点 H1<H2<...<Hn（n = TREND_LEVELS）才算上升趋势。
    Hn 被确认（价格从 Hn 回落超过阈值）的那根 K 线收盘后，在 Ln + (Hn-Ln)/3 挂限价买单，止损 Ln。

    只用确认时已知的转折点，没有未来函数。ZigZag 逐个交易时段单独计算：时段之间有跳空，
    跨时段的转折点会把已经作废的旧结构当成趋势；挂单也不跨时段（时段末撤单）。
    同一个转折点序列只挂一次单，止损后要等新的转折点出现才会再有信号。
    """
    threshold = ctx.tick_size * TREND_SWING_TICKS
    need = TREND_LEVELS * 2
    signals: list = [None] * len(bars)
    for lo_idx, hi_idx in split_sessions(bars):
        sub = bars[lo_idx : hi_idx + 1]
        pivots = zigzag_pivots(sub, threshold)
        for k in range(need - 1, len(pivots)):
            window = pivots[k - need + 1 : k + 1]
            last = window[-1]
            i = lo_idx + last["confirm"]
            if signals[i] is not None:
                continue
            lows = [p["price"] for p in window if p["kind"] == "low"]
            highs = [p["price"] for p in window if p["kind"] == "high"]
            # 本时段剩余的 K 线数：挂单不跨时段，最多只等到时段末
            left = hi_idx - i
            expire = min(TREND_PENDING_BARS, left)
            if expire <= 0:
                continue
            if window[0]["kind"] == "low":  # 低 高 低 高 ...：上升趋势
                if not (_strictly(lows, True) and _strictly(highs, True)):
                    continue
                lo_n, hi_n = lows[-1], highs[-1]
                entry = _snap(lo_n + (hi_n - lo_n) * TREND_ENTRY_RATIO, ctx.tick_size)
                if entry <= lo_n:
                    continue
                signals[i] = Signal("long", None, entry - lo_n, "三波段趋势·做多", entry_price=entry,
                                    stop_price=lo_n, expire_bars=expire)
            else:  # 高 低 高 低 ...：下降趋势
                if not (_strictly(lows, False) and _strictly(highs, False)):
                    continue
                lo_n, hi_n = lows[-1], highs[-1]
                entry = _snap(hi_n - (hi_n - lo_n) * TREND_ENTRY_RATIO, ctx.tick_size)
                if entry >= hi_n:
                    continue
                signals[i] = Signal("short", None, hi_n - entry, "三波段趋势·做空", entry_price=entry,
                                    stop_price=hi_n, expire_bars=expire)
    return signals


# ---------------------------------------------------------------------------
# 反马丁：顺势加仓
# ---------------------------------------------------------------------------
# (开仓时点, 收盘平仓时点)：K 线时间是结束时间，09:05 即 09:04~09:05 这根 1 分钟线，用它的收盘价开首单
AM_ROUNDS = (("09:05", "11:30"), ("13:35", "15:00"), ("21:05", "23:00"))
# 两个百分比都是「相对占用保证金」的收益率（带杠杆）：价格变动幅度 = 保证金收益率 × 保证金率。
# 例：燃料油保证金率 20%（5 倍杠杆），保证金收益 3% = 价格涨 0.6%，保证金亏损 5% = 价格跌约 1%。
AM_STEP_PCT = 0.03   # 保证金浮盈每增加 3%（相对首单）加 1 手
AM_STOP_PCT = 0.05   # 总浮亏达到占用保证金的 5% 全部平仓


def _hhmm(time_str: str) -> str:
    """'2026-10-20 09:05:00' -> '09:05'。"""
    return time_str[11:16]


def _am_stop_price(entries: list[float], margin_rate: float) -> float:
    """当前持仓（每笔 1 手）的止损价：总浮亏 = Σ(开仓价 - 价) 达到 占用保证金 × 5% 时的价格。
    占用保证金 = Σ开仓价 × 乘数 × 保证金率；浮亏 = Σ(开仓价 - 价) × 乘数，乘数两边约掉：
        Σ(开仓价 - 价) = 5% × 保证金率 × Σ开仓价  =>  价 = Σ开仓价 × (1 - 5% × 保证金率) / 手数"""
    return sum(entries) * (1 - AM_STOP_PCT * margin_rate) / len(entries)


@register(
    id="anti_martingale",
    name="反马丁策略",
    description=(
        "每天 09:05、13:35、21:05 各开一轮：以该时刻收盘价买入 1 手多单；保证金浮盈相对首单每增加 3% 就再加 1 手"
        "（+3% 加第 2 手，+6% 加第 3 手，以此类推），越赚越加。"
        "持仓总亏损达到占用保证金的 5% 时全部平仓止损；未止损则分别在 11:30、15:00、23:00 收盘全部平仓。"
        "百分比按带杠杆的保证金收益率计算（如燃料油保证金率 20%，即 5 倍杠杆：价格涨约 0.6% 加仓、跌约 1% 止损）。"
        "每轮只做一次，止损后本时段不再开仓；每笔加仓单独记一笔成交。"
    ),
    category="加仓",
    period="1",
    params={
        "开仓时点": "09:05 / 13:35 / 21:05，各买入 1 手多",
        "加仓规则": "保证金浮盈相对首单每增加 3% 加 1 手（价格涨幅 = 3% × 保证金率）：+3% 第 2 手、+6% 第 3 手 …",
        "止损": "总浮亏达到占用保证金的 5%（价格跌幅 ≈ 5% × 保证金率），全部平仓",
        "保证金率": "按品种取交易所一般持仓水平，燃料油 20%（5 倍杠杆）",
        "收盘平仓": "11:30 / 15:00 / 23:00 全部平仓（依次对应 09:05 / 13:35 / 21:05 的轮次）",
        "手数": "首单及每次加仓固定 1 手（不使用页面的「每笔手数」）",
    },
    managed=True,
)
def strategy_anti_martingale(bars: list[dict], ctx: StrategyContext, lots: int = 1) -> list[dict]:
    """返回已完成的成交列表（字段见 _settle_managed）。每次加仓固定 1 手，lots 参数不参与。

    3% / 5% 都是带杠杆的保证金收益率，换算成价格要乘保证金率 m = ctx.margin_rate：
      加仓价 = 首单价 ×（1 + 3% × m × 下一级）；止损价见 _am_stop_price。
    每一轮独立，从开仓时点那根 K 线开始，逐根往后：
      1. 止损：先判。low 触及止损价就按止损价全部平仓（开盘已跳空到止损价下方则按开盘价）。
      2. 加仓：high 触及加仓价就以该价加 1 手（开盘已跳空到其上方则按开盘价）；
         一根 K 线涨过多级就连续加到位。每次加仓后止损价随持仓抬高，立刻再核对本根 K 线的 low。
      3. 收盘：走到该轮的收盘时点（11:30 / 15:00 / 23:00）那根 K 线，以收盘价全部平仓。
    同一根 K 线内无法判断涨跌先后，保守地先止损、再加仓；止损后本轮结束，不再重开。
    收盘时点之前数据就结束（缺数据 / 取的区间到此为止）则按最后一根收盘价强平。
    """
    fills: list[dict] = []
    n = len(bars)
    m = ctx.margin_rate
    close_of = dict(AM_ROUNDS)
    i = 0
    while i < n:
        open_hhmm = _hhmm(bars[i]["time"])
        base = bars[i]["close"]
        if open_hhmm not in close_of or not base or base <= 0:
            i += 1
            continue
        close_hhmm = close_of[open_hhmm]

        entries: list[tuple[int, float]] = [(i, base)]   # (K 线下标, 成交价)，每笔 1 手
        exit_idx, exit_price, exit_reason = n - 1, bars[n - 1]["close"], "强制平仓"   # 默认：数据结束强平
        for j in range(i + 1, n):
            b = bars[j]
            stop = _am_stop_price([p for _, p in entries], m)
            if b["low"] <= stop:
                exit_idx, exit_price, exit_reason = j, min(stop, b["open"]), "止损"
                break
            at_close = _hhmm(b["time"]) == close_hhmm
            stopped = False
            while not at_close:   # 收盘那根 K 线只平仓，不再加仓（否则会在收盘价上加一手又立刻平掉）
                # 已有 k 手时下一级是保证金浮盈 +3%×k，对应价格涨幅 3%×k×保证金率
                trigger = base * (1 + AM_STEP_PCT * m * len(entries))
                if b["high"] < trigger:
                    break
                entries.append((j, _snap(max(trigger, b["open"]), ctx.tick_size)))
                stop = _am_stop_price([p for _, p in entries], m)
                if b["low"] <= stop:
                    exit_idx, exit_price, exit_reason = j, min(stop, b["open"]), "止损"
                    stopped = True
                    break
            if stopped:
                break
            if at_close:
                exit_idx, exit_price, exit_reason = j, b["close"], "收盘平仓"
                break

        final_stop = _snap(_am_stop_price([p for _, p in entries], m), ctx.tick_size)
        exit_price = _snap(exit_price, ctx.tick_size)
        for k, (idx, price) in enumerate(entries):
            fills.append({
                "side": "long", "entryIndex": idx, "entryPrice": price,
                "exitIndex": exit_idx, "exitPrice": exit_price, "lots": 1,
                "reason": exit_reason,
                "signal": "反马丁·首单" if k == 0 else f"反马丁·第{k}次加仓",
                "takeProfit": None, "stopLoss": final_stop,
            })
        i = exit_idx + 1   # 本轮结束后才找下一轮（各轮的时段互不重叠）
    return fills


def _snap(price: float, tick: float) -> float:
    """价格规整到最小变动价位的整数倍（去浮点尾巴）。"""
    if not tick or tick <= 0:
        return price
    n = round(price / tick)
    s = f"{tick:.10f}".rstrip("0").rstrip(".")
    decimals = len(s.split(".")[1]) if "." in s else 0
    return round(n * tick, decimals)


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
    ctx = StrategyContext(symbol, tick_size, multiplier, cfg.get("marginRate", DEFAULT_MARGIN_RATE))

    if not bars:
        return _build_result(sdef, symbol, lots, initial_capital, [], [], bars)

    if sdef.managed:
        trades = _settle_managed(sdef.func(bars, ctx, lots), bars, multiplier, initial_capital)
        return _build_result(sdef, symbol, lots, initial_capital, trades, [], bars)

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
                "takeProfit": _round(position["takeProfit"], 4) if position["takeProfit"] is not None else None,
                "stopLoss": _round(position["stopLoss"], 4),
                "profit": _round(profit),
                "capital": _round(capital),
                "holdBars": idx - position["entryIndex"],
            }
        )
        position = None

    pending: Optional[dict] = None  # 等待成交的限价挂单

    def levels(s: Signal, entry: float) -> tuple[Optional[float], float]:
        """按成交价算出 (止盈价或 None, 止损价)。给了绝对止损价就用它，否则用距离。"""
        if s.side == "long":
            tp = None if s.take_profit is None else entry + s.take_profit
            sl = s.stop_price if s.stop_price is not None else entry - s.stop_loss
        else:
            tp = None if s.take_profit is None else entry - s.take_profit
            sl = s.stop_price if s.stop_price is not None else entry + s.stop_loss
        return tp, sl

    def open_position(i: int, s: Signal, entry: float, limit: bool = False):
        nonlocal position
        tp, sl = levels(s, entry)
        position = {
            "side": s.side,
            "entryPrice": entry,
            "entryTime": bars[i]["time"],
            "entryIndex": i,
            "takeProfit": tp,
            "stopLoss": sl,
            "signal": s.reason,
            "limit": limit,  # 限价挂单成交：成交那根 K 线内也要检查止损
        }

    for i, b in enumerate(bars):
        # 0) 处理挂单：信号出现的【下一根】起才可能成交（本根收盘才产生的信号，不能用本根的价格成交）
        if position is None and pending is not None and i > pending["index"]:
            s = pending["signal"]
            _tp, sl = levels(s, s.entry_price)
            long_ = s.side == "long"
            if (long_ and b["low"] <= sl) or (not long_ and b["high"] >= sl):
                # 价格先破了止损位：这笔单的前提（止损位有效）已不成立，作废。
                # 同一根 K 线既触及挂单价又触及止损位时也按作废处理（无法判断先后，保守）
                pending = None
            elif (long_ and b["low"] <= s.entry_price) or (not long_ and b["high"] >= s.entry_price):
                # 开盘价已经越过挂单价（跳空）时按开盘价成交，更真实也更不乐观
                fill = min(s.entry_price, b["open"]) if long_ else max(s.entry_price, b["open"])
                open_position(i, s, fill, limit=True)
                pending = None
                # 成交当根继续往下走，让下面的止损判断也适用于这一根（成交后同一根打到止损要算出局）
            elif s.expire_bars is not None and i - pending["index"] >= s.expire_bars:
                pending = None  # 挂单超时未成交，撤单

        # 1) 先处理已有仓位的止盈止损（市价开仓当根不检查，开仓价就是该根收盘；挂单成交当根要检查）
        if position is not None and (position["entryIndex"] != i or position["limit"]):
            hit_price = hit_reason = None
            if position["side"] == "long":
                # 同一根 K 线内无法判断先后，按保守原则先判止损
                if b["low"] <= position["stopLoss"]:
                    hit_price, hit_reason = position["stopLoss"], "止损"
                elif position["takeProfit"] is not None and b["high"] >= position["takeProfit"]:
                    hit_price, hit_reason = position["takeProfit"], "止盈"
            else:
                if b["high"] >= position["stopLoss"]:
                    hit_price, hit_reason = position["stopLoss"], "止损"
                elif position["takeProfit"] is not None and b["low"] <= position["takeProfit"]:
                    hit_price, hit_reason = position["takeProfit"], "止盈"
            if hit_price is not None:
                close_position(i, hit_price, hit_reason)

        # 2) 空仓且没有挂单时才接收新信号
        if position is None and pending is None and signals[i] is not None:
            s: Signal = signals[i]
            if s.entry_price is None:
                open_position(i, s, b["close"])      # 市价：以收盘价开仓
            else:
                pending = {"signal": s, "index": i}  # 限价：挂出，下一根起才可能成交

    # 3) 数据结束仍有持仓：按最后收盘价强平
    if position is not None:
        close_position(len(bars) - 1, bars[-1]["close"], "强制平仓")

    return _build_result(sdef, symbol, lots, initial_capital, trades, signals, bars)


def _settle_managed(fills: list[dict], bars: list[dict], multiplier: float, initial_capital: float) -> list[dict]:
    """把自管仓位策略返回的成交结算成标准成交明细（盈亏、账户权益、序号）。

    fills 每项：{side, entryIndex, entryPrice, exitIndex, exitPrice, lots, reason, signal,
                 takeProfit(可选), stopLoss(可选)}。
    一轮里的多笔加仓共用同一个出场点，按平仓时间排序后逐笔累计权益，
    这样净值曲线、胜率、盈亏比等统计与普通策略完全同一口径（每笔加仓单独计一笔）。
    """
    ordered = sorted(fills, key=lambda f: (f["exitIndex"], f["entryIndex"]))
    capital = initial_capital
    trades: list[dict] = []
    for f in ordered:
        diff = f["exitPrice"] - f["entryPrice"] if f["side"] == "long" else f["entryPrice"] - f["exitPrice"]
        profit = diff * multiplier * f["lots"]
        capital += profit
        tp, sl = f.get("takeProfit"), f.get("stopLoss")
        trades.append(
            {
                "no": len(trades) + 1,
                "side": f["side"],
                "entryTime": bars[f["entryIndex"]]["time"],
                "entryIndex": f["entryIndex"],
                "entryPrice": _round(f["entryPrice"], 4),
                "exitTime": bars[f["exitIndex"]]["time"],
                "exitIndex": f["exitIndex"],
                "exitPrice": _round(f["exitPrice"], 4),
                "lots": f["lots"],
                "reason": f["reason"],
                "signal": f.get("signal", ""),
                "takeProfit": _round(tp, 4) if tp is not None else None,
                "stopLoss": _round(sl, 4) if sl is not None else None,
                "profit": _round(profit),
                "capital": _round(capital),
                "holdBars": f["exitIndex"] - f["entryIndex"],
            }
        )
    return trades


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
            "managed": sdef.managed,   # 自管仓位：手数由策略自己决定，不使用页面的「每笔手数」
        },
        "symbol": symbol,
        "marginRate": get_instrument_config(symbol).get("marginRate", DEFAULT_MARGIN_RATE),   # 保证金率（杠杆 = 1 / 保证金率）
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
            "managed": s.managed,
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


def span_days(bars: list[dict]) -> int:
    """K 线数据覆盖的自然日数（首尾日期之差 + 1）。"""
    if not bars:
        return 0
    from datetime import datetime

    first = datetime.strptime(bars[0]["time"][:10], "%Y-%m-%d")
    last = datetime.strptime(bars[-1]["time"][:10], "%Y-%m-%d")
    return (last - first).days + 1


def data_coverage(all_bars: list[dict], days: int) -> dict:
    """所选 days 天相对于实际可得数据的覆盖情况。

    本地行情库里该合约导入的 tick 只覆盖有限的交易日，数据不足 days 天时，
    实际回测用的是全部可得数据，必须明确告诉用户，不能让「60 天」「90 天」悄悄变成同一份结果。
      availableDays：数据覆盖的自然日数
      requestedDays：用户选择的天数
      usedDays：本次回测实际覆盖的天数 = min(requested, available)
      truncated：所选范围超出可得数据（True 时前端提示「实际只有 N 天」）
    """
    available = span_days(all_bars)
    used = min(days, available) if available else 0
    return {
        "availableDays": available,
        "requestedDays": days,
        "usedDays": used,
        "truncated": bool(available) and days > available,
        "dataFrom": all_bars[0]["time"] if all_bars else None,
        "dataTo": all_bars[-1]["time"] if all_bars else None,
    }
