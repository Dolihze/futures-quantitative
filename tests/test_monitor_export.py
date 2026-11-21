"""运行日志导出 Excel 的接口测试：python -m pytest tests/test_monitor_export.py -q"""
import io
import os
import sys

import pytest
from openpyxl import load_workbook

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backend.app import app  # noqa: E402
from backend.core import copy_trading  # noqa: E402


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def _set_logs(monkeypatch, logs):
    monkeypatch.setattr(copy_trading.engine, "get_logs", lambda: logs)


def test_export_logs_xlsx(client, monkeypatch):
    # 引擎里是「最新在前」，导出应按时间正序
    _set_logs(monkeypatch, [
        {"time": "10:00:02", "level": "error", "msg": "下单失败：资金不足"},
        {"time": "10:00:01", "level": "warn", "msg": "对方成交，延迟较大"},
        {"time": "10:00:00", "level": "info", "msg": "跟单已启动"},
    ])
    r = client.get("/api/monitor/logs/export")
    assert r.status_code == 200
    assert r.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment" in r.headers["Content-Disposition"]

    ws = load_workbook(io.BytesIO(r.data)).active
    rows = [[c.value for c in row] for row in ws.iter_rows()]
    assert rows == [
        ["时间", "级别", "内容"],
        ["10:00:00", "信息", "跟单已启动"],
        ["10:00:01", "警告", "对方成交，延迟较大"],
        ["10:00:02", "错误", "下单失败：资金不足"],
    ]


def test_export_logs_empty_still_valid_xlsx(client, monkeypatch):
    _set_logs(monkeypatch, [])
    r = client.get("/api/monitor/logs/export")
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.data)).active
    assert [[c.value for c in row] for row in ws.iter_rows()] == [["时间", "级别", "内容"]]
