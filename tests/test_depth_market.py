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

import depth_market as dm  # noqa: E402
import backend  # noqa: E402

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
    assert any("不是从开盘开始" in w for w in td.warnings)
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


def _upload(content, name="t.csv", overwrite=True):
    data = {"file": (io.BytesIO(content), name)}
    if overwrite:
        data["overwrite"] = "1"
    return client.post("/api/depth/upload", data=data, content_type="multipart/form-data")


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
    assert any(f["name"] == "flow.csv" for f in files)
    o = client.post("/api/depth/open", json={"name": "flow.csv"}).get_json()
    assert o["success"] and o["tickCount"] == 5
    assert client.post("/api/depth/open", json={"name": "../evil.csv"}).status_code == 400
    assert client.delete("/api/depth/files", json={"name": "flow.csv"}).status_code == 200
    assert client.post("/api/depth/open", json={"name": "flow.csv"}).status_code == 404

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


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print("ok", name)
    finally:
        shutil.rmtree(_TMP_DIR, ignore_errors=True)
