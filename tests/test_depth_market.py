"""深度行情测试：tick CSV 解析、K 线聚合、历史盘口、上传接口。

运行：python tests/test_depth_market.py（或 python -m pytest tests/test_depth_market.py -q）
"""
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 上传会保存到 depth_files：测试一律指向临时目录，不能写进真实项目文件夹
_TMP_DIR = tempfile.mkdtemp(prefix="depth_files_test_")
os.environ["DEPTH_FILES_DIR"] = _TMP_DIR

from backend.core import depth_market as dm  # noqa: E402
from backend import app as backend  # noqa: E402
from backend.services import depth_service  # noqa: E402

client = backend.app.test_client()

HEADER = "symbol,code,name,time,open,current,high,low,volume,money,position,a1_v,a1_p,b1_v,b1_p"
ROWS = [
    # 夜盘 21:00 归属下一个交易日 2026-06-01（5/29 是周五）
    "A2607.XDCE,a2607,豆一2607,20260529210000500,4720,4722,4725,4720,713,33660570,291801,28,4725,107,4722",
    "A2607.XDCE,a2607,豆一2607,20260529210001000,4720,4724,4725,4720,720,33693000,291805,20,4725,50,4724",
    "A2607.XDCE,a2607,豆一2607,20260529210105000,4720,4720,4725,4720,730,33741000,291800,20,4721,50,4720",
    # 日盘开盘：累计量从头开始
    "A2607.XDCE,a2607,豆一2607,20260601090000000,4721,4721,4721,4721,10,470000,291800,5,4722,6,4721",
    "A2607.XDCE,a2607,豆一2607,20260601090030000,4721,4723,4723,4721,25,1180000,291802,5,4723,6,4722",
]


def csv_bytes(rows=ROWS, header=HEADER):
    return ("\n".join([header] + rows)).encode("utf-8")


def test_parse_basic():
    td = dm.parse(csv_bytes(), "a.csv")
    assert td.count == 5
    assert td.symbol == "A2607.XDCE" and td.name == "豆一2607"
    assert td.levels == 1
    assert td.days == ["2026-06-01"]
    # 累计 -> 增量：713(夜盘首笔)、7、10；日盘 10 与夜盘属同一交易日，累计 25 > 10 之前的 730？
    # 夜盘 730 -> 日盘 10 视为回退重置，增量取当前值 10；之后 25 - 10 = 15
    assert list(td.vol) == [713, 7, 10, 10, 15]


def test_parse_gbk_and_aliases():
    text = "时间,最新价,成交量\n20260601090000000,100,5\n20260601090001000,101,9\n"
    td = dm.parse(text.encode("gbk"), "x.csv")
    assert td.count == 2 and td.levels == 0
    assert list(td.vol) == [5, 4]
    assert any("盘口" in w for w in td.warnings)


def test_parse_multi_levels():
    cols = ",".join(f"a{n}_p,a{n}_v,b{n}_p,b{n}_v" for n in range(1, 6))
    vals = ",".join(f"{100 + n},{n},{99 - n},{n * 2}" for n in range(0, 5))
    text = f"time,current,volume,{cols}\n20260601090000000,100,1,{vals}\n"
    td = dm.parse(text.encode(), "x.csv")
    assert td.levels == 5
    book = dm.book_at(td, index=0)
    assert [a["price"] for a in book["asks"]] == [100, 101, 102, 103, 104]
    assert [b["volume"] for b in book["bids"]] == [0, 2, 4, 6, 8]


def test_parse_errors():
    for bad in (b"", b"a,b\n1,2\n"):
        try:
            dm.parse(bad, "x.csv")
        except dm.DepthParseError:
            continue
        raise AssertionError("应抛 DepthParseError")


def test_kline_1m_and_daily():
    td = dm.parse(csv_bytes(), "a.csv")
    bars = dm.build_kline(td, 1)["bars"]
    assert [b["time"] for b in bars] == ["2026-05-29 21:00", "2026-05-29 21:01", "2026-06-01 09:00"]
    b0 = bars[0]
    assert (b0["open"], b0["high"], b0["low"], b0["close"], b0["volume"]) == (4722, 4724, 4722, 4724, 720)
    assert b0["ticks"] == 2 and b0["ti0"] == 0 and b0["ti1"] == 1

    daily = dm.build_kline(td, 1440)["bars"]
    assert len(daily) == 1
    d = daily[0]
    assert (d["open"], d["high"], d["low"], d["close"]) == (4722, 4724, 4720, 4723)
    assert d["volume"] == 755


def test_kline_5m_alignment_and_day_filter():
    td = dm.parse(csv_bytes(), "a.csv")
    bars = dm.build_kline(td, 5, "2026-06-01")["bars"]
    assert [b["time"] for b in bars] == ["2026-05-29 21:00", "2026-06-01 09:00"]
    assert dm.build_kline(td, 1, "2030-01-01")["bars"] == []


def test_book_lookup():
    td = dm.parse(csv_bytes(), "a.csv")
    ts2 = int(td.ts[2])
    b = dm.book_at(td, ts=ts2 + 10)          # 晚于第 3 笔、早于第 4 笔 -> 取第 3 笔
    assert b["index"] == 2 and b["asks"][0]["price"] == 4721 and b["bids"][0]["price"] == 4720
    assert dm.book_at(td, ts=0)["index"] == 0          # 早于首笔取首笔
    assert dm.book_at(td, ts=10 ** 15)["index"] == 4   # 晚于末笔取末笔
    assert len(dm.ticks_range(td, 3, 100)) == 2


# ---------------------------------------------------------------------------
# 新格式：InstrumentID, TradingTime(只到分钟、不补零), BS, LastPrice, Bid/Ask 1 档, Volume 累计, Turnover 科学计数
# ---------------------------------------------------------------------------
HEADER_B = "InstrumentID,TradingTime,BS,LastPrice,BidPrice1,BidVolume1,AskPrice1,AskVolume1,Volume,Turnover,OpenInterest,Open,High,Low"
ROWS_B = [
    "a2611,2026-9-17 8:59,多平,5033,5033,25,5035,2,71845,3.623E+09,333386,5046,5058,5028",
    "a2611,2026-9-17 8:59,空开,5033,5032,11,5033,30,71874,3.624E+09,333410,5046,5058,5028",
    "a2611,2026-9-17 9:00,空开,5031,5029,30,5031,11,71953,3.628E+09,333435,5046,5058,5028",
    "a2611,2026-9-17 9:00,空开,5029,5028,232,5029,30,72020,3.632E+09,333462,5046,5058,5028",
    "a2611,2026-9-17 9:00,空开,5028,5027,153,5028,8,72153,3.639E+09,333537,5046,5058,5027",
    "a2611,2026-9-17 9:00,多开,5028,5027,91,5029,41,72211,3.641E+09,333538,5046,5058,5027",
    "a2611,2026-9-17 9:00,空开,5027,5027,64,5028,1,72215,3.642E+09,333539,5046,5058,5027",
    "a2611,2026-9-17 9:00,多平,5025,5025,98,5026,11,72298,3.646E+09,333523,5046,5058,5025",
    "a2611,2026-9-17 9:00,空开,5025,5024,158,5026,25,72403,3.651E+09,333549,5046,5058,5025",
    "a2611,2026-9-17 9:01,多开,5026,5025,20,5026,9,72420,3.652E+09,333560,5046,5058,5025",
]


def test_new_format_parse():
    td = dm.parse(csv_bytes(ROWS_B, HEADER_B), "a2611.csv")
    assert td.count == 10 and td.symbol == "a2611" and td.levels == 1
    assert td.days == ["2026-09-17"]
    # 首笔累计 71845 是文件之前的成交，不能算进首根 K 线：增量记 0
    assert list(td.vol) == [0, 29, 79, 67, 133, 58, 4, 83, 105, 17]
    assert not any("不是从开盘开始" in w for w in td.warnings)   # 只静默处理，不再提示用户
    # Turnover 科学计数法被识别
    assert td.money.sum() > 0
    # 不补零的 '2026-9-17 8:59' 解析正确
    assert dm.fmt_ts(td.ts[0]) == "2026-09-17 08:59:00"


def test_new_format_kline_1m():
    td = dm.parse(csv_bytes(ROWS_B, HEADER_B), "a2611.csv")
    bars = dm.build_kline(td, 1)["bars"]
    assert [b["time"] for b in bars] == ["2026-09-17 08:59", "2026-09-17 09:00", "2026-09-17 09:01"]
    b0, b1, b2 = bars
    # 同一分钟的多笔 tick 时间戳相同，靠文件行顺序取开 / 收
    assert (b0["open"], b0["high"], b0["low"], b0["close"], b0["volume"]) == (5033, 5033, 5033, 5033, 29)
    assert (b1["open"], b1["high"], b1["low"], b1["close"]) == (5031, 5031, 5025, 5025)
    assert b1["volume"] == 79 + 67 + 133 + 58 + 4 + 83 + 105 and b1["ticks"] == 7
    assert b1["ti0"] == 2 and b1["ti1"] == 8
    assert b1["position"] == 333549
    # 各类成交性质手数统计
    assert b1["bs"] == {"空开": 79 + 67 + 133 + 4 + 105, "多开": 58, "多平": 83}
    assert b2["bs"] == {"多开": 17}


def test_new_format_book_by_index():
    td = dm.parse(csv_bytes(ROWS_B, HEADER_B), "a2611.csv")
    # 同一分钟时间戳相同：必须按序号取，不能按时间戳（时间戳只会命中该分钟最后一笔）
    b = dm.book_at(td, index=3)
    assert b["price"] == 5029 and b["bids"][0]["price"] == 5028 and b["bids"][0]["volume"] == 232
    assert b["asks"][0]["price"] == 5029 and b["asks"][0]["volume"] == 30 and b["bs"] == "空开"
    # 序号保持文件顺序：同一分钟内第 3、4 笔的盘口各不相同
    assert dm.book_at(td, index=2)["bids"][0]["volume"] == 30


def test_mixed_time_formats_and_bs_codes():
    text = ("time,last,bs,volume\n"
            "2026-9-17 9:00,100,BO,5\n"
            "2026-9-17 9:00:30,101,SC,9\n"
            "2026/9/17 9:01:00.500,102,双开,12\n"
            "20260917090200000,103,xx,15\n")
    td = dm.parse(text.encode(), "x.csv")
    assert td.count == 4, td.warnings
    assert list(td.bs) == ["多开", "空平", "双开", ""]
    assert [dm.fmt_ts(x, True)[11:] for x in td.ts] == ["09:00:00.000", "09:00:30.000", "09:01:00.500", "09:02:00.000"]


def test_footprint_levels_and_side():
    td = dm.parse(csv_bytes(ROWS_B, HEADER_B), "a2611.csv")
    fp = dm.build_footprint(td, 1)
    assert [b["time"] for b in fp["bars"]] == ["2026-09-17 08:59", "2026-09-17 09:00", "2026-09-17 09:01"]
    # 价位成交量之和 == K 线成交量（含中性），不能丢量
    for b in fp["bars"]:
        total = sum((lv["buy"] or 0) + (lv["sell"] or 0) + (lv["neutral"] or 0) for lv in b["levels"])
        assert total == b["volume"], (b["time"], total, b["volume"])

    lv = {x["price"]: x for x in fp["bars"][1]["levels"]}
    # 价位从低到高
    assert [x["price"] for x in fp["bars"][1]["levels"]] == sorted(lv)
    # 9:00：5031 空开 79（卖方主动）；5029 空开 67；5028 空开 133 + 多开 58；5027 空开 4；5025 多平 83 + 空开 105
    assert lv[5031]["sell"] == 79 and lv[5031]["buy"] == 0
    assert lv[5028]["sell"] == 133 and lv[5028]["buy"] == 58
    assert lv[5025]["sell"] == 83 + 105          # 多平 = 卖出平多，属于卖方主动
    # 08:59：首笔增量 0（盘中截取），第二笔空开 29
    assert [(x["price"], x["sell"]) for x in fp["bars"][0]["levels"]] == [(5033, 29)]
    # 9:01 多开 17 -> 买方主动
    assert fp["bars"][2]["levels"][0]["buy"] == 17
    assert fp["tickSize"] == 1


def test_footprint_big_orders_threshold():
    td = dm.parse(csv_bytes(ROWS_B, HEADER_B), "a2611.csv")
    # 默认 100 手：只有 133 和 105 两笔
    big = dm.build_footprint(td, 1)["bigOrders"]
    assert [(x["volume"], x["price"], x["side"], x["bar"]) for x in big] == [(133, 5028, -1, 1), (105, 5025, -1, 1)]
    assert big[0]["index"] == 4 and big[0]["bs"] == "空开"
    # 调低到 60：多出 79 和 67 和 83
    assert [x["volume"] for x in dm.build_footprint(td, 1, big_order=60)["bigOrders"]] == [79, 67, 133, 83, 105]
    # 调高到 1000：没有
    assert dm.build_footprint(td, 1, big_order=1000)["bigOrders"] == []
    # 阈值不影响价位成交量
    a = dm.build_footprint(td, 1, big_order=10)["bars"]
    b = dm.build_footprint(td, 1, big_order=500)["bars"]
    assert a == b


def test_footprint_5m_and_daily_consistent_with_kline():
    td = dm.parse(csv_bytes(ROWS_B, HEADER_B), "a2611.csv")
    for period in (1, 5, 1440):
        fp = dm.build_footprint(td, period)
        kl = dm.build_kline(td, period)
        assert len(fp["bars"]) == len(kl["bars"])
        for f, k in zip(fp["bars"], kl["bars"]):
            assert (f["open"], f["high"], f["low"], f["close"], f["volume"]) == (k["open"], k["high"], k["low"], k["close"], k["volume"])
            assert sum((x["buy"] or 0) + (x["sell"] or 0) + (x["neutral"] or 0) for x in f["levels"]) == f["volume"]
    # 5 分钟线把 08:59 和 09:00 分到两根（08:55 桶 / 09:00 桶）
    assert [b["time"] for b in dm.build_footprint(td, 5)["bars"]] == ["2026-09-17 08:55", "2026-09-17 09:00"]


def test_footprint_neutral_and_requires_bs():
    text = ("time,last,bs,volume\n"
            "2026-9-17 9:00,100,多开,10\n2026-9-17 9:00,100,双开,25\n2026-9-17 9:00,101,xx,40\n")
    td = dm.parse(text.encode(), "x.csv")
    lv = {x["price"]: x for x in dm.build_footprint(td, 1)["bars"][0]["levels"]}
    assert lv[100]["buy"] == 10 and lv[100]["neutral"] == 15 and lv[101]["neutral"] == 15
    # 没有 BS 列
    td2 = dm.parse(csv_bytes(), "a.csv")
    try:
        dm.build_footprint(td2, 1)
    except ValueError as e:
        assert "BS" in str(e)
    else:
        raise AssertionError("没有 BS 列应抛 ValueError")


def test_footprint_api():
    r = _upload(csv_bytes(ROWS_B, HEADER_B), "fp.csv")
    did = r.get_json()["depthId"]
    j = client.get(f"/api/depth/footprint?depthId={did}&period=1").get_json()
    assert j["success"] and len(j["bars"]) == 3 and j["bigOrder"] == 100 and len(j["bigOrders"]) == 2
    j2 = client.get(f"/api/depth/footprint?depthId={did}&bigOrder=60").get_json()
    assert len(j2["bigOrders"]) == 5
    assert client.get(f"/api/depth/footprint?depthId={did}&bigOrder=0").status_code == 400
    assert client.get(f"/api/depth/footprint?depthId={did}&bigOrder=abc").status_code == 400
    # 旧格式（没有 BS）：400 + 可读说明
    did2 = _upload(csv_bytes(), "nobs.csv").get_json()["depthId"]
    r2 = client.get(f"/api/depth/footprint?depthId={did2}")
    assert r2.status_code == 400 and "BS" in r2.get_json()["message"]
    assert client.get("/api/depth/footprint?depthId=nope").status_code == 410


# ---------------------------------------------------------------------------
# 合约合并 / 合约索引
# ---------------------------------------------------------------------------
def _day_rows(symbol, day, start_cum, n=5, minute0=0, bs="多开", hour=9):
    """某个交易日（日盘）的 n 笔 tick：每笔 +10 手，累计量从 start_cum 开始。day 形如 '2026-9-17'。"""
    rows = []
    for i in range(n):
        cum = start_cum + (i + 1) * 10
        rows.append(f"{symbol},{day} {hour}:{minute0 + i},{bs},{5000 + i},{4999 + i},5,{5001 + i},6,{cum},3.6E+09,300000,5000,5010,4990")
    return rows


def test_merge_keeps_per_file_volume_increments():
    # 两个交易日各一个文件：第二天开盘累计量从头开始（比前一天末尾小很多）。
    # 如果合并后再整体差分，第二天首笔会被错算；合并必须只拼接各文件已算好的增量。
    a = dm.parse(csv_bytes(_day_rows("fu2701", "2026-9-17", 0), HEADER_B), "a.csv")
    b = dm.parse(csv_bytes(_day_rows("fu2701", "2026-9-18", 0), HEADER_B), "b.csv")
    m = dm.merge([a, b])
    assert m.count == 10 and m.days == ["2026-09-17", "2026-09-18"]
    assert list(m.vol) == [10] * 10
    # 乱序传入也按时间合并
    m2 = dm.merge([b, a])
    assert list(m2.ts) == list(m.ts) and m2.symbol == "fu2701"
    assert [x["time"][:10] for x in dm.build_kline(m, 1440)["bars"]] == ["2026-09-17", "2026-09-18"]


def test_merge_dedups_overlapping_days():
    full = dm.parse(csv_bytes(_day_rows("fu2701", "2026-9-17", 0, n=8), HEADER_B), "full.csv")
    part = dm.parse(csv_bytes(_day_rows("fu2701", "2026-9-17", 0, n=3), HEADER_B), "part.csv")
    other = dm.parse(csv_bytes(_day_rows("fu2701", "2026-9-18", 0, n=4), HEADER_B), "other.csv")
    m = dm.merge([part, full, other])
    # 9-17 只保留 tick 更多的 full（8 笔），不翻倍
    assert m.count == 8 + 4
    assert sum(m.vol[m.day == "2026-09-17"]) == 80
    assert any("重复出现" in w for w in m.warnings)


def test_merge_keeps_night_session_split_across_files():
    # 行情文件按自然日切：文件 A = 9-17 日盘 + 当晚夜盘（归 9-18），文件 B = 9-18 日盘 + 当晚夜盘（归 9-21，周五夜盘算下周一）。
    # 9-18 的夜盘在 A、日盘在 B，是互补不是重复，合并后两段都要保留。
    a = dm.parse(csv_bytes(
        _day_rows("fu2701", "2026-9-17", 0, n=6) + _day_rows("fu2701", "2026-9-17", 0, n=3, hour=21), HEADER_B), "a.csv")
    b = dm.parse(csv_bytes(
        _day_rows("fu2701", "2026-9-18", 0, n=5) + _day_rows("fu2701", "2026-9-18", 0, n=2, hour=21), HEADER_B), "b.csv")
    assert a.days == ["2026-09-17", "2026-09-18"] and b.days == ["2026-09-18", "2026-09-21"]   # 周五夜盘归下周一
    m = dm.merge([a, b])
    assert m.count == 6 + 3 + 5 + 2                      # 一笔都不丢
    assert (m.day == "2026-09-18").sum() == 3 + 5        # 9-18：夜盘 3 笔（来自 A）+ 日盘 5 笔（来自 B）
    assert not any("重复出现" in w for w in m.warnings)  # 互补，不算重复


def test_merge_levels_and_bs_mismatch_degrade():
    with_bs = dm.parse(csv_bytes(_day_rows("fu2701", "2026-9-17", 0), HEADER_B), "a.csv")
    text = "time,last,volume,a1_p,a1_v,b1_p,b1_v\n2026-9-18 9:00,100,5,101,1,99,1\n2026-9-18 9:01,101,9,102,1,100,1\n"
    no_bs = dm.parse(text.encode(), "b.csv")
    m = dm.merge([with_bs, no_bs])
    assert m.bs is None and any("BS" in w for w in m.warnings)
    assert dm.merge([with_bs]) is with_bs


def test_peek_meta_matches_parse():
    content = csv_bytes(ROWS_B, HEADER_B)
    meta = dm.peek_meta(content, "a2611.csv")
    td = dm.parse(content, "a2611.csv")
    assert meta["symbol"] == td.symbol and meta["tickCount"] == td.count and meta["days"] == td.days
    assert meta["start"] == dm.fmt_ts(td.ts[0], True) and meta["end"] == dm.fmt_ts(td.ts[-1], True)
    assert meta["hasBs"] is True and meta["levels"] == 1
    try:
        dm.peek_meta(b"a,b\n1,2\n", "x.csv")
    except dm.DepthParseError:
        pass
    else:
        raise AssertionError("无法识别的文件应抛 DepthParseError")


def _data_files():
    """目录里的数据文件（不含点开头的元数据索引文件）。"""
    return sorted(n for n in os.listdir(_TMP_DIR) if not n.startswith('.'))


def _clear_depth_files():
    for n in os.listdir(_TMP_DIR):
        os.remove(os.path.join(_TMP_DIR, n))
    depth_service._DEPTH_META_CACHE.clear()


def test_contracts_index_open_and_delete():
    _clear_depth_files()
    assert client.get("/api/depth/contracts").get_json()["contracts"] == []
    # fu2701 两个交易日（两个文件），a2611 一个文件，外加一个无法识别的文件
    assert _upload(csv_bytes(_day_rows("fu2701", "2026-9-17", 0), HEADER_B), "fu_0917.csv").status_code == 200
    assert _upload(csv_bytes(_day_rows("fu2701", "2026-9-18", 0), HEADER_B), "fu_0918.csv").status_code == 200
    assert _upload(csv_bytes(ROWS_B, HEADER_B), "a2611.csv").status_code == 200
    with open(os.path.join(_TMP_DIR, "junk.csv"), "wb") as f:
        f.write(b"x,y\n1,2\n")

    j = client.get("/api/depth/contracts").get_json()
    by = {c["symbol"]: c for c in j["contracts"]}
    assert set(by) == {"fu2701", "a2611"}
    fu = by["fu2701"]
    assert fu["fileCount"] == 2 and fu["tickCount"] == 10 and fu["dayCount"] == 2 and fu["hasBs"] is True
    assert fu["days"] == ["2026-09-17", "2026-09-18"]
    assert [f["name"] for f in fu["files"]] == ["fu2701_20260917.csv", "fu2701_20260918.csv"]   # 上传时按文件内容改名；按开始时间升序
    assert [x["name"] for x in j["unrecognized"]] == ["junk.csv"]

    # 索引缓存：文件没变不会重复读（缓存条目的签名保持不变）
    sig = depth_service._DEPTH_META_CACHE["fu2701_20260917.csv"][0]
    client.get("/api/depth/contracts")
    assert depth_service._DEPTH_META_CACHE["fu2701_20260917.csv"][0] == sig

    # 按合约打开：两个文件合并，增量不被错误相减
    o = client.post("/api/depth/open-contract", json={"symbol": "fu2701"}).get_json()
    assert o["success"] and o["tickCount"] == 10 and o["fileCount"] == 2 and o["days"] == ["2026-09-17", "2026-09-18"]
    k = client.get(f"/api/depth/kline?depthId={o['depthId']}&period=1440").get_json()
    assert [b["volume"] for b in k["bars"]] == [50, 50]
    assert client.post("/api/depth/open-contract", json={"symbol": "nope"}).status_code == 404

    # 文件被改动后索引随之更新（缓存按大小 / 修改时间失效）
    assert _upload(csv_bytes(_day_rows("fu2701", "2026-9-17", 0, n=7), HEADER_B), "fu_0917.csv").status_code == 200
    fu2 = {c["symbol"]: c for c in client.get("/api/depth/contracts").get_json()["contracts"]}["fu2701"]
    assert fu2["tickCount"] == 7 + 5

    # 删除合约：只删它名下的文件
    d = client.delete("/api/depth/contracts", json={"symbol": "fu2701"}).get_json()
    assert d["success"] and sorted(d["deleted"]) == ["fu2701_20260917.csv", "fu2701_20260918.csv"]
    left = {c["symbol"] for c in client.get("/api/depth/contracts").get_json()["contracts"]}
    assert left == {"a2611"} and os.path.exists(os.path.join(_TMP_DIR, "a2611_20260917.csv"))
    assert client.delete("/api/depth/contracts", json={"symbol": "fu2701"}).status_code == 404
    _clear_depth_files()


def _upload(content, name="t.csv", overwrite=True):
    data = {"file": (io.BytesIO(content), name)}
    if overwrite:
        data["overwrite"] = "1"
    return client.post("/api/depth/upload", data=data, content_type="multipart/form-data")


FLOW_SAVED = "A2607.XDCE_20260601.csv"   # flow.csv 上传后按文件内的合约和交易日改名


def test_api_flow():
    r = _upload(csv_bytes(), "flow.csv")
    assert r.status_code == 200
    j = r.get_json()
    assert j["success"] and j["tickCount"] == 5 and j["levels"] == 1 and j["saved"]
    did = j["depthId"]

    # 同名不覆盖 -> 409
    r2 = _upload(csv_bytes(), "flow.csv", overwrite=False)
    assert r2.status_code == 409 and r2.get_json()["exists"]

    k = client.get(f"/api/depth/kline?depthId={did}&period=1").get_json()
    assert k["success"] and len(k["bars"]) == 3
    assert client.get(f"/api/depth/kline?depthId={did}&period=7").status_code == 400

    b = client.get(f"/api/depth/book?depthId={did}&index=1").get_json()
    assert b["success"] and b["price"] == 4724 and b["bids"][0]["volume"] == 50

    t = client.get(f"/api/depth/ticks?depthId={did}&start=0&count=3").get_json()
    assert len(t["ticks"]) == 3 and t["total"] == 5

    # 列表 / 打开 / 删除
    files = client.get("/api/depth/files").get_json()["files"]
    assert any(f["name"] == FLOW_SAVED for f in files)
    o = client.post("/api/depth/open", json={"name": FLOW_SAVED}).get_json()
    assert o["success"] and o["tickCount"] == 5
    assert client.post("/api/depth/open", json={"name": "../evil.csv"}).status_code == 400
    assert client.delete("/api/depth/files", json={"name": FLOW_SAVED}).status_code == 200
    assert client.post("/api/depth/open", json={"name": FLOW_SAVED}).status_code == 404

    # 缓存失效
    assert client.get("/api/depth/kline?depthId=nope").status_code == 410


def test_upload_rejects_bad_file():
    assert _upload(b"a,b\n1,2\n", "bad.csv").status_code == 400
    assert _upload(b"x", "bad.txt").status_code == 400
    assert not os.path.exists(os.path.join(_TMP_DIR, "bad.csv"))


def test_upload_larger_than_global_limit():
    # 全局限制 20MB，深度行情放宽到 500MB：构造 ~22MB 的 CSV
    row = ROWS[0]
    body = csv_bytes([row] * 260000)
    assert len(body) > 20 * 1024 * 1024
    r = _upload(body, "big.csv")
    assert r.status_code == 200, r.get_data(as_text=True)[:200]


# ---------------------------------------------------------------------------
# 批量导入：全量压缩包（YYYYMM/YYYYMMDD/合约.zip）-> 指定品种
# ---------------------------------------------------------------------------
import zipfile  # noqa: E402

FU_HEADER = "InstrumentID,TradingTime,BS,LastPrice,Volume"


def _fu_csv(symbol, day_str):
    """某合约某天的 CSV（日盘单个交易日）。day_str 形如 2026-11-02。"""
    rows = [f"{symbol},{day_str} 9:00:00,多开,3000,10", f"{symbol},{day_str} 9:00:01,空平,3001,12"]
    return ("\n".join([FU_HEADER] + rows)).encode("utf-8")


def _inner_zip(csv, csv_name):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(csv_name, csv)
    return buf.getvalue()


def _archive(entries, nested_months=False):
    """entries: {zip 内路径: 字节}；nested_months=True 时把整个月份文件夹再打成 zip。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in entries.items():
            z.writestr(path, data)
    return buf.getvalue()


class _Resp:
    """把「上传 -> 轮询任务」包装成和同步接口一样的响应，方便断言。"""

    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def get_json(self):
        return self._body

    def get_data(self, as_text=False):
        return str(self._body)


def _upload_archive(content, product, overwrite=False, name="all.zip"):
    import time
    data = {"file": (io.BytesIO(content), name), "product": product}
    if overwrite:
        data["overwrite"] = "1"
    r = client.post("/api/depth/upload-archive", data=data, content_type="multipart/form-data")
    if r.status_code != 200:
        return r
    task_id = r.get_json()["taskId"]
    for _ in range(200):
        t = client.get(f"/api/depth/archive-task?id={task_id}").get_json()
        if t["status"] == "done":
            assert t["done"] == t["total"]
            return _Resp(200, t["result"])
        if t["status"] == "error":
            return _Resp(400, {"success": False, "message": t["message"]})
        time.sleep(0.05)
    raise AssertionError("批量导入任务超时")


def _full_archive():
    return _archive({
        "202611/20261102/fu2611.zip": _inner_zip(_fu_csv("fu2611", "2026-11-02"), "fu2611.csv"),
        "202611/20261102/fu2701.zip": _inner_zip(_fu_csv("fu2701", "2026-11-02"), "fu2701.csv"),
        "202611/20261102/rb2610.zip": _inner_zip(_fu_csv("rb2610", "2026-11-02"), "rb2610.csv"),
        "202611/20261103/fu2611.zip": _inner_zip(_fu_csv("fu2611", "2026-11-03"), "fu2611.csv"),
        "202611/20261103/fut2611.zip": _inner_zip(_fu_csv("fut2611", "2026-11-03"), "fut2611.csv"),  # 不能被 fu 误匹配
        "__MACOSX/202611/20261103/._fu2611.zip": b"junk",
    })


def test_archive_import_by_product():
    _clear_depth_files()
    r = _upload_archive(_full_archive(), "FU")   # 品种大小写不敏感
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert j["products"] == ["fu"] and j["perProduct"] == {"fu": 3} and j["matched"] == 3
    assert j["imported"] == 3 and j["failed"] == 0 and j["skipped"] == 0
    assert j["contracts"] == ["fu2611", "fu2701"]
    assert sorted(_data_files()) == ["fu2611_20261102.csv", "fu2611_20261103.csv", "fu2701_20261102.csv"]
    # 数据库管理里能按合约合并出来
    cs = client.get("/api/depth/contracts").get_json()["contracts"]
    fu = next(c for c in cs if c["symbol"] == "fu2611")
    assert fu["fileCount"] == 2 and fu["dayCount"] == 2

    # 再导一次：默认跳过；overwrite=1 覆盖
    j2 = _upload_archive(_full_archive(), "fu").get_json()
    assert j2["imported"] == 0 and j2["skipped"] == 3
    j3 = _upload_archive(_full_archive(), "fu", overwrite=True).get_json()
    assert j3["overwritten"] == 3 and j3["skipped"] == 0
    _clear_depth_files()


def test_archive_nested_zip_layers():
    """月份、交易日这两层本身也是 zip 的情况。"""
    _clear_depth_files()
    day = _archive({"fu2611.zip": _inner_zip(_fu_csv("fu2611", "2026-11-04"), "fu2611.csv")})
    month = _archive({"20261104.zip": day})
    outer = _archive({"202611.zip": month})
    j = _upload_archive(outer, "fu").get_json()
    assert j["imported"] == 1 and _data_files() == ["fu2611_20261104.csv"]
    _clear_depth_files()


def test_archive_bad_member_reported_not_fatal():
    _clear_depth_files()
    arc = _archive({
        "202611/20261102/fu2611.zip": _inner_zip(_fu_csv("fu2611", "2026-11-02"), "fu2611.csv"),
        "202611/20261103/fu2611.zip": _inner_zip(b"a,b\n1,2\n", "fu2611.csv"),     # CSV 无法识别
        "202611/20261104/fu2611.zip": b"not a zip",                                 # 不是 zip
    })
    j = _upload_archive(arc, "fu").get_json()
    assert j["matched"] == 3 and j["imported"] == 1 and j["failed"] == 2
    assert _data_files() == ["fu2611_20261102.csv"]
    _clear_depth_files()


def test_archive_rejects():
    _clear_depth_files()
    assert _upload_archive(_full_archive(), "").status_code == 400            # 没选品种
    assert _upload_archive(_full_archive(), "fu2611").status_code == 400      # 品种非法
    assert _upload_archive(_full_archive(), "zz").status_code == 400          # 没有该品种
    assert _upload_archive(b"nope", "fu").status_code == 400                  # 不是 zip
    assert _upload_archive(b"x", "fu", name="a.csv").status_code == 400       # 扩展名不对
    assert _data_files() == []


def _multi_archive():
    return _archive({
        "202611/20261102/fu2611.zip": _inner_zip(_fu_csv("fu2611", "2026-11-02"), "fu2611.csv"),
        "202611/20261102/ag2612.zip": _inner_zip(_fu_csv("ag2612", "2026-11-02"), "ag2612.csv"),
        "202611/20261102/a2701.zip": _inner_zip(_fu_csv("a2701", "2026-11-02"), "a2701.csv"),
        "202611/20261102/rb2610.zip": _inner_zip(_fu_csv("rb2610", "2026-11-02"), "rb2610.csv"),
        "202611/20261103/ag2612.zip": _inner_zip(_fu_csv("ag2612", "2026-11-03"), "ag2612.csv"),
    })


def test_archive_multiple_products():
    _clear_depth_files()
    j = _upload_archive(_multi_archive(), ["fu", "AG", "zz"]).get_json()   # zz 压缩包里没有：不报错，计数为 0
    assert j["products"] == ["fu", "ag", "zz"]
    assert j["perProduct"] == {"fu": 1, "ag": 2, "zz": 0}
    assert j["matched"] == 3 and j["imported"] == 3 and j["failed"] == 0
    assert j["contracts"] == ["ag2612", "fu2611"]
    assert sorted(_data_files()) == ["ag2612_20261102.csv", "ag2612_20261103.csv", "fu2611_20261102.csv"]
    _clear_depth_files()

    # 同时选 a 和 ag：ag2612 归 ag，不能被算进 a；a2701 归 a
    j = _upload_archive(_multi_archive(), ["a", "ag"]).get_json()
    assert j["perProduct"] == {"a": 1, "ag": 2} and j["matched"] == 3
    assert j["contracts"] == ["a2701", "ag2612"]
    _clear_depth_files()

    # 逗号分隔的单个字段也兼容；全部都没有 -> 400；任一项非法 -> 400
    assert _upload_archive(_multi_archive(), "fu,ag").get_json()["perProduct"] == {"fu": 1, "ag": 2}
    _clear_depth_files()
    assert _upload_archive(_multi_archive(), ["zz", "yy"]).status_code == 400
    assert _upload_archive(_multi_archive(), ["fu", "fu2611"]).status_code == 400
    assert _data_files() == []


def test_archive_latest_task_for_restoring_progress():
    """页面重新进入时不带 id 查询：有运行中的任务优先返回它，否则返回最近一个；没有任务 404 + noTask。"""
    import time
    from backend.services import depth_archive
    _clear_depth_files()
    saved = dict(depth_archive._TASKS)
    depth_archive._TASKS.clear()
    try:
        r = client.get("/api/depth/archive-task")
        assert r.status_code == 404 and r.get_json()["noTask"]

        # 构造一个「运行中」的任务和一个「已完成」的任务
        depth_archive._TASKS["done1"] = {"id": "done1", "status": "done", "products": ["fu"], "originalName": "a.zip",
                                         "done": 3, "total": 3, "current": "", "message": "", "result": None}
        depth_archive._TASKS["run1"] = {"id": "run1", "status": "running", "products": ["ag"], "originalName": "b.zip",
                                        "done": 1, "total": 5, "current": "202611/x/ag2612.zip", "message": "", "result": None}
        depth_archive._TASKS["done2"] = {"id": "done2", "status": "done", "products": ["rb"], "originalName": "c.zip",
                                         "done": 2, "total": 2, "current": "", "message": "", "result": None}
        j = client.get("/api/depth/archive-task").get_json()
        assert j["taskId"] == "run1" and j["status"] == "running" and j["done"] == 1 and j["total"] == 5

        depth_archive._TASKS["run1"]["status"] = "done"
        assert client.get("/api/depth/archive-task").get_json()["taskId"] == "done2"   # 无运行中 -> 最后一个

        # 带 id 仍按 id 查；不存在的 id 是 404 + expired
        assert client.get("/api/depth/archive-task?id=done1").get_json()["products"] == ["fu"]
        r = client.get("/api/depth/archive-task?id=nope")
        assert r.status_code == 404 and r.get_json()["expired"]
    finally:
        depth_archive._TASKS.clear()
        depth_archive._TASKS.update(saved)


# ---------------------------------------------------------------------------
# 持久化元数据索引（depth_files/.meta_index.json）
# ---------------------------------------------------------------------------
import json  # noqa: E402


class _CountPeek:
    """统计 depth_market.peek_meta 被调用的次数（= 实际读了多少个 CSV）。"""

    def __enter__(self):
        self.n = 0
        self._orig = depth_market_mod.peek_meta

        def counted(*a, **k):
            self.n += 1
            return self._orig(*a, **k)
        depth_market_mod.peek_meta = counted
        return self

    def __exit__(self, *exc):
        depth_market_mod.peek_meta = self._orig


from backend.core import depth_market as depth_market_mod  # noqa: E402


def _index_file():
    return os.path.join(_TMP_DIR, depth_service.META_INDEX_NAME)


def _simulate_restart():
    """模拟后端重启：内存缓存清空、'已加载' 标记复位，下一次 scan 只能靠磁盘索引。"""
    depth_service._DEPTH_META_CACHE.clear()
    depth_service._index_state.update(dir=None, loaded=False, dirty=False)


def test_index_import_records_meta_so_listing_reads_no_csv():
    _clear_depth_files()
    _simulate_restart()
    assert _upload(csv_bytes(_day_rows("fu2701", "2026-9-17", 0), HEADER_B), "x.csv").status_code == 200
    assert os.path.exists(_index_file())            # 导入时就落盘了
    with _CountPeek() as c:
        j = client.get("/api/depth/contracts").get_json()
    assert c.n == 0 and [x["symbol"] for x in j["contracts"]] == ["fu2701"]   # 列表没有再读 CSV
    _clear_depth_files()


def test_index_survives_restart_without_reading_csv():
    _clear_depth_files()
    _simulate_restart()
    for d in ("2026-9-17", "2026-9-18"):
        assert _upload(csv_bytes(_day_rows("fu2701", d, 0), HEADER_B), f"x{d}.csv").status_code == 200
    before = client.get("/api/depth/contracts").get_json()

    _simulate_restart()                              # 重启：内存清空，只剩磁盘索引
    with _CountPeek() as c:
        after = client.get("/api/depth/contracts").get_json()
    assert c.n == 0, "重启后列表应直接用磁盘索引，不读 CSV"
    assert after == before                           # 结果与重启前完全一致
    _clear_depth_files()


def test_index_invalidates_on_change_and_prunes_deleted():
    _clear_depth_files()
    _simulate_restart()
    assert _upload(csv_bytes(_day_rows("fu2701", "2026-9-17", 0), HEADER_B), "a.csv").status_code == 200
    assert _upload(csv_bytes(_day_rows("fu2701", "2026-9-18", 0), HEADER_B), "b.csv").status_code == 200
    client.get("/api/depth/contracts")
    _simulate_restart()

    # 重启期间有人直接改了一个文件、删了一个文件、又丢进来一个新文件（没经过后端）
    changed = os.path.join(_TMP_DIR, "fu2701_20260917.csv")
    with open(changed, "wb") as f:
        f.write(csv_bytes(_day_rows("fu2701", "2026-9-17", 0, n=9), HEADER_B))
    os.remove(os.path.join(_TMP_DIR, "fu2701_20260918.csv"))
    with open(os.path.join(_TMP_DIR, "ag_new.csv"), "wb") as f:
        f.write(csv_bytes(_day_rows("ag2612", "2026-9-19", 0), HEADER_B))

    with _CountPeek() as c:
        j = client.get("/api/depth/contracts").get_json()
    assert c.n == 2, "只有改动的和新增的文件需要重新读取"
    by = {x["symbol"]: x for x in j["contracts"]}
    assert by["fu2701"]["tickCount"] == 9 and by["fu2701"]["fileCount"] == 1 and "ag2612" in by

    saved = json.load(open(_index_file(), encoding="utf-8"))
    assert saved["version"] == depth_service.META_INDEX_VERSION
    assert sorted(saved["files"]) == ["ag_new.csv", "fu2701_20260917.csv"]   # 已删除的文件从索引里清掉
    _clear_depth_files()


def test_index_corrupt_or_wrong_version_is_rebuilt():
    _clear_depth_files()
    _simulate_restart()
    assert _upload(csv_bytes(_day_rows("fu2701", "2026-9-17", 0), HEADER_B), "a.csv").status_code == 200
    for garbage in ('{ not json', json.dumps({"version": 999, "files": {}}), json.dumps({"version": 1, "files": [1]}),
                    json.dumps({"version": 1, "files": {"fu2701_20260917.csv": {"sig": "bad", "meta": 1}}})):
        with open(_index_file(), "w", encoding="utf-8") as f:
            f.write(garbage)
        _simulate_restart()
        with _CountPeek() as c:
            j = client.get("/api/depth/contracts").get_json()
        assert c.n == 1 and [x["symbol"] for x in j["contracts"]] == ["fu2701"], garbage   # 丢弃坏索引，重新读 CSV
        assert json.load(open(_index_file(), encoding="utf-8"))["version"] == depth_service.META_INDEX_VERSION   # 并重写
    _clear_depth_files()


def test_index_file_is_not_treated_as_data():
    _clear_depth_files()
    _simulate_restart()
    assert _upload(csv_bytes(_day_rows("fu2701", "2026-9-17", 0), HEADER_B), "a.csv").status_code == 200
    assert os.path.exists(_index_file())
    names = [f["name"] for f in client.get("/api/depth/files").get_json()["files"]]
    assert depth_service.META_INDEX_NAME not in names
    assert client.get("/api/depth/contracts").get_json()["unrecognized"] == []
    _clear_depth_files()


def test_index_unreadable_csv_error_is_persisted_too():
    """解析不了的文件也进索引（带 error），重启后不会反复尝试解析同一个坏文件。"""
    _clear_depth_files()
    _simulate_restart()
    with open(os.path.join(_TMP_DIR, "junk.csv"), "wb") as f:
        f.write(b"x,y\n1,2\n")
    j = client.get("/api/depth/contracts").get_json()
    assert [x["name"] for x in j["unrecognized"]] == ["junk.csv"]
    _simulate_restart()
    with _CountPeek() as c:
        j2 = client.get("/api/depth/contracts").get_json()
    assert c.n == 0 and j2["unrecognized"] == j["unrecognized"]
    _clear_depth_files()


def test_archive_import_writes_index_once_and_listing_reads_nothing():
    _clear_depth_files()
    _simulate_restart()
    saves = []
    orig = depth_service._save_index

    def spy():
        saves.append(1)
        return orig()
    depth_service._save_index = spy
    try:
        j = _upload_archive(_full_archive(), "fu").get_json()
    finally:
        depth_service._save_index = orig
    assert j["imported"] == 3
    assert len(saves) == 1, f"批量导入应在结束时统一落盘一次，实际 {len(saves)} 次"
    saved = json.load(open(_index_file(), encoding="utf-8"))
    assert sorted(saved["files"]) == ["fu2611_20261102.csv", "fu2611_20261103.csv", "fu2701_20261102.csv"]
    _simulate_restart()
    with _CountPeek() as c:
        client.get("/api/depth/contracts")
    assert c.n == 0
    _clear_depth_files()


def test_archive_import_parses_each_csv_once():
    """批量导入每份 CSV 只解析一次（以前 peek_meta 在导入里跑了两遍）。"""
    _clear_depth_files()
    _simulate_restart()
    with _CountPeek() as c:
        j = _upload_archive(_full_archive(), "fu").get_json()
    assert j["imported"] == 3 and c.n == 3, f"3 份 CSV 应只解析 3 次，实际 {c.n}"
    _clear_depth_files()


def test_index_concurrent_scans_are_consistent():
    import threading
    _clear_depth_files()
    _simulate_restart()
    for i, d in enumerate(("2026-9-17", "2026-9-18", "2026-9-19")):
        with open(os.path.join(_TMP_DIR, f"f{i}.csv"), "wb") as f:
            f.write(csv_bytes(_day_rows("fu2701", d, 0), HEADER_B))
    results, errors = [], []

    def work():
        try:
            results.append(client.get("/api/depth/contracts").get_json()["contracts"][0]["tickCount"])
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors and results == [15] * 8
    saved = json.load(open(_index_file(), encoding="utf-8"))      # 并发写后索引仍是合法 JSON
    assert len(saved["files"]) == 3
    _clear_depth_files()


# ---------------------------------------------------------------------------
# K 线聚合向量化：必须和旧的逐根组装实现（tests/kline_reference.py）逐字段、逐类型、逐字节一致
# ---------------------------------------------------------------------------
import json as _json  # noqa: E402
from kline_reference import build_kline_reference  # noqa: E402


def _strict_equal(a, b):
    """逐字段比较且要求类型一致（int 与 float 视为不同：1 == 1.0 会掩盖 JSON 输出差异）；dict 还要求键顺序一致。"""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return list(a) == list(b) and all(_strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_strict_equal(x, y) for x, y in zip(a, b))
    return a == b


def _assert_same_kline(td, periods=(1, 5, 15, 30, 60, 1440), days=(None,)):
    for period in periods:
        for day in days:
            old = build_kline_reference(td, period, day)
            new = dm.build_kline(td, period, day)
            assert _strict_equal(old, new), (period, day)
            assert _json.dumps(old, ensure_ascii=False) == _json.dumps(new, ensure_ascii=False), (period, day)


def test_kline_vectorized_matches_reference_on_fixture_data():
    td = dm.parse(csv_bytes(), "a.csv")                       # 带夜盘 + 日盘、BS 列
    _assert_same_kline(td, days=(None, "2026-06-01", "2030-01-01"))
    td2 = dm.parse(csv_bytes(ROWS_B, HEADER_B), "a2611.csv")
    _assert_same_kline(td2, days=(None, "2026-09-17"))


def test_kline_vectorized_matches_reference_multi_day_merge():
    parts = [dm.parse(csv_bytes(_day_rows("fu2701", d, 0, n=40, minute0=0), HEADER_B), "x.csv")
             for d in ("2026-9-17", "2026-9-18", "2026-9-21")]
    td = dm.merge(parts)
    _assert_same_kline(td, days=(None, "2026-09-18"))
    assert len(dm.build_kline(td, 1)["bars"]) > 3


def test_kline_vectorized_without_bs_column_and_empty_result():
    no_bs = "symbol,code,name,time,open,current,high,low,volume,money,position"
    rows = ["fu2701,x,燃油,20261020090000000,0,3000,3000,3000,10,30000,100",
            "fu2701,x,燃油,20261020090010000,0,3001.5,3001.5,3000,25,75000,101",
            "fu2701,x,燃油,20261020090100000,0,2999.25,3001.5,2999.25,40,120000,99"]
    td = dm.parse(csv_bytes(rows, no_bs), "nobs.csv")
    assert td.bs is None
    _assert_same_kline(td, days=(None,))
    assert all(b["bs"] is None for b in dm.build_kline(td, 1)["bars"])      # 没有 BS 列：每根 bs 都是 None（不是 {}）
    assert dm.build_kline(td, 1, "2099-01-01") == {"bars": [], "period": 1} == build_kline_reference(td, 1, "2099-01-01")
    # 非整数价格保留小数、整数价格输出 int —— 两个实现的类型必须一致
    bars = dm.build_kline(td, 1)["bars"]
    assert any(isinstance(b["close"], float) for b in bars) and any(isinstance(b["open"], int) for b in bars)


def test_clean_list_equals_clean_elementwise():
    """_clean_list 对各种数值的结果必须与逐个 _clean 完全一致（含 NaN、负数、大数、6 位小数舍入边界、-0.0）。"""
    import numpy as np
    vals = np.array([0.0, -0.0, 1.0, -1.0, 3000.0, 3001.5, 2999.25, 0.1 + 0.2, 1 / 3, 2 / 3, -2 / 3, 1e-7, 5e-7, 1.0000005,
                     0.1234565, 0.1234575, 123456.7891235, 1e14, 1e15, 1e15 - 1, 9.99e14, -1e15, 4.5e15, 12345678901234.5,
                     float("nan"), 2.5, 0.5, 1.5, 1234567.0000004, 99.9999996, 1e-320])
    assert _strict_equal(dm._clean_list(vals), [dm._clean(x) for x in vals])
    rng = np.random.default_rng(7)
    rand = np.concatenate([rng.normal(3000, 50, 5000).round(rng.integers(0, 8)), rng.integers(0, 10**6, 2000).astype(float),
                           rng.random(2000) * 1e-3, -rng.random(1000) * 1e4])
    assert _strict_equal(dm._clean_list(rand), [dm._clean(x) for x in rand])
    assert dm._clean_list(np.array([])) == []


def test_kline_vectorized_handles_bs_blank_and_missing_bars():
    """BS 列里有认不出的值（解析后是空串，不计入 bs）；某根 K 线所有成交性质都认不出时 bs 是 {} 而不是 None。"""
    hdr = "InstrumentID,TradingTime,BS,LastPrice,BidPrice1,BidVolume1,AskPrice1,AskVolume1,Volume,Turnover,OpenInterest"
    rows = ["fu2701,2026-9-17 9:00:00,多开,5000,4999,5,5001,6,10,100000,300",
            "fu2701,2026-9-17 9:00:10,未知,5001,5000,5,5002,6,25,250000,301",     # 认不出的 BS -> 空串
            "fu2701,2026-9-17 9:01:00,???,5002,5001,5,5003,6,30,300000,302",       # 这根 K 线全是认不出的 BS
            "fu2701,2026-9-17 9:02:00,空开,5003,5002,5,5004,6,45,450000,303"]
    td = dm.parse(csv_bytes(rows, hdr), "blank.csv")
    _assert_same_kline(td, days=(None,))
    by_time = {b["time"][-5:]: b["bs"] for b in dm.build_kline(td, 1)["bars"]}
    assert by_time["09:01"] == {} and by_time["09:00"] == {"多开": 10}


def test_footprint_still_aligned_with_vectorized_kline():
    """足迹图复用 build_kline 的分组：bars 数量要和 levels 的分组完全对得上（足迹图原有测试的补充）。"""
    td = dm.parse(csv_bytes(ROWS_B, HEADER_B), "a2611.csv")
    fp = dm.build_footprint(td, 1)
    kl = dm.build_kline(td, 1)
    assert [b["time"] for b in fp["bars"]] == [b["time"] for b in kl["bars"]]
    assert all("levels" in b for b in fp["bars"])
    assert sum(lv["buy"] + lv["sell"] + lv["neutral"] for b in fp["bars"] for lv in b["levels"]) == \
        sum(b["volume"] for b in kl["bars"])


# ---------------------------------------------------------------------------
# 统一 tick 缓存（services/tick_cache.py）：深度行情 / 回测 / 复盘共用
# ---------------------------------------------------------------------------
from backend.services import kline_store, tick_cache  # noqa: E402


class _CountParse:
    """统计 depth_market.parse 的调用次数（= 实际解析了多少个 CSV）。"""

    def __enter__(self):
        self.n = 0
        self._orig = depth_market_mod.parse

        def counted(*a, **k):
            self.n += 1
            return self._orig(*a, **k)
        depth_market_mod.parse = counted
        return self

    def __exit__(self, *exc):
        depth_market_mod.parse = self._orig


def _seed_contract(symbol, days=("2026-9-17", "2026-9-18")):
    for i, d in enumerate(days):
        assert _upload(csv_bytes(_day_rows(symbol, d, 0), HEADER_B), f"{symbol}-{i}.csv").status_code == 200


def test_cache_depth_and_backtest_share_one_parse():
    """深度行情打开合约后，回测 / 复盘取同一合约的 K 线不再重新解析；内存里只有一份 TickData。"""
    _clear_depth_files()
    _seed_contract("fu2701")
    tick_cache.clear()          # 上传时登记的单文件句柄不在本测试范围内，清掉后只看合约这条路径
    with _CountParse() as c:
        o = client.post("/api/depth/open-contract", json={"symbol": "fu2701"}).get_json()
        assert o["success"] and c.n == 2                      # 2 个文件各解析一次
        bars = kline_store.fetch_bars("SHFE.fu2701", "1")     # 回测 / 复盘入口
        assert bars and c.n == 2, "回测取同一合约不应重新解析"
        # 再开一次深度行情：同样直接复用
        o2 = client.post("/api/depth/open-contract", json={"symbol": "fu2701"}).get_json()
        assert c.n == 2 and o2["depthId"] != o["depthId"] and o2["tickCount"] == o["tickCount"]
    assert tick_cache.get_handle(o["depthId"]) is tick_cache.get_handle(o2["depthId"])   # 句柄指向同一个对象
    st = tick_cache.stats()
    assert st["contracts"] == ["fu2701"]
    assert [h for h in (o["depthId"], o2["depthId"]) if tick_cache.get_handle(h) is not None] == [o["depthId"], o2["depthId"]]
    one = tick_cache.estimate_bytes(tick_cache.get_handle(o["depthId"]))
    assert st["usedBytes"] == one, "按对象去重：两个句柄 + 合约缓存只算一份内存"
    _clear_depth_files()


def test_cache_backtest_first_then_depth_reuses():
    _clear_depth_files()
    _seed_contract("fu2701")
    tick_cache.clear()
    with _CountParse() as c:
        assert kline_store.fetch_bars("fu2701", "5")
        assert c.n == 2
        o = client.post("/api/depth/open-contract", json={"symbol": "fu2701"}).get_json()
        assert o["success"] and c.n == 2, "深度行情应复用回测已解析的数据"
        assert kline_store.fetch_bars("fu2701", "1") and c.n == 2   # 其它周期复用同一份 tick
    _clear_depth_files()


def test_cache_invalidated_when_files_change_including_old_handles():
    _clear_depth_files()
    tick_cache.clear()
    _seed_contract("fu2701")
    o = client.post("/api/depth/open-contract", json={"symbol": "fu2701"}).get_json()
    assert client.get(f"/api/depth/kline?depthId={o['depthId']}&period=1440").status_code == 200
    n_before = len(kline_store.fetch_bars("fu2701", "1"))

    # 重新导入覆盖其中一天（数据变多）：合约缓存按文件签名失效，下次取用重新解析
    assert _upload(csv_bytes(_day_rows("fu2701", "2026-9-17", 0, n=9), HEADER_B), "again.csv").status_code == 200
    with _CountParse() as c:
        bars = kline_store.fetch_bars("fu2701", "1")
        assert c.n == 2 and len(bars) > n_before          # 重新解析 + K 线也是新的
    # 旧句柄指向的是过期数据，已一并作废（前端收到 410 会重新打开），不会悄悄返回旧数据
    assert client.get(f"/api/depth/kline?depthId={o['depthId']}&period=1440").status_code == 410
    o2 = client.post("/api/depth/open-contract", json={"symbol": "fu2701"}).get_json()
    assert o2["tickCount"] == 9 + 5
    _clear_depth_files()


def test_cache_single_file_open_has_own_handle_and_no_contract_entry():
    _clear_depth_files()
    tick_cache.clear()
    j = _upload(csv_bytes(), "flow.csv").get_json()
    assert client.get(f"/api/depth/kline?depthId={j['depthId']}&period=1").status_code == 200
    assert tick_cache.stats()["contracts"] == [] and tick_cache.stats()["handles"] == 1
    _clear_depth_files()


def _fake_td(n):
    """一个占用约 n 字节的假 TickData（只用数组，足够给淘汰逻辑测试）。"""
    import numpy as np
    from backend.core.depth_market import TickData
    k = max(1, n // (8 * 6))   # ts / price / vol / cum_vol / money / position 共 6 个 8 字节数组
    z = np.zeros(k)
    return TickData(ts=z.astype("int64"), price=z, vol=z, cum_vol=z, money=z, position=z, day=np.array([], dtype=object))


def test_cache_evicts_by_memory_budget_lru_and_keeps_latest(monkeypatch=None):
    import os as _os
    old = _os.environ.get(tick_cache.BUDGET_ENV)
    try:
        tick_cache.clear()
        mb = 1024 * 1024
        _os.environ[tick_cache.BUDGET_ENV] = "10"           # 预算 10MB
        # 6 个 3MB 的合约：一共 18MB > 10MB，只能留 3 个（最近使用的）
        for i in range(1, 7):
            td = _fake_td(3 * mb)
            tick_cache.put_contract(f"c{i}", ("sig",), td)
            if i == 2:
                tick_cache.get_contract("c1", ("sig",))      # 使用一下 c1，让它比 c2 新
        left = tick_cache.stats()["contracts"]
        assert left == ["c4", "c5", "c6"], left
        assert tick_cache.stats()["usedBytes"] <= 10 * mb

        # 句柄：深度行情正在看的合约（通过句柄使用）算最近使用，不会被后来的挤掉
        tick_cache.clear()
        td_a = _fake_td(4 * mb)
        tick_cache.put_contract("a", ("s",), td_a)
        h = tick_cache.new_handle(td_a, "a")
        tick_cache.put_contract("b", ("s",), _fake_td(4 * mb))
        assert tick_cache.get_handle(h) is td_a              # 用一下 a 的句柄 -> a 比 b 新
        tick_cache.put_contract("c", ("s",), _fake_td(4 * mb))   # 12MB > 10MB：淘汰最久没用的 b
        assert tick_cache.stats()["contracts"] == ["a", "c"] and tick_cache.get_handle(h) is td_a

        # 单份就超预算：最新的这份仍然保留（刚打开就失效是不可接受的）
        tick_cache.clear()
        big = _fake_td(30 * mb)
        tick_cache.put_contract("big", ("s",), big)
        h2 = tick_cache.new_handle(big, "big")
        assert tick_cache.get_handle(h2) is big and tick_cache.stats()["contracts"] == ["big"]
        # 再来一个小的：big 最久没用被淘汰，连同它的句柄一起失效（否则 TickData 仍被句柄持有，内存释放不了）
        tick_cache.put_contract("small", ("s",), _fake_td(1 * mb))
        assert tick_cache.stats()["contracts"] == ["small"] and tick_cache.get_handle(h2) is None
    finally:
        if old is None:
            _os.environ.pop(tick_cache.BUDGET_ENV, None)
        else:
            _os.environ[tick_cache.BUDGET_ENV] = old
        tick_cache.clear()


def test_cache_budget_env_parsing():
    import os as _os
    old = _os.environ.get(tick_cache.BUDGET_ENV)
    try:
        _os.environ.pop(tick_cache.BUDGET_ENV, None)
        assert tick_cache.budget_bytes() == tick_cache.DEFAULT_BUDGET_MB * 1024 * 1024
        _os.environ[tick_cache.BUDGET_ENV] = "abc"
        assert tick_cache.budget_bytes() == tick_cache.DEFAULT_BUDGET_MB * 1024 * 1024   # 非法值回退默认
        _os.environ[tick_cache.BUDGET_ENV] = "0"
        assert tick_cache.budget_bytes() >= 1024 * 1024                                  # 下限 1MB
    finally:
        if old is None:
            _os.environ.pop(tick_cache.BUDGET_ENV, None)
        else:
            _os.environ[tick_cache.BUDGET_ENV] = old


def test_cache_many_contracts_no_410_for_the_one_on_screen():
    """以前深度行情只留 3 份：连续打开 4 个合约，第 1 个就 410。现在按内存预算，几个小合约都留得住。"""
    _clear_depth_files()
    tick_cache.clear()
    ids = []
    for sym in ("fu2701", "fu2702", "fu2703", "fu2704", "fu2705"):
        _seed_contract(sym, days=("2026-9-17",))
        ids.append(client.post("/api/depth/open-contract", json={"symbol": sym}).get_json()["depthId"])
    for did in ids:
        assert client.get(f"/api/depth/kline?depthId={did}&period=1").status_code == 200
    _clear_depth_files()


def test_archive_zip_slip_ignored():
    _clear_depth_files()
    arc = _archive({"../../evil/20261102/fu2611.zip": _inner_zip(_fu_csv("fu2611", "2026-11-02"), "../evil.csv")})
    r = _upload_archive(arc, "fu")
    # 含 .. 的成员被忽略，因此视为没有找到数据
    assert r.status_code == 400
    assert _data_files() == []


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print("ok", name)
    finally:
        shutil.rmtree(_TMP_DIR, ignore_errors=True)
