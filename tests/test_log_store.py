"""运行日志持久化（SQLite）测试：python -m pytest tests/test_log_store.py -q"""
import io
import os
import sys
import time

import pytest
from openpyxl import load_workbook

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backend.app import app  # noqa: E402
from backend.core import copy_trading as ct  # noqa: E402
from backend.core import log_store  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


def test_log_is_written_to_db():
    e = ct.CopyEngine()
    e.log("跟单已启动")
    e.log("下单失败", "error")
    rows = log_store.recent(10)
    assert [(r["level"], r["msg"]) for r in rows] == [("error", "下单失败"), ("info", "跟单已启动")]


def test_logs_survive_restart():
    e1 = ct.CopyEngine()
    e1.log("第一条")
    e1.log("第二条", "warn")

    e2 = ct.CopyEngine()          # 模拟重启客户端：新引擎、内存是空的
    assert e2.get_logs() == []
    e2.load_saved_logs()
    logs = e2.get_logs()
    assert [(l["level"], l["msg"]) for l in logs] == [("warn", "第二条"), ("info", "第一条")]   # 最新在前
    assert all(l["time"] and l["ts"] for l in logs)


def test_load_saved_logs_limited_to_max_logs(monkeypatch):
    monkeypatch.setattr(ct, "MAX_LOGS", 3)
    e = ct.CopyEngine()
    for i in range(5):
        e.log(f"log{i}")
    e2 = ct.CopyEngine()
    e2.load_saved_logs()
    assert [l["msg"] for l in e2.get_logs()] == ["log4", "log3", "log2"]
    assert len(log_store.all_logs()) == 5       # 数据库里仍是完整的


def test_purge_old_logs_on_startup():
    day = 86400
    log_store.add(time.time() - 31 * day, "info", "31天前")
    log_store.add(time.time() - 29 * day, "info", "29天前")
    log_store.add(time.time(), "info", "刚刚")
    e = ct.CopyEngine()
    e.load_saved_logs()
    assert [l["msg"] for l in e.get_logs()] == ["刚刚", "29天前"]
    assert [r["msg"] for r in log_store.all_logs()] == ["29天前", "刚刚"]


def test_db_failure_does_not_break_logging(monkeypatch):
    def boom():
        raise OSError("disk full")
    monkeypatch.setattr(log_store, "_connect", boom)
    e = ct.CopyEngine()
    e.log("数据库坏了也不能影响跟单")           # 不抛异常
    assert e.get_logs()[0]["msg"] == "数据库坏了也不能影响跟单"
    assert log_store.recent(10) == []
    assert log_store.purge_old() == 0


def test_export_includes_full_history_with_date():
    # 导出的是数据库里的全部历史（超过界面显示的 MAX_LOGS），时间带日期，正序
    e = ct.CopyEngine()
    for i in range(ct.MAX_LOGS + 20):
        e.log(f"msg{i}")
    app.config["TESTING"] = True
    r = app.test_client().get("/api/monitor/logs/export")
    ws = load_workbook(io.BytesIO(r.data)).active
    rows = [[c.value for c in row] for row in ws.iter_rows()]
    assert rows[0] == ["时间", "级别", "内容"]
    assert len(rows) == 1 + ct.MAX_LOGS + 20
    assert rows[1][2] == "msg0" and rows[-1][2] == f"msg{ct.MAX_LOGS + 19}"
    assert len(rows[1][0]) == len("2026-01-01 00:00:00")
