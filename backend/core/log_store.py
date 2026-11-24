"""跟单运行日志的本地数据库（SQLite）。

日志写进 %LOCALAPPDATA%\\futures-quantitative\\copy_logs.db（与 copy_config.json 同目录，不在项目目录里），
关闭客户端后不会丢失；启动时自动清理超过保留期的旧日志。

原则：日志只是辅助信息，任何数据库错误都只打印，绝不向外抛，不能影响跟单本身。
"""
import os
import sqlite3
import threading
import time

DB_FILENAME = "copy_logs.db"
RETENTION_DAYS = 30

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
        "CREATE TABLE IF NOT EXISTS run_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " ts REAL NOT NULL,"
        " level TEXT NOT NULL,"
        " msg TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_logs_ts ON run_logs(ts)")
    conn.commit()
    _conn, _conn_path = conn, path
    return conn


def add(ts, level, msg):
    """写入一条日志。失败返回 False（只打印）。"""
    try:
        with _lock:
            conn = _connect()
            conn.execute("INSERT INTO run_logs (ts, level, msg) VALUES (?, ?, ?)", (ts, level, msg))
            conn.commit()
        return True
    except (sqlite3.Error, OSError) as e:
        print(f"[Copy] 日志写入数据库失败: {e}")
        return False


def recent(limit):
    """最近 limit 条日志，最新在前：[{ts, level, msg}]。失败返回 []。"""
    try:
        with _lock:
            rows = _connect().execute(
                "SELECT ts, level, msg FROM run_logs ORDER BY ts DESC, id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [{"ts": r[0], "level": r[1], "msg": r[2]} for r in rows]
    except (sqlite3.Error, OSError) as e:
        print(f"[Copy] 日志读取失败: {e}")
        return []


def all_logs():
    """保留期内的全部日志，时间正序（旧 -> 新），用于导出。失败返回 []。"""
    try:
        with _lock:
            rows = _connect().execute(
                "SELECT ts, level, msg FROM run_logs ORDER BY ts ASC, id ASC"
            ).fetchall()
        return [{"ts": r[0], "level": r[1], "msg": r[2]} for r in rows]
    except (sqlite3.Error, OSError) as e:
        print(f"[Copy] 日志读取失败: {e}")
        return []


def purge_old(days=RETENTION_DAYS):
    """删除 days 天前的日志，返回删除条数。失败返回 0。"""
    try:
        with _lock:
            conn = _connect()
            cur = conn.execute("DELETE FROM run_logs WHERE ts < ?", (time.time() - days * 86400,))
            conn.commit()
            return cur.rowcount
    except (sqlite3.Error, OSError) as e:
        print(f"[Copy] 清理旧日志失败: {e}")
        return 0
