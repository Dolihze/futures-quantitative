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


def test_product_catalog():
    prods = be.list_products()
    codes = [p["code"] for p in prods]
    assert len(codes) == len(set(codes)) and len(codes) > 50
    # 默认品种是燃料油主连，且只有一个默认
    assert [p["code"] for p in prods if p["default"]] == ["FU"]
    fu = next(p for p in prods if p["code"] == "FU")
    assert fu["name"] == "燃料油主连" and fu["symbol"] == "FU0" and fu["exchange"] == "上期所"
    assert be.main_symbol("rb") == "RB0" and be.main_symbol("FU2611") == "FU0"
    # 每个品种都有可用的合约参数，且新浪主连代码形如 XX0
    for p in prods:
        cfg = be.get_instrument_config(p["code"])
        assert cfg["tickSize"] > 0 and cfg["multiplier"] > 0
        assert p["symbol"] == p["code"] + "0"
    assert be.get_instrument_config("AU0") == {"tickSize": 0.02, "multiplier": 1000}


def test_backtest_api_selects_product_main_contract():
    """product 参数选择品种主连：默认燃料油 FU0；未知品种返回 400；每个品种用自己的合约乘数结算。"""
    import backend

    asked = []
    bars = [bar("2026-10-20 09:05:00", 100, 100, 100, 100), bar("2026-10-20 09:10:00", 100, 101, 99, 100)]
    orig = backend.fetch_backtest_bars
    backend.fetch_backtest_bars = lambda symbol, period: (asked.append(symbol), bars)[1]
    try:
        client = backend.app.test_client()
        d = client.get("/api/backtest/overview?days=30").get_json()                       # 默认品种
        o = client.get("/api/backtest/overview?product=rb&days=30").get_json()           # 小写也可
        r = client.get("/api/backtest/run?strategy=reversal&product=AU&days=30").get_json()
        k = client.get("/api/backtest/kline?product=CU&period=5&days=30").get_json()
        bad = client.get("/api/backtest/overview?product=XX&days=30")
        bad_k = client.get("/api/backtest/kline?product=XX&period=5")
        prods = client.get("/api/backtest/products").get_json()
    finally:
        backend.fetch_backtest_bars = orig
    assert d["product"] == "FU" and d["symbol"] == "FU0" and d["symbolName"] == "燃料油主连"
    assert o["product"] == "RB" and o["symbol"] == "RB0" and o["symbolName"] == "螺纹钢主连"
    assert r["success"] and r["symbol"] == "AU0" and r["symbolName"] == "沪金主连"
    assert k["success"] and k["symbol"] == "CU0"
    assert set(asked) == {"FU0", "RB0", "AU0", "CU0"}
    assert bad.status_code == 400 and bad_k.status_code == 400
    assert prods["success"] and prods["default"] == "FU" and len(prods["data"]) > 50


def test_data_coverage_reports_truncation():
    # 数据只覆盖 10-20 ~ 10-25，共 6 个自然日
    bars = [bar("2026-10-20 09:05:00", 1, 1, 1, 1), bar("2026-10-25 09:05:00", 1, 1, 1, 1)]
    assert be.span_days(bars) == 6 and be.span_days([]) == 0
    c = be.data_coverage(bars, 90)
    assert c["availableDays"] == 6 and c["usedDays"] == 6 and c["truncated"] is True and c["requestedDays"] == 90
    assert c["dataFrom"].startswith("2026-10-20") and c["dataTo"].startswith("2026-10-25")
    ok = be.data_coverage(bars, 3)
    assert ok["usedDays"] == 3 and ok["truncated"] is False
    assert be.data_coverage([], 30)["truncated"] is False


def test_api_returns_coverage_so_60_and_90_are_not_silently_identical():
    import backend

    # 5 分钟线只有约 3 周：构造 21 天数据，每天 1 根
    bars = [bar(f"2026-10-{d:02d} 09:05:00", 100, 100, 100, 100) for d in range(1, 22)]
    orig = backend.fetch_backtest_bars
    backend.fetch_backtest_bars = lambda symbol, period: bars
    try:
        client = backend.app.test_client()
        o30 = client.get("/api/backtest/overview?days=30").get_json()
        o90 = client.get("/api/backtest/overview?days=90").get_json()
        r90 = client.get("/api/backtest/run?strategy=reversal&days=90").get_json()
        r7 = client.get("/api/backtest/run?strategy=reversal&days=7").get_json()
    finally:
        backend.fetch_backtest_bars = orig
    assert o30["availableDays"] == 21 and o90["availableDays"] == 21
    cov = o90["data"][0]["coverage"]
    assert cov["truncated"] and cov["requestedDays"] == 90 and cov["usedDays"] == 21
    assert r90["coverage"]["truncated"] and len(r90["kline"]) == 21
    assert not r7["coverage"]["truncated"] and len(r7["kline"]) == 8  # 末日往前 7 天（含端点）


def test_pnl_uses_each_products_multiplier():
    bars = [
        bar("2026-10-20 09:05:00", 100, 100, 100, 100),
        bar("2026-10-20 09:10:00", 100, 100, 100, 103),
    ]
    sig = [be.Signal("long", 100, 100), None]
    # 数据结束强平：多 3 个价位；FU 乘数 10、AU 乘数 1000
    assert run_with_signals(bars, sig, symbol="FU0", lots=1)["trades"][0]["profit"] == 30.0
    assert run_with_signals(bars, sig, symbol="AU0", lots=1)["trades"][0]["profit"] == 3000.0


# ----------------------------------------------------------------------------
# 引擎扩展：限价挂单 / 绝对止损价 / 不设止盈
# ----------------------------------------------------------------------------

def tbar(i, o, h, l, c):
    return bar(f"2026-10-20 09:{i:02d}:00", o, h, l, c)


def test_limit_order_fills_on_later_bar_with_absolute_stop_and_no_take_profit():
    bars = [
        tbar(1, 100, 100, 100, 100),   # 信号：在 95 挂多单，止损 90，不设止盈
        tbar(2, 100, 120, 99, 118),    # 最低 99 > 95，没成交
        tbar(3, 118, 118, 94, 96),     # 最低 94 <= 95，95 成交；成交当根没打到止损 90
        tbar(4, 96, 200, 96, 199),     # 涨到 200：没有止盈，继续持有
        tbar(5, 199, 199, 89, 90),     # 跌破 90，止损出局
    ]
    sig = [be.Signal("long", None, 5, "t", entry_price=95, stop_price=90), None, None, None, None]
    t = run_with_signals(bars, sig)["trades"]
    assert len(t) == 1
    assert t[0]["entryPrice"] == 95 and t[0]["entryIndex"] == 2
    assert t[0]["takeProfit"] is None and t[0]["stopLoss"] == 90
    assert t[0]["reason"] == "止损" and t[0]["exitPrice"] == 90 and t[0]["profit"] == -50.0


def test_limit_order_cannot_fill_on_signal_bar():
    bars = [
        tbar(1, 100, 100, 90, 100),    # 信号当根最低 90 已低于挂单价 95，但信号收盘才产生，不能用本根成交
        tbar(2, 100, 101, 99, 100),
    ]
    sig = [be.Signal("long", None, 5, "t", entry_price=95, stop_price=90), None]
    assert run_with_signals(bars, sig)["trades"] == []


def test_limit_order_gap_fills_at_open():
    bars = [
        tbar(1, 100, 100, 100, 100),
        tbar(2, 90, 92, 88, 91),       # 跳空低开到 90，已低于挂单价 95：按开盘价 90 成交（不是 95）
        tbar(3, 91, 100, 91, 99),
    ]
    sig = [be.Signal("long", None, 10, "t", entry_price=95, stop_price=80), None, None]
    t = run_with_signals(bars, sig)["trades"]
    assert t[0]["entryPrice"] == 90 and t[0]["reason"] == "强制平仓" and t[0]["profit"] == 90.0


def test_limit_order_filled_and_stopped_in_same_bar():
    bars = [
        tbar(1, 100, 100, 100, 100),
        tbar(2, 100, 100, 92, 93),     # 先触及挂单价 95 成交，同一根最低 92 未破止损 90：持有
        tbar(3, 93, 93, 85, 88),       # 跌破止损 90
    ]
    sig = [be.Signal("long", None, 5, "t", entry_price=95, stop_price=90), None, None]
    t = run_with_signals(bars, sig)["trades"]
    assert len(t) == 1 and t[0]["entryIndex"] == 1 and t[0]["exitIndex"] == 2 and t[0]["profit"] == -50.0


def test_limit_order_filled_bar_that_also_breaks_stop_is_cancelled_not_filled():
    """成交当根若同时破了止损位：无法判断先后，保守地作废，不会出现“成交即止损”的假成交。"""
    bars = [tbar(1, 100, 100, 100, 100), tbar(2, 100, 100, 85, 88)]
    sig = [be.Signal("long", None, 5, "t", entry_price=95, stop_price=90), None]
    assert run_with_signals(bars, sig)["trades"] == []


def test_limit_order_cancelled_when_stop_level_broken_first():
    bars = [
        tbar(1, 100, 100, 100, 100),
        tbar(2, 100, 100, 85, 86),     # 同一根既到挂单价 95 又破止损 90：无法判断先后，保守作废
        tbar(3, 86, 100, 80, 95),      # 作废之后价格再回来也不会成交
    ]
    sig = [be.Signal("long", None, 5, "t", entry_price=95, stop_price=90), None, None]
    assert run_with_signals(bars, sig)["trades"] == []


def test_limit_order_expires():
    bars = [tbar(1, 100, 100, 100, 100)] + [tbar(i, 100, 101, 99, 100) for i in range(2, 6)] + [
        tbar(6, 100, 100, 90, 92),     # 第 5 根起触价，但挂单只有效 3 根，早已撤单
    ]
    sig = [be.Signal("long", None, 5, "t", entry_price=95, stop_price=90, expire_bars=3), None, None, None, None, None]
    assert run_with_signals(bars, sig)["trades"] == []


def test_short_limit_order_mirrors_long():
    bars = [
        tbar(1, 100, 100, 100, 100),
        tbar(2, 100, 106, 100, 104),   # 最高 106 >= 105，空单 105 成交
        tbar(3, 104, 111, 104, 110),   # 最高 111 >= 止损 110
    ]
    sig = [be.Signal("short", None, 5, "t", entry_price=105, stop_price=110), None, None]
    t = run_with_signals(bars, sig)["trades"]
    assert t[0]["side"] == "short" and t[0]["entryPrice"] == 105 and t[0]["exitPrice"] == 110
    assert t[0]["profit"] == -50.0


def test_no_new_signal_while_order_pending():
    bars = [tbar(1, 100, 100, 100, 100), tbar(2, 100, 101, 99, 100), tbar(3, 100, 101, 99, 100)]
    sig = [
        be.Signal("long", None, 5, "a", entry_price=95, stop_price=90),
        be.Signal("short", 10, 10, "b"),          # 挂单还在等：这个信号被忽略
        None,
    ]
    assert run_with_signals(bars, sig)["trades"] == []


# ----------------------------------------------------------------------------
# ZigZag 与三波段趋势策略
# ----------------------------------------------------------------------------

SESSION_BREAK = "BREAK"   # path_bars 里的标记：此处插入一个时段间隔（模拟午休 / 日夜盘切换，价格可以跳空）


def path_bars(points, start="2026-10-20 09:00:00"):
    """用一串价格拐点生成逐根 1 分钟 K 线：每两个拐点之间每根走 1 个价位（open/close 连续）。
    points 里的 SESSION_BREAK 后面的下一个价格直接跳空到该价位，并让时间间隔 2 小时（新时段）。"""
    from datetime import datetime, timedelta

    t = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    out = []

    def add(o, h, l, c):
        out.append(bar(t.strftime("%Y-%m-%d %H:%M:%S"), o, h, l, c))

    prev = None
    jump = False
    for p in points:
        if p == SESSION_BREAK:
            jump = True
            continue
        if prev is None or jump:
            if prev is not None:
                t += timedelta(hours=2)
            add(p, p, p, p)
            prev, jump = p, False
            continue
        step = 1 if p > prev else -1
        while prev != p:
            t += timedelta(minutes=1)
            nxt = prev + step
            add(prev, max(prev, nxt), min(prev, nxt), nxt)
            prev = nxt
    return out


# 上升趋势（阈值 15 跳）：L1=100 H1=130 L2=110 H2=150 L3=125 H3=170，之后回落 170->150 确认 H3（回落 20 >= 15）
# 建仓 = L3 + (H3-L3)/3 = 125 + 15 = 140，止损 L3 = 125
UP3 = [100, 130, 110, 150, 125, 170, 150]
# 下降趋势（镜像）：H1=200 L1=170 H2=190 L2=150 H3=175 L3=130，之后反弹 130->150 确认 L3
# 建仓 = H3 - (H3-L3)/3 = 175 - 15 = 160，止损 H3 = 175
DOWN3 = [200, 170, 190, 150, 175, 130, 150]


def test_zigzag_confirms_pivots_with_threshold():
    # 100 -> 130 -> 110 -> 150 -> 125：阈值 15
    bars = path_bars([100, 130, 110, 150, 125])
    pv = be.zigzag_pivots(bars, 15)
    assert [(p["kind"], p["price"]) for p in pv] == [("low", 100), ("high", 130), ("low", 110), ("high", 150)]
    # 确认发生在极值之后（不是极值当根），不使用未来数据
    assert all(p["confirm"] > p["index"] for p in pv)
    # 高低交替
    assert [p["kind"] for p in pv] == ["low", "high", "low", "high"]


def test_zigzag_ignores_moves_below_threshold():
    bars = path_bars([100, 110, 103, 112, 101])    # 全部波动都小于 15
    assert be.zigzag_pivots(bars, 15) == []


def test_trend_swing_long_places_limit_at_one_third_above_low_and_stops_at_low():
    # 3 级抬高后，回踩到 140 成交，随后跌破止损 125
    bars = path_bars(UP3 + [140, 160, 124])
    t = be.run_backtest(bars, "trend_swing", "FU0", lots=1)["trades"]
    assert len(t) == 1
    assert t[0]["side"] == "long" and t[0]["entryPrice"] == 140
    assert t[0]["stopLoss"] == 125 and t[0]["takeProfit"] is None
    assert t[0]["reason"] == "止损" and t[0]["exitPrice"] == 125
    assert t[0]["profit"] == (125 - 140) * 10      # 亏 15 个价位 × 乘数 10 × 1 手


def test_trend_swing_needs_three_levels_not_two():
    # 只有 2 级抬高（L1 H1 L2 H2）：不够，不挂单。这正是之前把“大跌后的小反弹”误当趋势的情形
    bars = path_bars([100, 130, 110, 150, 125, 140, 100])
    assert be.run_backtest(bars, "trend_swing", "FU0", lots=1)["trades"] == []


def test_trend_swing_requires_every_low_and_high_to_rise():
    # L3(105) 低于 L2(110)：低点没有逐级抬高，不是上升趋势
    bars = path_bars([100, 130, 110, 150, 105, 170, 150, 140, 120])
    assert be.run_backtest(bars, "trend_swing", "FU0", lots=1)["trades"] == []
    # H3(145) 低于 H2(150)：高点没有逐级抬高
    bars = path_bars([100, 130, 110, 150, 125, 145, 125, 130, 100])
    assert be.run_backtest(bars, "trend_swing", "FU0", lots=1)["trades"] == []


def test_trend_swing_short_mirrors_long():
    # 3 级降低后，反弹到 160 成交，随后涨破止损 175
    bars = path_bars(DOWN3 + [160, 140, 176])
    t = be.run_backtest(bars, "trend_swing", "FU0", lots=1)["trades"]
    assert len(t) == 1
    assert t[0]["side"] == "short" and t[0]["entryPrice"] == 160
    assert t[0]["stopLoss"] == 175 and t[0]["takeProfit"] is None
    assert t[0]["reason"] == "止损" and t[0]["profit"] == (160 - 175) * 10


def test_trend_swing_keeps_winning_trade_open_without_take_profit():
    # 建仓后一路上涨，没有止盈，直到数据结束才强平
    bars = path_bars(UP3 + [140, 200])
    t = be.run_backtest(bars, "trend_swing", "FU0", lots=1)["trades"]
    assert len(t) == 1 and t[0]["reason"] == "强制平仓" and t[0]["exitPrice"] == 200
    assert t[0]["profit"] == (200 - 140) * 10


def test_trend_swing_big_drop_then_small_bounce_is_not_an_uptrend():
    """复现实测问题：大跌之后的小反弹只有 2 级抬高（L1 H1 L2 H2），旧逻辑会把它当上升趋势做多。
    现在要求 3 级，这种小反弹不开仓。"""
    # 大跌 300->200，然后反弹：L1=200 H1=230 L2=210 H2=250（2 级抬高），回落 250->230 确认 H2
    bars = path_bars([300, 200, 230, 210, 250, 230, 240, 200])
    assert be.run_backtest(bars, "trend_swing", "FU0", lots=1)["trades"] == []


def test_split_sessions_by_time_gap():
    bars = path_bars([100, 103, SESSION_BREAK, 90, 93])
    spans = be.split_sessions(bars)
    assert len(spans) == 2
    assert bars[spans[0][1]]["close"] == 103 and bars[spans[1][0]]["open"] == 90


def test_trend_swing_does_not_connect_pivots_across_sessions():
    # 前 2 级结构在时段 1，第 3 级在时段 2（中间有跳空）：不能跨时段拼成 3 级
    bars = path_bars([100, 130, 110, 150, SESSION_BREAK, 125, 170, 150, 140, 124])
    assert be.run_backtest(bars, "trend_swing", "FU0", lots=1)["trades"] == []


def test_trend_swing_pending_order_does_not_survive_session_end():
    # 信号后本时段还剩几根就收盘，挂单随时段结束撤销；下一时段价格触及 140 也不会成交
    bars = path_bars(UP3 + [SESSION_BREAK, 160, 140, 124])
    assert be.run_backtest(bars, "trend_swing", "FU0", lots=1)["trades"] == []


def test_trend_swing_registered_as_one_minute_strategy():
    sdef = be.STRATEGIES["trend_swing"]
    assert sdef.period == "1" and sdef.category == "趋势"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
