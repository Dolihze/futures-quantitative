"""「最近使用」记录的本地数据库（SQLite）。

目前只用于策略总览的合约下拉框：记住用户最近手动选过的合约，最多保留 MAX_RECENT 个，最新的在最前。
写进 %LOCALAPPDATA%\\futures-quantitative\\recent.db（与 copy_logs.db 同目录，不在项目目录里），
关闭客户端后不丢。表按 kind 区分用途，以后别的下拉框也要「最近使用」时直接换一个 kind 即可。

原则同 log_store：这只是辅助体验，任何数据库错误都只打印，绝不向外抛，不能影响回测本身。
"""
import os
import sqlite3
import threading
import time

DB_FILENAME = "recent.db"
MAX_RECENT = 3
KIND_BACKTEST_SYMBOL = "backtest_symbol"

_lock = threading.Lock()
_conn = None
_conn_path = None


def db_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "futures-quantitative", DB_FILENAME)


def _connect():
    """取得（必要时建立）连接。调用方须持有 _lock。路径变化（如测试改了 LOCALAPPDATA）时重连。"""
    global _conn, _conn_path
    path = db_path()
    if _conn is not None and _conn_path == path:
        return _conn
    if _conn is not None:
        try:
            _conn.close()
        except sqlite3.Error:
            pass
        _conn = None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=5)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS recent_items ("
        " kind TEXT NOT NULL,"
        " value TEXT NOT NULL,"
        " used_at REAL NOT NULL,"
        " PRIMARY KEY (kind, value))"
    )
    conn.commit()
    _conn, _conn_path = conn, path
    return conn


def touch(kind, value):
    """记一次使用：已有则刷新时间（移到最前），没有则新增；超出 MAX_RECENT 的最旧记录删掉。
    返回最新的列表（最新在前）；失败返回 None（只打印）。"""
    value = str(value or "").strip()
    if not value:
        return None
    try:
        with _lock:
            conn = _connect()
            # 同一毫秒内连续点击也要有确定的先后：时间戳至少比库里最新的一条大一点
            row = conn.execute("SELECT MAX(used_at) FROM recent_items WHERE kind = ?", (kind,)).fetchone()
            now = max(time.time(), (row[0] or 0) + 1e-6)
            conn.execute(
                "INSERT INTO recent_items (kind, value, used_at) VALUES (?, ?, ?) "
                "ON CONFLICT(kind, value) DO UPDATE SET used_at = excluded.used_at",
                (kind, value, now),
            )
            conn.execute(
                "DELETE FROM recent_items WHERE kind = ? AND value NOT IN ("
                " SELECT value FROM recent_items WHERE kind = ? ORDER BY used_at DESC LIMIT ?)",
                (kind, kind, MAX_RECENT),
            )
            conn.commit()
            return _recent(conn, kind)
    except (sqlite3.Error, OSError) as e:
        print(f"[Recent] 写入失败: {e}")
        return None


def _recent(conn, kind):
    rows = conn.execute(
        "SELECT value FROM recent_items WHERE kind = ? ORDER BY used_at DESC LIMIT ?", (kind, MAX_RECENT)
    ).fetchall()
    return [r[0] for r in rows]


def recent(kind):
    """最近使用的值，最新在前，最多 MAX_RECENT 个。失败返回 []。"""
    try:
        with _lock:
            return _recent(_connect(), kind)
    except (sqlite3.Error, OSError) as e:
        print(f"[Recent] 读取失败: {e}")
        return []


def remove(kind, value):
    """删除一条记录（不存在也安全）。失败只打印。"""
    try:
        with _lock:
            conn = _connect()
            conn.execute("DELETE FROM recent_items WHERE kind = ? AND value = ?", (kind, str(value or "").strip()))
            conn.commit()
    except (sqlite3.Error, OSError) as e:
        print(f"[Recent] 删除失败: {e}")
