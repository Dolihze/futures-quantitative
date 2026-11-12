"""量化回测引擎单元测试：python -m pytest tests -q（或 python tests/test_backtest_engine.py）。

用手工构造的 K 线验证撮合、止盈止损、盈亏比等统计，期望值都是手算的。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import backtest_engine as be  # noqa: E402


def bar(time, o, h, l, c):
    return {"time": time, "open": o, "high": h, "low": l, "close": c, "volume": 1}


def run_with_signals(bars, signals, symbol="FU2611", lots=1):
    """临时注册一个按给定信号开仓的策略并回测。"""

    @be.register(id="_t", name="t", description="t")
    def _s(b, ctx):
        return signals

    try:
        return be.run_backtest(bars, "_t", symbol, lots)
    finally:
        be.STRATEGIES.pop("_t", None)


def test_long_take_profit_and_short_stop_loss():
    # FU: tickSize=1, multiplier=10，1 手一个价位 = 10 元
    bars = [
        bar("2026-10-20 09:05:00", 100, 100, 100, 100),  # 做多信号，收盘 100 开仓；TP=110 SL=90
        bar("2026-10-20 09:10:00", 100, 111, 99, 105),   # 最高 111 >= 110 -> 止盈 +10 价位 = +100 元
        bar("2026-10-20 09:15:00", 105, 105, 105, 105),  # 做空信号，收盘 105 开仓；TP=95 SL=115
        bar("2026-10-20 09:20:00", 105, 116, 104, 110),  # 最高 116 >= 115 -> 止损 -10 价位 = -100 元
    ]
    sig = [be.Signal("long", 10, 10), None, be.Signal("short", 10, 10), None]
    r = run_with_signals(bars, sig)
    t = r["trades"]
    assert len(t) == 2
    assert (t[0]["side"], t[0]["reason"], t[0]["exitPrice"], t[0]["profit"]) == ("long", "止盈", 110, 100.0)
    assert (t[1]["side"], t[1]["reason"], t[1]["exitPrice"], t[1]["profit"]) == ("short", "止损", 115, -100.0)
    s = r["stats"]
    assert s["tradeCount"] == 2 and s["winRate"] == 50.0 and s["totalProfit"] == 0.0
    assert s["plRatio"] == 1.0  # 平均盈利 100 / 平均亏损 100
    assert r["equity"][-1]["equity"] == be.INITIAL_CAPITAL


def test_same_bar_hits_both_prefers_stop_loss():
    bars = [
        bar("2026-10-20 09:05:00", 100, 100, 100, 100),
        bar("2026-10-20 09:10:00", 100, 120, 80, 100),  # 同时触及止盈止损，保守按止损
    ]
    r = run_with_signals(bars, [be.Signal("long", 10, 10), None])
    assert r["trades"][0]["reason"] == "止损" and r["trades"][0]["profit"] == -100.0


def test_no_new_entry_while_holding_and_force_close_at_end():
    bars = [
        bar("2026-10-20 09:05:00", 100, 100, 100, 100),
        bar("2026-10-20 09:10:00", 100, 102, 98, 101),   # 持仓中，来的信号被忽略
        bar("2026-10-20 09:15:00", 101, 102, 99, 103),
    ]
    sig = [be.Signal("long", 10, 10), be.Signal("short", 10, 10), None]
    r = run_with_signals(bars, sig, lots=2)
    assert len(r["trades"]) == 1
    t = r["trades"][0]
    assert t["reason"] == "强制平仓" and t["exitPrice"] == 103
    assert t["profit"] == 3 * 10 * 2  # 3 个价位 * 乘数 10 * 2 手


def test_stats_pl_ratio_profit_factor_and_drawdown():
    bars = [bar(f"2026-10-20 09:{5 * i:02d}:00", 100, 100, 100, 100) for i in range(1, 6)]
    trades = [
        {"profit": 300.0, "side": "long", "holdBars": 1},
        {"profit": -100.0, "side": "long", "holdBars": 2},
        {"profit": -100.0, "side": "short", "holdBars": 3},
        {"profit": 100.0, "side": "short", "holdBars": 4},
    ]
    s = be.compute_stats(trades, 10000)
    assert s["winRate"] == 50.0
    assert s["avgWin"] == 200.0 and s["avgLoss"] == 100.0 and s["plRatio"] == 2.0
    assert s["profitFactor"] == 2.0  # 400 / 200
    assert s["maxLossStreak"] == 2 and s["maxWinStreak"] == 1
    assert s["longWinRate"] == 50.0 and s["shortCount"] == 2
    assert be._max_drawdown([10000, 10300, 10200, 10100, 10200]) == (200.0, round(200 / 10300 * 100, 2))
    del bars


def test_no_loss_gives_none_ratio_and_empty_is_safe():
    s = be.compute_stats([{"profit": 50.0, "side": "long", "holdBars": 1}], 10000)
    assert s["plRatio"] is None and s["profitFactor"] is None and s["winRate"] == 100.0
    r = be.run_backtest([], "reversal", "FU2611")
    assert r["stats"]["tradeCount"] == 0 and r["equity"] == []


def test_reversal_strategy_runs_and_trades_only_in_windows():
    import random
    from datetime import datetime, timedelta

    random.seed(3)
    price, bars = 2900.0, []
    t = datetime(2026, 10, 1, 9, 0)
    for _ in range(2500):
        price += random.uniform(-8, 8)
        o, c = price, price + random.uniform(-5, 5)
        bars.append(bar(t.strftime("%Y-%m-%d %H:%M:%S"), o, max(o, c) + random.uniform(0, 3), min(o, c) - random.uniform(0, 3), c))
        t += timedelta(minutes=5)
        if 15 <= t.hour < 21:
            t = t.replace(hour=21, minute=0)
        if t.hour >= 23:
            t = (t + timedelta(days=1)).replace(hour=9, minute=0)
    r = be.run_backtest(bars, "reversal", "FU2611", 5)
    assert r["stats"]["tradeCount"] == len(r["trades"])
    for tr in r["trades"]:
        hh, mm = (int(x) for x in tr["entryTime"].split(" ")[1].split(":")[:2])
        assert (hh, mm <= 15) in ((9, True), (21, True))
        assert tr["entryIndex"] <= tr["exitIndex"]
    # 每个交易日的每个时段最多开一单
    slots = [(tr["entryTime"][:10], tr["entryTime"][11:13]) for tr in r["trades"]]
    assert len(slots) == len(set(slots))


def test_slice_recent_days_and_registry():
    bars = [bar("2026-10-01 09:05:00", 1, 1, 1, 1), bar("2026-10-20 09:05:00", 1, 1, 1, 1), bar("2026-10-25 09:05:00", 1, 1, 1, 1)]
    assert [b["time"][:10] for b in be.slice_recent_days(bars, 7)] == ["2026-10-20", "2026-10-25"]
    ids = [s["id"] for s in be.list_strategies()]
    assert "reversal" in ids


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
