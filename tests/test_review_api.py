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
