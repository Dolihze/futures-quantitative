"""全部测试共用的隔离：绝不允许测试读写真实用户的本地数据。

跟单引擎的配置 / 运行日志 / 记住的账号凭据都放在 %LOCALAPPDATA%\\futures-quantitative 下。
如果某个测试没有单独隔离（或在 fixture 之外被单独运行），引擎的 log() 会把测试产生的日志
（例如看门狗测试里的「跟单已自动暂停」）写进真实的 copy_logs.db，污染用户的运行日志。

这里用 autouse fixture 兜底：每个测试都把 LOCALAPPDATA 指向独立的临时目录，
并在前后重置 log_store 的模块级连接缓存，避免连接继续指向上一个测试（或真实）的数据库。
各测试文件里自己的 monkeypatch.setenv 仍然可以覆盖它，互不冲突。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backend.core import log_store, recent_store  # noqa: E402


def _reset_sqlite_stores():
    """关闭并丢弃各 SQLite 存储缓存的模块级连接，下次使用时按当前 LOCALAPPDATA 重新建立。"""
    for store in (log_store, recent_store):
        with store._lock:
            if store._conn is not None:
                try:
                    store._conn.close()
                except Exception:  # noqa: BLE001
                    pass
            store._conn = None
            store._conn_path = None


@pytest.fixture(autouse=True)
def _isolate_local_appdata(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path_factory.mktemp("localappdata")))
    _reset_sqlite_stores()
    yield
    _reset_sqlite_stores()


@pytest.fixture(autouse=True)
def _isolate_trading_calendar(tmp_path_factory, monkeypatch):
    """交易日历：缓存文件指到临时目录，联网拉取默认直接失败（测试绝不访问网络、不写真实缓存）。
    要用日历的测试自己 monkeypatch calendar_service._fetch 返回假数据。"""
    from backend.services import calendar_service

    def no_network():
        raise OSError("tests must not hit the network")

    monkeypatch.setenv("TRADING_CALENDAR_FILE", str(tmp_path_factory.mktemp("calendar") / "cal.json"))
    monkeypatch.setattr(calendar_service, "_fetch", no_network)
    calendar_service.reset_memory()
    yield
    calendar_service.reset_memory()
