"""交易日历：缓存 / 离线回退 / 缺失交易日 / 接口。联网拉取一律用假数据（conftest 已禁网）。"""
import datetime as dt
import json
import time

import pytest

from backend.app import app
from backend.services import calendar_service as cal

client = app.test_client()


def _weekdays(start, end, skip=()):
    """start~end 内除周末和 skip 外的日期（模拟交易日历）。"""
    out, d = [], dt.date.fromisoformat(start)
    last = dt.date.fromisoformat(end)
    while d <= last:
        s = d.isoformat()
        if d.weekday() < 5 and s not in skip:
            out.append(s)
        d += dt.timedelta(days=1)
    return out


# 2026-10-01 ~ 10-07 国庆休市；日历前面补足年份，满足「条数不能太少」的合理性检查
HOLIDAYS = {f"2026-10-0{i}" for i in range(1, 8)}
FAKE = _weekdays("2018-01-01", "2026-12-31", skip=HOLIDAYS)


@pytest.fixture
def fake_net(monkeypatch):
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return list(FAKE)

    monkeypatch.setattr(cal, "_fetch", fetch)
    return calls


def test_load_fetches_then_uses_cache_without_network(fake_net):
    a = cal.load()
    assert a["stale"] is False and "2026-10-08" in a["days"] and "2026-10-02" not in a["days"]
    assert fake_net["n"] == 1
    cal.reset_memory()          # 模拟重启：只剩磁盘缓存
    b = cal.load()
    assert b["days"] == a["days"] and fake_net["n"] == 1   # 没再联网


def test_expired_cache_refreshes_and_offline_falls_back_to_stale(fake_net, monkeypatch):
    cal.load()
    path = cal.cache_path()
    old = json.load(open(path, encoding="utf-8"))
    old["fetchedAt"] = time.time() - cal.CACHE_TTL - 10
    json.dump(old, open(path, "w", encoding="utf-8"))
    cal.reset_memory()

    def down():
        raise OSError("offline")

    monkeypatch.setattr(cal, "_fetch", down)
    r = cal.load()
    assert r is not None and r["stale"] is True and r["days"] == old["days"]   # 断网：用旧缓存


def test_no_cache_and_offline_returns_none():
    assert cal.load() is None
    assert cal.missing_days(["2026-10-08", "2026-10-12"]) is None   # 不联网，缓存也没有 -> 不判断


def test_failure_is_not_retried_immediately(monkeypatch):
    n = {"c": 0}

    def down():
        n["c"] += 1
        raise OSError("offline")

    monkeypatch.setattr(cal, "_fetch", down)
    assert cal.load() is None and cal.load() is None
    assert n["c"] == 1   # 第二次在 RETRY_AFTER 内，不再卡一次超时


def test_implausibly_small_calendar_is_rejected(monkeypatch):
    monkeypatch.setattr(cal, "_fetch", lambda: (_ for _ in ()).throw(ValueError("too few")))
    assert cal.load() is None


def test_missing_days_excludes_weekends_and_holidays(fake_net):
    cal.load()
    # 09-30(三) 与 10-08(四) 之间是国庆，不算缺；10-09(五) 导入了，10-12(一) 缺，10-13 导入
    got = cal.missing_days(["2026-09-29", "2026-09-30", "2026-10-08", "2026-10-09", "2026-10-13"])
    assert got == ["2026-10-12"]


def test_missing_days_empty_and_contiguous(fake_net):
    cal.load()
    assert cal.missing_days([]) == []
    assert cal.missing_days(["2026-10-08", "2026-10-09", "2026-10-12"]) == []   # 跨周末不缺


def test_cached_never_touches_network(monkeypatch):
    def boom():
        raise AssertionError("cached() must not fetch synchronously")

    monkeypatch.setattr(cal, "_fetch", boom)
    monkeypatch.setattr(cal, "refresh_in_background", lambda: None)
    assert cal.cached() is None


def test_api_trading_days(fake_net):
    j = client.get("/api/calendar/trading-days?start=2026-09-30&end=2026-10-12").get_json()
    assert j["success"] and j["tradingDays"] == ["2026-09-30", "2026-10-08", "2026-10-09", "2026-10-12"]
    assert "2026-10-03" in j["closedDays"] and "2026-10-10" in j["closedDays"]   # 国庆 + 周末
    assert "2026-10-08" not in j["closedDays"] and j["coveredTo"] == "2026-12-31" and j["stale"] is False


def test_api_beyond_coverage_is_not_reported_closed(fake_net):
    j = client.get("/api/calendar/trading-days?start=2026-12-30&end=2027-01-05").get_json()
    assert j["tradingDays"] == ["2026-12-30", "2026-12-31"]
    assert j["closedDays"] == [] and j["coveredTo"] == "2026-12-31"   # 2027 年无数据：不能说它休市


def test_api_validation_and_unavailable():
    assert client.get("/api/calendar/trading-days?start=abc&end=2026-10-12").status_code == 400
    assert client.get("/api/calendar/trading-days?start=2026-10-12&end=2026-10-01").status_code == 400
    assert client.get("/api/calendar/trading-days?start=2000-01-01&end=2026-10-01").status_code == 400
    r = client.get("/api/calendar/trading-days?start=2026-10-01&end=2026-10-12")   # 没缓存、断网
    assert r.status_code == 503 and r.get_json()["success"] is False
