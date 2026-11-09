"""交易复盘 API 测试（Flask test client，真实 multipart 上传）。

运行：python tests/test_review_api.py
"""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backend  # noqa: E402
from test_review import HEADER_A, ROWS_A, make_xlsx  # noqa: E402

client = backend.app.test_client()


def upload(content: bytes, name: str):
    return client.post("/api/review/upload", data={"file": (io.BytesIO(content), name)},
                       content_type="multipart/form-data")


def test_upload_and_curve_flow():
    r = upload(make_xlsx(ROWS_A, HEADER_A, title_rows=2), "records.xlsx")
    assert r.status_code == 200
    j = r.get_json()
    assert j["success"] and j["products"] == ["FU", "RB"]
    assert j["start"].startswith("2026-10-20") and j["end"].startswith("2026-10-22")
    assert j["tradeCount"] == 6
    rid = j["reviewId"]

    # 全部品种，不扣手续费
    c = client.get(f"/api/review/curve?reviewId={rid}&fee=0").get_json()
    # 文件有 6 行成交（3 开 + 3 平），曲线上只统计“平”：3 笔
    assert c["success"] and c["stats"]["totalPnl"] == 100.0 and c["trades"] == 3
    # 扣手续费
    assert client.get(f"/api/review/curve?reviewId={rid}").get_json()["stats"]["totalPnl"] == 79.0
    # 品种 + 时间范围
    c = client.get(f"/api/review/curve?reviewId={rid}&products=FU&start=2026-10-20&end=2026-10-20&fee=0").get_json()
    assert c["stats"]["totalPnl"] == 400.0 and c["trades"] == 1      # 当天 FU 一开一平，只算平仓这 1 笔
    # 多个品种
    c = client.get(f"/api/review/curve?reviewId={rid}&products=FU,RB&fee=0").get_json()
    assert c["stats"]["totalPnl"] == 100.0
    # 筛选后没有数据：不是错误，返回空曲线
    c = client.get(f"/api/review/curve?reviewId={rid}&start=2027-01-01").get_json()
    assert c["success"] and c["points"] == [] and c["trades"] == 0


def test_detail_sheet_upload_merge_fee_and_flags():
    from test_review import GROSS_D, make_detail_sheet, ROWS_D
    j = upload(make_detail_sheet(ROWS_D), "settlement.xlsx").get_json()
    assert j["success"] and j["products"] == ["FU", "IF", "RB"]
    assert j["tradeCount"] == 13, "tradeCount 是文件里的成交行数（开+平）；曲线上的笔数以 curve 接口为准"
    assert j["hasFee"] is True and "dateOnly" not in j
    assert any("成交明细" in w for w in j["warnings"])
    rid = j["reviewId"]
    gross = client.get(f"/api/review/curve?reviewId={rid}&fee=0").get_json()
    net = client.get(f"/api/review/curve?reviewId={rid}&fee=1").get_json()
    assert gross["trades"] == net["trades"] == 5, "13 行成交 → 只统计平 → 同一时刻同合约同方向合并 → 5 笔"
    assert gross["stats"]["totalPnl"] == GROSS_D == 3810.0
    assert net["stats"]["totalPnl"] == 3708.0, "扣除的是开+平全部手续费 102.0"
    assert net["stats"]["totalFee"] == 102.0
    first = net["details"][1]
    assert first["lots"] == 6 and first["fills"] == 3 and first["time"] == "2026-10-21 21:30:05"
    # 横坐标：固定四个交易时段，夜盘排最前；xs 与 points 一一对应
    assert len(net["xs"]) == len(net["points"]) == 6 and net["xs"] == sorted(net["xs"])
    assert [s["name"] for s in net["segments"]] == ["夜盘", "早盘（上）", "早盘（下）", "午盘"]
    assert [round(s["x1"] - s["x0"]) for s in net["segments"]] == [120, 75, 60, 90], "段宽 = 真实时长（分钟）"
    assert net["segments"][0]["start"] == "2026-10-21 21:00:00" and net["segments"][3]["end"] == "2026-10-22 15:00:00"
    # 休息时间不画：整条轴 = 左边留白 + 345 分钟的交易时间 + 3 个段间隔，远小于真实跨度（约 18 小时）。
    # 精确值，不用宽松上限：之前一个按“第一个点”平移的 bug（夜盘起点跑到负坐标）就是被宽松上限漏过去的
    import review
    assert net["segments"][0]["x0"] == review.AXIS_PAD, "整条轴从 AXIS_PAD 开始，不能是负数"
    assert net["segments"][-1]["x1"] == review.AXIS_PAD + 345 + 3 * review.SESSION_GAP_WIDTH
    # 第一笔（21:30:05）在夜盘内，比夜盘开盘晚 30.0833 分钟；起点在它左边 START_POINT_OFFSET
    assert abs(net["xs"][1] - (review.AXIS_PAD + 30.0833)) < 0.01
    assert abs(net["xs"][1] - net["xs"][0] - review.START_POINT_OFFSET) < 1e-6
    # 日期时间格式在 JSON 里是字符串，前端的时间轴据此画图
    assert all(isinstance(p[0], str) for p in net["points"])


def test_trade_detail_upload_reports_fee_and_time_flags():
    j = upload(make_xlsx(ROWS_A, HEADER_A, title_rows=2), "records.xlsx").get_json()
    assert j["hasFee"] is True and "dateOnly" not in j


def test_upload_of_date_only_file_returns_readable_400():
    import datetime as dt
    from test_review import _row, make_detail_sheet
    rows = [_row(1, "FU2611", dt.time(0, 0, 0), "买", "开", 2900, 1, 2.5, None, "2026-10-21"),
            _row(2, "FU2611", dt.time(0, 0, 0), "卖", "平", 2910, 1, 2.5, 100.0, "2026-10-21")]
    r = upload(make_detail_sheet(rows), "dateonly.xlsx")
    j = r.get_json()
    assert r.status_code == 400 and j["success"] is False
    assert "只有日期" in j["message"] and "成交明细" in j["message"]


def test_upload_validation_errors():
    assert client.post("/api/review/upload").status_code == 400                       # 没有文件
    r = upload(b"hello", "notes.txt")
    assert r.status_code == 400 and "仅支持" in r.get_json()["message"]               # 扩展名不对
    r = upload(b"this is not an excel file", "fake.xlsx")
    assert r.status_code == 400 and "无法读取" in r.get_json()["message"]              # 内容不是 Excel
    r = upload(make_xlsx([[1, 2]], ["foo", "bar"]), "wrong.xlsx")
    assert r.status_code == 400 and "没有识别到必需的列" in r.get_json()["message"]    # 列名不认识


def test_curve_errors():
    r = client.get("/api/review/curve?reviewId=nope")
    j = r.get_json()
    assert r.status_code == 404 and j["expired"] is True and "重新上传" in j["message"]
    rid = upload(make_xlsx(ROWS_A, HEADER_A, title_rows=2), "a.xlsx").get_json()["reviewId"]
    r = client.get(f"/api/review/curve?reviewId={rid}&start=not-a-date")
    assert r.status_code == 400 and r.get_json()["success"] is False                    # 日期格式错误不应 500


def test_cache_is_bounded():
    data = make_xlsx(ROWS_A, HEADER_A, title_rows=2)
    first = upload(data, "a.xlsx").get_json()["reviewId"]
    for _ in range(backend.REVIEW_CACHE_MAX):
        upload(data, "a.xlsx")
    assert len(backend.REVIEW_CACHE) == backend.REVIEW_CACHE_MAX
    assert client.get(f"/api/review/curve?reviewId={first}").status_code == 404        # 最早的已被淘汰


def test_too_large_upload():
    r = client.post("/api/review/upload",
                    data={"file": (io.BytesIO(b"0" * (21 * 1024 * 1024)), "big.xlsx")},
                    content_type="multipart/form-data")
    assert r.status_code == 413 and "文件过大" in r.get_json()["message"]


def test_day_trades_pairs_open_and_close_fifo_and_splits_by_day():
    from test_review import GROSS_D, make_detail_sheet, ROWS_D
    rid = upload(make_detail_sheet(ROWS_D), "settlement.xlsx").get_json()["reviewId"]
    j = client.get(f"/api/review/day-trades?reviewId={rid}&day=2026-10-22").get_json()
    assert j["success"] and j["day"] == "2026-10-22" and j["days"] == ["2026-10-22"]
    by = {s["symbol"]: s["trades"] for s in j["symbols"]}
    assert sorted(by) == ["FU2611", "IF2611", "rb2610"]

    # FU：夜盘买开 6 手，同刻分 3 笔平（1+2+3 手，价格 2910/2912/2914）→ 开仓时间、平仓时间相同，合并成 1 笔：
    # 6 手，平仓价取按手数加权的均价 (2910*1+2912*2+2914*3)/6 = 2912.67，盈亏相加 100+240+420 = 760
    fu = by["FU2611"]
    big = [t for t in fu if t["openTime"] == "2026-10-21 21:25:05"]
    assert len(big) == 1 and big[0]["lots"] == 6 and big[0]["fills"] == 3
    assert big[0]["side"] == "多" and big[0]["openPrice"] == 2900 and big[0]["closePrice"] == 2912.67
    assert big[0]["pnl"] == 760.0, "有平仓盈亏列：按文件里的值，合并后相加，和资金曲线合并后的那一笔一致"
    # 次日买开 1 手 → 同刻卖平：盈亏 -50
    assert any(t["openTime"] == "2026-10-22 09:01:00" and t["closeTime"] == "2026-10-22 09:15:00" and t["pnl"] == -50.0
               for t in fu)
    # rb 夜盘卖开 → 买平，是空单
    rb = by["rb2610"]
    short = next(t for t in rb if t["side"] == "空")
    assert short["openTime"] == "2026-10-21 21:05:00" and short["closeTime"] == "2026-10-21 22:10:30" and short["pnl"] == 200.0
    # 所有已平仓交易的盈亏之和 = 资金曲线的毛盈亏
    closed = [t for s in j["symbols"] for t in s["trades"] if t["closeTime"]]
    assert round(sum(t["pnl"] for t in closed), 2) == GROSS_D
    # 夜盘（真实 10-21）属于 10-22 交易日，开仓、平仓都算在当天
    assert all(t["openInDay"] and t["closeInDay"] for t in closed)
    # 品种筛选；没有成交的交易日返回空列表而不是报错
    only = client.get(f"/api/review/day-trades?reviewId={rid}&day=2026-10-22&products=IF").get_json()
    assert [s["symbol"] for s in only["symbols"]] == ["IF2611"]
    assert client.get(f"/api/review/day-trades?reviewId={rid}&day=2026-10-23").get_json()["symbols"] == []
    assert client.get(f"/api/review/day-trades?reviewId={rid}").status_code == 400
    assert client.get("/api/review/day-trades?reviewId=nope&day=2026-10-22").status_code == 404


def test_day_trades_merges_same_time_on_both_ends_with_weighted_prices():
    # 同一时刻分两笔开仓（价格不同）、之后同一时刻一笔平掉：先进先出会拆成两条，开仓时间和平仓时间都相同 → 合并
    # 另一组开仓时间不同、平仓时间相同 → 不能合并（开仓点在不同的 K 线上）
    from test_review import make_xlsx
    rows = [
        ["2026-10-21 09:00:00", "FU2611", "买", "开", 2900, 1, 1.0],
        ["2026-10-21 09:00:00", "FU2611", "买", "开", 2910, 3, 1.0],
        ["2026-10-21 09:30:00", "FU2611", "卖", "平", 2920, 4, 1.0],
        ["2026-10-21 10:00:00", "FU2611", "买", "开", 2900, 1, 1.0],
        ["2026-10-21 10:05:00", "FU2611", "买", "开", 2900, 1, 1.0],
        ["2026-10-21 10:30:00", "FU2611", "卖", "平", 2910, 2, 1.0],
    ]
    header = ["成交时间", "合约", "买卖", "开平", "成交价", "手数", "手续费"]
    rid = upload(make_xlsx(rows, header), "r.xlsx").get_json()["reviewId"]
    t = client.get(f"/api/review/day-trades?reviewId={rid}&day=2026-10-21").get_json()["symbols"][0]["trades"]
    # 没有“平仓盈亏”列：按价差×乘数(10)×手数计算
    a = next(x for x in t if x["openTime"] == "2026-10-21 09:00:00")
    assert a["lots"] == 4 and a["fills"] == 2
    assert a["openPrice"] == 2907.5, "(2900*1 + 2910*3) / 4"
    assert a["closePrice"] == 2920 and a["pnl"] == (2920 - 2900) * 1 * 10 + (2920 - 2910) * 3 * 10 == 500.0
    others = [x for x in t if x["openTime"] != "2026-10-21 09:00:00"]
    assert [x["openTime"][11:] for x in others] == ["10:00:00", "10:05:00"], "开仓时间不同，各自一条"
    assert all(x["lots"] == 1 and x["fills"] == 1 for x in others)
    # 合并只改变条数，不改变总手数和总盈亏
    assert sum(x["lots"] for x in t) == 6 and round(sum(x["pnl"] for x in t), 2) == 500.0 + 100.0 + 100.0


def test_day_trades_overnight_position_and_pnl_computed_without_file_pnl():
    # 没有“平仓盈亏”列时按价差×乘数×手数计算；隔夜持仓：开仓在前一个交易日，平仓在后一个
    from test_review import HEADER_A, make_xlsx
    rows = [
        ["2026-10-20 10:00:00", "FU2611", "买", "开", 2900, 2, 1.0],
        ["2026-10-21 09:30:00", "FU2611", "卖", "平", 2910, 1, 1.0],
        ["2026-10-21 10:00:00", "FU2611", "卖", "平", 2890, 1, 1.0],
    ]
    header = ["成交时间", "合约", "买卖", "开平", "成交价", "手数", "手续费"]
    rid = upload(make_xlsx(rows, header), "r.xlsx").get_json()["reviewId"]
    j = client.get(f"/api/review/day-trades?reviewId={rid}&day=2026-10-21").get_json()
    t = j["symbols"][0]["trades"]
    assert [x["pnl"] for x in t] == [100.0, -100.0]          # (2910-2900)*1*10，(2890-2900)*1*10
    assert all(x["openTime"] == "2026-10-20 10:00:00" and not x["openInDay"] and x["closeInDay"] for x in t)
    assert j["days"] == ["2026-10-20", "2026-10-21"]
    # 开仓那一天也能看到这两笔：开仓在当天，平仓在之后的交易日
    prev = client.get(f"/api/review/day-trades?reviewId={rid}&day=2026-10-20").get_json()
    assert len(prev["symbols"][0]["trades"]) == 2
    assert all(x["openInDay"] and not x["closeInDay"] for x in prev["symbols"][0]["trades"])


def _fake_bars(start, n, freq):
    import pandas as pd
    t = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame({"datetime": t, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 3, "hold": 9})


def _with_fake_sina(by_period, calls=None):
    """把 akshare 的新浪分钟线接口换成离线假数据：by_period 是 {周期: DataFrame 或 异常}。"""
    import akshare as ak
    orig = ak.futures_zh_minute_sina

    def fake(symbol, period):
        if calls is not None:
            calls.append(period)
        v = by_period.get(period)
        if isinstance(v, Exception):
            raise v
        return v if v is not None else _fake_bars("2000-01-01", 0, "1min")
    ak.futures_zh_minute_sina = fake
    return lambda: setattr(ak, "futures_zh_minute_sina", orig)


def test_day_kline_uses_finest_period_that_fully_covers_the_day():
    import pandas as pd
    # 1 分钟线从 10-21 夜盘 21:00 开始（该交易日 10-22 的第一根就是整份数据的第一根 → 开头被截断，不完整）
    # 5 分钟线更早开始 → 完整，用它；交易日口径：夜盘 21:00 属于 10-22
    one = _fake_bars("2026-10-21 21:00", 6, "1min")
    five = pd.concat([_fake_bars("2026-10-20 09:00", 3, "5min"), _fake_bars("2026-10-21 21:00", 3, "5min"),
                      _fake_bars("2026-10-22 09:00", 3, "5min")], ignore_index=True)
    calls = []
    restore = _with_fake_sina({"1": one, "5": five}, calls)
    try:
        j = client.get("/api/review/day-kline?symbol=SHFE.FU2611&day=2026-10-22").get_json()
    finally:
        restore()
    assert j["success"] and j["available"] and j["symbol"] == "FU2611"
    assert j["period"] == 5 and j["partial"] is False and j["count"] == 6, "1 分钟被截断，降级到完整的 5 分钟"
    assert j["data"][0]["time"] == "2026-10-21 21:00:00" and j["data"][-1]["time"] == "2026-10-22 09:10:00"
    assert calls == ["1", "5"], "找到完整的就停，不再请求更长的周期"


def test_day_kline_one_minute_when_complete_and_partial_when_nothing_is_complete():
    import pandas as pd
    # 1 分钟完整（这个交易日前面还有更早的数据）→ 直接用 1 分钟，只请求一次
    one = pd.concat([_fake_bars("2026-10-21 09:00", 3, "1min"), _fake_bars("2026-10-21 21:00", 3, "1min")],
                    ignore_index=True)
    calls = []
    restore = _with_fake_sina({"1": one}, calls)
    try:
        j = client.get("/api/review/day-kline?symbol=FU2611&day=2026-10-22").get_json()
    finally:
        restore()
    assert j["period"] == 1 and j["partial"] is False and calls == ["1"]

    # 每个周期里这一天都是最早的数据（都被截断）→ 取最细的 1 分钟，标 partial
    same = _fake_bars("2026-10-21 21:00", 3, "1min")
    restore = _with_fake_sina({p: same for p in ("1", "5", "15", "30", "60")})
    try:
        j = client.get("/api/review/day-kline?symbol=FU2611&day=2026-10-22").get_json()
    finally:
        restore()
    assert j["available"] and j["period"] == 1 and j["partial"] is True


def test_day_kline_unavailable_lists_ranges_and_handles_errors():
    # 所有周期都没有这一天：不是错误，available=False，message 里写清各周期能取到的范围
    bars = {p: _fake_bars("2026-11-04 09:00", 3, "1min") for p in ("1", "5", "15", "30", "60")}
    restore = _with_fake_sina(bars)
    try:
        j = client.get("/api/review/day-kline?symbol=FU2611&day=2026-10-01").get_json()
    finally:
        restore()
    assert j["success"] and j["available"] is False and "2026-10-01" in j["message"]
    assert "1分钟 11-04" in j["message"] and "60分钟" in j["message"]

    # 个别周期出错（网络抖动）不影响用其它周期；全部出错才是 502
    five = _fake_bars("2026-10-20 09:00", 2, "5min")
    five = __import__("pandas").concat([five, _fake_bars("2026-10-22 09:00", 2, "5min")], ignore_index=True)
    restore = _with_fake_sina({"1": RuntimeError("boom"), "5": five})
    try:
        j = client.get("/api/review/day-kline?symbol=FU2611&day=2026-10-22").get_json()
    finally:
        restore()
    assert j["available"] and j["period"] == 5
    restore = _with_fake_sina({p: RuntimeError("boom") for p in ("1", "5", "15", "30", "60")})
    try:
        r = client.get("/api/review/day-kline?symbol=FU2611&day=2026-10-22")
    finally:
        restore()
    assert r.status_code == 502 and "boom" in r.get_json()["message"]
    assert client.get("/api/review/day-kline?symbol=FU2611").status_code == 400


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS ", t.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL ", t.__name__, "->", repr(e))
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
