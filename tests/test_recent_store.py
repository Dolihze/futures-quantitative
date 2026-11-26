"""「最近使用」存储与策略总览合约下拉的接口测试：python -m pytest tests/test_recent_store.py -q

覆盖：最多 3 个且最新在前、重复选择只刷新位置、重启（新连接）后仍在、数据库故障不外抛，
以及 /api/backtest/contracts 的 recent / default、/api/backtest/recent-symbol 的校验。
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backend import app as backend  # noqa: E402
from backend.core import recent_store  # noqa: E402

KIND = recent_store.KIND_BACKTEST_SYMBOL


# ----------------------------------------------------------------------------
# 存储层
# ----------------------------------------------------------------------------

def test_touch_puts_latest_first_and_keeps_only_three():
    for s in ("a", "b", "c"):
        recent_store.touch(KIND, s)
    assert recent_store.recent(KIND) == ["c", "b", "a"]
    recent_store.touch(KIND, "d")                      # 第 4 个：最旧的 a 被挤掉
    assert recent_store.recent(KIND) == ["d", "c", "b"]


def test_touching_existing_value_moves_it_to_front_without_duplicates():
    for s in ("a", "b", "c"):
        recent_store.touch(KIND, s)
    assert recent_store.touch(KIND, "a") == ["a", "c", "b"]
    assert recent_store.recent(KIND) == ["a", "c", "b"]
    recent_store.touch(KIND, "a")                      # 连续重复选同一个：不增加、顺序不变
    assert recent_store.recent(KIND) == ["a", "c", "b"]


def test_rapid_touches_keep_a_deterministic_order(monkeypatch):
    # 时钟不前进（同一时刻连续点击）时也要有确定的先后，不能因为时间戳相同而乱序
    monkeypatch.setattr(recent_store.time, "time", lambda: 1000.0)
    for s in ("a", "b", "c"):
        recent_store.touch(KIND, s)
    assert recent_store.recent(KIND) == ["c", "b", "a"]
    recent_store.touch(KIND, "a")
    assert recent_store.recent(KIND) == ["a", "c", "b"]


def test_recent_survives_reconnect():
    # 入库：丢掉缓存的连接（相当于重启后端）后，数据仍在
    recent_store.touch(KIND, "fu2611")
    recent_store.touch(KIND, "rb2610")
    with recent_store._lock:
        recent_store._conn.close()
        recent_store._conn = None
        recent_store._conn_path = None
    assert recent_store.recent(KIND) == ["rb2610", "fu2611"]


def test_kinds_are_independent():
    recent_store.touch(KIND, "fu2611")
    recent_store.touch("other_kind", "x")
    assert recent_store.recent(KIND) == ["fu2611"] and recent_store.recent("other_kind") == ["x"]
    for s in ("1", "2", "3", "4"):
        recent_store.touch("other_kind", s)
    assert recent_store.recent(KIND) == ["fu2611"]    # 另一种用途挤满了也不影响这一种


def test_blank_value_ignored_and_remove():
    assert recent_store.touch(KIND, "  ") is None and recent_store.touch(KIND, None) is None
    recent_store.touch(KIND, "a")
    recent_store.remove(KIND, "a")
    recent_store.remove(KIND, "never-existed")         # 不存在也安全
    assert recent_store.recent(KIND) == []


def test_database_failure_never_raises(monkeypatch):
    def boom():
        raise OSError("disk full")

    monkeypatch.setattr(recent_store, "_connect", boom)
    assert recent_store.touch(KIND, "a") is None
    assert recent_store.recent(KIND) == []
    recent_store.remove(KIND, "a")                     # 都不抛异常


# ----------------------------------------------------------------------------
# 接口
# ----------------------------------------------------------------------------

client = backend.app.test_client()


@pytest.fixture(autouse=True)
def _depth_dir(monkeypatch, tmp_path):
    from backend.services import depth_service, kline_store, tick_store
    d = tmp_path / "depth_files"
    d.mkdir()
    monkeypatch.setenv("DEPTH_FILES_DIR", str(d))
    tick_store.reset_state()
    kline_store.clear_cache()
    yield


def _import(symbol):
    rows = ["symbol,name,time,current,volume,money,position",
            f"{symbol},测试,20261020090010000,100,10,10000,1000",
            f"{symbol},测试,20261020090120000,101,20,20000,1000"]
    r = client.post("/api/depth/upload",
                    data={"file": (io.BytesIO(("\n".join(rows) + "\n").encode("utf-8")), f"{symbol}.csv"),
                          "overwrite": "1"},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()


def _contracts():
    return client.get("/api/backtest/contracts").get_json()


def _record(symbol):
    return client.post("/api/backtest/recent-symbol", json={"symbol": symbol})


def test_no_usage_yet_defaults_to_first_library_contract():
    for s in ("fu2611", "rb2610"):
        _import(s)
    j = _contracts()
    assert j["recent"] == [] and j["default"] == "fu2611"     # 没有使用记录：退回库里第一个（按代码排序）


def test_default_is_most_recently_selected_contract():
    for s in ("fu2611", "rb2610", "hc2610"):
        _import(s)
    for s in ("hc2610", "rb2610"):
        assert _record(s).get_json()["success"]
    j = _contracts()
    assert j["recent"] == ["rb2610", "hc2610"] and j["default"] == "rb2610"   # 进页面加载最近的第一个
    assert [c["symbol"] for c in j["data"]] == ["fu2611", "hc2610", "rb2610"]  # 全部合约列表不受影响


def test_record_returns_latest_list_and_caps_at_three():
    for s in ("fu2611", "rb2610", "hc2610", "ag2612"):
        _import(s)
    last = None
    for s in ("fu2611", "rb2610", "hc2610", "ag2612"):
        last = _record(s).get_json()
    assert last["recent"] == ["ag2612", "hc2610", "rb2610"]   # 4 个只留最近 3 个，fu2611 被挤掉
    assert _contracts()["recent"] == ["ag2612", "hc2610", "rb2610"]


def test_record_matches_symbol_case_insensitively_and_stores_library_spelling():
    _import("fu2611")
    r = _record("FU2611").get_json()
    assert r["success"] and r["recent"] == ["fu2611"]          # 大小写不敏感，存的是库里的写法
    # 带交易所前缀的不是库里的写法：明确拒绝，也不写入
    assert _record("SHFE.fu2611").status_code == 404
    assert _contracts()["recent"] == ["fu2611"]


def test_record_rejects_unknown_or_blank_symbol():
    _import("fu2611")
    bad = _record("")
    assert bad.status_code == 400 and bad.get_json()["success"] is False
    miss = _record("zz9999")
    assert miss.status_code == 404 and miss.get_json()["success"] is False
    assert _contracts()["recent"] == []                        # 失败的请求不会写进去


def test_deleted_contract_disappears_from_recent_and_default():
    for s in ("fu2611", "rb2610"):
        _import(s)
    _record("fu2611")
    _record("rb2610")
    assert _contracts()["default"] == "rb2610"
    # 走真实的「数据库管理 → 删除合约」接口，把 rb2610 从行情库里删掉
    r = client.delete("/api/depth/contracts", json={"symbol": "rb2610"})
    assert r.status_code == 200 and r.get_json()["success"], r.get_json()
    j = _contracts()
    assert [c["symbol"] for c in j["data"]] == ["fu2611"]       # rb2610 确实已经不在库里
    # 已删除的合约不能留在 recent / default 里，否则默认会去加载一个不存在的合约
    assert j["recent"] == ["fu2611"] and j["default"] == "fu2611"


def test_empty_library_still_works():
    j = _contracts()
    assert j["data"] == [] and j["recent"] == [] and j["default"] == ""
