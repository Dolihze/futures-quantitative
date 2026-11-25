"""量化回测引擎单元测试：python -m pytest tests -q（或 python tests/test_backtest_engine.py）。

用手工构造的 K 线验证撮合、止盈止损、盈亏比等统计，期望值都是手算的。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backend.core import backtest_engine as be  # noqa: E402


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


def test_instrument_config_by_contract_code():
    # 合约参数按品种字母取：fu2611 / SHFE.fu2611 / FU0 都是燃料油
    assert be.product_code("fu2611") == "FU" and be.product_code("SHFE.fu2611") == "FU" and be.product_code("FU0") == "FU"
    assert be.get_instrument_config("au2612") == {"tickSize": 0.02, "multiplier": 1000}
    assert be.get_instrument_config("zz9999") == be.DEFAULT_INSTRUMENT   # 目录外品种走默认参数
    for code, cfg in be.INSTRUMENT_CONFIG.items():
        assert cfg["tickSize"] > 0 and cfg["multiplier"] > 0, code
    assert be.contract_name("fu2611") == "燃料油 FU2611" and be.contract_name("SHFE.rb2610") == "螺纹钢 RB2610"
    assert be.contract_name("zz9999") == "ZZ9999"


def _tick_csv(symbol, day_prices):
    """造一份 tick CSV（time 为 YYYYMMDDHHMMSSmmm，volume 为当日累计）。day_prices: [(YYYYMMDD, [(HHMMSS, price, cum_vol), ...])]"""
    rows = ["symbol,name,time,current,volume,money,position"]
    for day, ticks in day_prices:
        for hms, price, cum in ticks:
            rows.append(f"{symbol},测试,{day}{hms}000,{price},{cum},{cum * price * 10},1000")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _with_depth_dir(tmp_path, monkeypatch, files):
    """把 depth_files 指到临时目录并写入 {文件名: bytes}，清掉 K 线缓存。"""
    from backend.services import depth_service, kline_store, tick_store
    monkeypatch.setenv("DEPTH_FILES_DIR", str(tmp_path))
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    tick_store.reset_state()
    depth_service.migrate_legacy()   # 夹具写的是 CSV：同步迁入行情库（回测只读库，不碰遗留 CSV）
    kline_store.clear_cache()
    return kline_store


def test_kline_store_aggregates_ticks_with_end_time_stamps(tmp_path, monkeypatch):
    # 09:00:10 / 09:00:50 在同一根 1 分钟线（标 09:01），09:01:20 在下一根（标 09:02）；5 分钟线都落在 09:05
    csv = _tick_csv("fu2611", [("20261020", [("090010", 100, 10), ("090050", 102, 30), ("090120", 99, 45), ("090430", 101, 60)])])
    ks = _with_depth_dir(tmp_path, monkeypatch, {"fu2611_20261020.csv": csv})
    one = ks.fetch_bars("fu2611", "1")
    assert [b["time"] for b in one] == ["2026-10-20 09:01:00", "2026-10-20 09:02:00", "2026-10-20 09:05:00"]
    first = one[0]
    assert (first["open"], first["high"], first["low"], first["close"]) == (100, 102, 100, 102)
    assert first["volume"] == 30 and one[1]["volume"] == 15 and one[2]["volume"] == 15   # 累计量差分成增量
    five = ks.fetch_bars("SHFE.FU2611", "5")   # 大小写 / 交易所前缀都能匹配
    assert len(five) == 1 and five[0]["time"] == "2026-10-20 09:05:00"
    assert (five[0]["open"], five[0]["high"], five[0]["low"], five[0]["close"]) == (100, 102, 99, 101)
    assert five[0]["volume"] == 60


def test_kline_store_missing_contract_and_bad_period(tmp_path, monkeypatch):
    from backend.errors import ApiError
    ks = _with_depth_dir(tmp_path, monkeypatch, {})
    for args, status in ((("fu2611", "5"), 404), (("fu2611", "7"), 400)):
        try:
            ks.fetch_bars(*args)
        except ApiError as e:
            assert e.status == status
            if status == 404:
                assert "数据库管理" in e.message   # 提示去导入
        else:
            raise AssertionError("应该抛 ApiError")
    assert ks.list_contracts() == []


def test_kline_store_cache_invalidates_when_files_change(tmp_path, monkeypatch):
    day1 = _tick_csv("fu2611", [("20261020", [("090010", 100, 10), ("090120", 101, 20)])])
    ks = _with_depth_dir(tmp_path, monkeypatch, {"fu2611_20261020.csv": day1})
    assert len(ks.fetch_bars("fu2611", "1")) == 2
    # 再导入第二个交易日：同一合约的文件合并成一条时间线，缓存按文件签名自动失效
    day2 = _tick_csv("fu2611", [("20261021", [("090010", 105, 10), ("090120", 106, 20)])])
    (tmp_path / "fu2611_20261021.csv").write_bytes(day2)
    from backend.services import depth_service
    depth_service.migrate_legacy()
    bars = ks.fetch_bars("fu2611", "1")
    assert [b["time"][:10] for b in bars] == ["2026-10-20"] * 2 + ["2026-10-21"] * 2
    c = ks.list_contracts()
    assert len(c) == 1 and c[0]["symbol"] == "fu2611" and c[0]["dayCount"] == 2


def test_backtest_api_uses_local_library_contracts(tmp_path, monkeypatch):
    """回测接口按 symbol 取本地库 K 线：symbol 必填；未导入的合约 404 并提示导入；每个合约用自己品种的乘数结算。"""
    from backend import app as backend
    ks = _with_depth_dir(tmp_path, monkeypatch, {
        "fu2611_20261020.csv": _tick_csv("fu2611", [("20261020", [("090010", 100, 10), ("090120", 101, 20), ("090230", 99, 30)])]),
        "au2612_20261020.csv": _tick_csv("au2612", [("20261020", [("090010", 500, 10), ("090120", 501, 20)])]),
    })
    client = backend.app.test_client()

    cs = client.get("/api/backtest/contracts").get_json()
    assert cs["success"] and [c["symbol"] for c in cs["data"]] == ["au2612", "fu2611"] and cs["default"] == "au2612"
    assert {c["symbol"]: c["label"] for c in cs["data"]} == {"au2612": "沪金 AU2612", "fu2611": "燃料油 FU2611"}

    k = client.get("/api/backtest/kline?symbol=fu2611&period=1&days=30").get_json()
    assert k["success"] and k["symbol"] == "fu2611" and k["symbolName"] == "燃料油 FU2611" and k["count"] == 3
    r = client.get("/api/backtest/run?strategy=reversal&symbol=au2612&days=30").get_json()
    assert r["success"] and r["symbol"] == "au2612" and r["symbolName"] == "沪金 AU2612" and "product" not in r
    o = client.get("/api/backtest/overview?symbol=fu2611&days=30").get_json()
    assert o["success"] and o["symbol"] == "fu2611" and o["data"]

    assert client.get("/api/backtest/overview?days=30").status_code == 400            # 没选合约
    assert client.get("/api/backtest/kline?symbol=fu2611&period=7").status_code == 400
    for url in ("/api/backtest/overview?symbol=rb2610", "/api/backtest/kline?symbol=rb2610&period=5",
                "/api/backtest/run?strategy=reversal&symbol=rb2610"):
        miss = client.get(url)
        assert miss.status_code == 404 and "数据库管理" in miss.get_json()["message"], url


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


def test_api_returns_coverage_so_60_and_90_are_not_silently_identical(monkeypatch):
    from backend import app as backend
    from backend.services import backtest_service

    # 本地库只有约 3 周数据：构造 21 天数据，每天 1 根
    bars = [bar(f"2026-10-{d:02d} 09:05:00", 100, 100, 100, 100) for d in range(1, 22)]
    monkeypatch.setattr(backtest_service, "fetch_backtest_bars", lambda symbol, period: bars)
    client = backend.app.test_client()
    o30 = client.get("/api/backtest/overview?symbol=fu2611&days=30").get_json()
    o90 = client.get("/api/backtest/overview?symbol=fu2611&days=90").get_json()
    r90 = client.get("/api/backtest/run?strategy=reversal&symbol=fu2611&days=90").get_json()
    r7 = client.get("/api/backtest/run?strategy=reversal&symbol=fu2611&days=7").get_json()
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
