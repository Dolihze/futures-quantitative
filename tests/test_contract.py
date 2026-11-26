"""接口契约测试：用真实响应校验 backend/schemas.py 里的 pydantic 模型。

后端改了响应字段而没同步 schemas.py（也就没同步前端类型）时，这里会失败。
同时校验 RESPONSES 里登记的每个 (方法, 路由) 都对应真实存在的路由，避免契约表和路由悄悄脱节。

运行：python -m pytest tests/test_contract.py -q
"""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from backend import app as backend  # noqa: E402
from backend import schemas  # noqa: E402
from backend.services import backtest_service  # noqa: E402

client = backend.app.test_client()
backend.init_runtime()   # 需要期货公司列表等磁盘配置；导入 backend.app 本身不会加载


@pytest.fixture(autouse=True)
def _isolated_dirs(monkeypatch, tmp_path):
    """每个用例用自己的数据目录。

    各测试模块在 import 时都会改同名环境变量（REVIEW_FILES_DIR / DEPTH_FILES_DIR），pytest 又是先 import 全部模块再跑用例，
    所以靠 import 时设置的目录会被“最后 import 的模块”覆盖，互相串数据。这里在用例运行时重新设置并在结束后自动还原。
    """
    review_dir = tmp_path / "review_files"
    depth_dir = tmp_path / "depth_files"
    review_dir.mkdir()
    depth_dir.mkdir()
    monkeypatch.setenv("REVIEW_FILES_DIR", str(review_dir))
    monkeypatch.setenv("DEPTH_FILES_DIR", str(depth_dir))
    # 元信息 / 合并结果缓存是进程级的，按文件名 + 大小 + 修改时间失效；换目录后清掉，避免命中别的用例留下的缓存
    from backend.services import depth_service, review_service, tick_store
    tick_store.reset_state()
    review_service._PARSED_CACHE.clear()
    review_service._REVIEW_ALL_CACHE.update(sig=None, id=None, warnings=[], skipped=[], fileCount=0)
    yield


def _validate(model, payload):
    return model.model_validate(payload)


def _upload(url, content, name):
    return client.post(url, data={"file": (io.BytesIO(content), name), "overwrite": "1"},
                       content_type="multipart/form-data")


def _bars(n=3):
    return [{"time": f"2026-10-20 09:{5 * i:02d}:00", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 5}
            for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# 契约表本身
# ---------------------------------------------------------------------------
def test_every_registered_contract_matches_a_real_route():
    rules = {}
    for r in backend.app.url_map.iter_rules():
        for m in r.methods - {"HEAD", "OPTIONS"}:
            rules[(m, r.rule)] = r
    missing = [k for k in schemas.RESPONSES if k not in rules]
    assert not missing, f"契约里登记了不存在的路由：{missing}"


# ---------------------------------------------------------------------------
# 账号
# ---------------------------------------------------------------------------
def test_brokers_contract():
    j = client.get("/api/brokers").get_json()
    assert isinstance(j, list) and j
    for g in j:
        _validate(schemas.BrokerGroup, g)


def test_credentials_contract():
    _validate(schemas.SavedCredentials, client.get("/api/credentials").get_json())


# ---------------------------------------------------------------------------
# 量化回测
# ---------------------------------------------------------------------------
def _tick_csv(symbol, rows_):
    """rows_: [(YYYYMMDDHHMMSS, price, 当日累计量)]"""
    rows = ["symbol,name,time,current,volume,money,position"]
    rows += [f"{symbol},测试,{t}000,{p},{v},{v * p * 10},1000" for t, p, v in rows_]
    return ("\n".join(rows) + "\n").encode("utf-8")


def test_backtest_contracts(monkeypatch):
    monkeypatch.setattr(backtest_service, "fetch_backtest_bars", lambda symbol, period: _bars())
    # 合约列表来自本地行情库（depth_files）：先导入一个合约
    csv = _tick_csv("fu2611", [("20261020090010", 100, 10), ("20261020090120", 101, 20)])
    assert _upload("/api/depth/upload", csv, "fu2611.csv").status_code == 200
    cs = _validate(schemas.BacktestContracts, client.get("/api/backtest/contracts").get_json())
    assert [c.symbol for c in cs.data] == ["fu2611"] and cs.default == "fu2611" and cs.recent == []
    rec = _validate(schemas.BacktestRecentSymbol,
                    client.post("/api/backtest/recent-symbol", json={"symbol": "fu2611"}).get_json())
    assert rec.recent == ["fu2611"]
    cs = _validate(schemas.BacktestContracts, client.get("/api/backtest/contracts").get_json())
    assert cs.recent == ["fu2611"] and cs.default == "fu2611"
    _validate(schemas.BacktestKline, client.get("/api/backtest/kline?symbol=fu2611&period=5&days=30").get_json())
    ov = _validate(schemas.BacktestOverview, client.get("/api/backtest/overview?symbol=fu2611&days=30").get_json())
    assert ov.data, "至少应有一个策略"
    _validate(schemas.BacktestRun, client.get("/api/backtest/run?strategy=reversal&symbol=fu2611&days=30").get_json())


def test_backtest_contracts_empty_library_contract():
    cs = _validate(schemas.BacktestContracts, client.get("/api/backtest/contracts").get_json())
    assert cs.data == [] and cs.default == ""


def test_error_envelope_contract():
    for url in ("/api/backtest/kline", "/api/backtest/run?strategy=nope",
                "/api/review/curve?reviewId=zzz", "/api/depth/kline?depthId=zzz"):
        j = client.get(url).get_json()
        m = _validate(schemas.ApiResult, j)
        assert m.success is False and m.message


# ---------------------------------------------------------------------------
# 交易复盘
# ---------------------------------------------------------------------------
def test_review_contracts():
    from test_review import HEADER_A, ROWS_A, make_xlsx

    opened = _upload("/api/review/upload", make_xlsx(ROWS_A, HEADER_A, title_rows=2), "contract.xlsx").get_json()
    _validate(schemas.ReviewOpenResult, opened)
    _validate(schemas.ReviewOpenResult,
              client.post("/api/review/open", json={"name": "contract.xlsx"}).get_json())
    _validate(schemas.ReviewFiles, client.get("/api/review/files").get_json())
    detail = _validate(schemas.ReviewFilesDetail, client.get("/api/review/files/detail").get_json())
    assert detail.files and detail.files[0].error is None
    ov = _validate(schemas.ReviewOverview, client.get("/api/review/overview").get_json())
    assert ov.fileCount == 1
    day = opened["days"][0]
    _validate(schemas.ReviewDayTrades,
              client.get(f"/api/review/day-trades?reviewId={opened['reviewId']}&day={day}").get_json())


def test_review_overview_empty_state_contract():
    ov = _validate(schemas.ReviewOverview, client.get("/api/review/overview").get_json())
    assert ov.fileCount == 0


def test_review_day_kline_contract():
    csv = _tick_csv("fu2611", [("20261019210010", 100, 10), ("20261019210120", 101, 20),
                               ("20261020090010", 102, 5), ("20261020090120", 103, 9)])
    assert _upload("/api/depth/upload", csv, "fu2611.csv").status_code == 200
    j = client.get("/api/review/day-kline?symbol=fu2611&day=2026-10-20").get_json()
    m = _validate(schemas.ReviewDayKline, j)
    assert m.available is True and m.count == 4
    nodata = client.get("/api/review/day-kline?symbol=fu2611&day=2000-01-01").get_json()
    m = _validate(schemas.ReviewDayKline, nodata)
    assert m.available is False


# ---------------------------------------------------------------------------
# 深度行情
# ---------------------------------------------------------------------------
def test_depth_contracts():
    from test_depth_market import HEADER, ROWS, csv_bytes

    up = _upload("/api/depth/upload", csv_bytes(ROWS, HEADER), "contract.csv").get_json()
    _validate(schemas.DepthOpenResult, up)
    saved = up["savedName"]
    _validate(schemas.DepthOpenResult, client.post("/api/depth/open", json={"name": saved}).get_json())
    contracts = _validate(schemas.DepthContracts, client.get("/api/depth/contracts").get_json())
    assert contracts.contracts
    _validate(schemas.DepthOpenResult,
              client.post("/api/depth/open-contract", json={"symbol": contracts.contracts[0].symbol}).get_json())
    _validate(schemas.DepthFiles, client.get("/api/depth/files").get_json())
