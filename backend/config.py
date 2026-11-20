"""运行环境配置：基础目录、数据文件查找、监听地址。

端口由 Tauri 在启动 sidecar 时选好空闲端口并通过环境变量 BACKEND_PORT 传入；
单独运行（python backend/app.py）时没有该变量，回退到 DEFAULT_PORT，与 Vite 代理默认值一致。
"""
import os
import sys

HOST = '127.0.0.1'
DEFAULT_PORT = 5000
PORT_ENV = 'BACKEND_PORT'

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_port() -> int:
    raw = os.environ.get(PORT_ENV, '').strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        raise SystemExit(f'{PORT_ENV} 必须是整数，当前值：{raw!r}')
    if not 1 <= port <= 65535:
        raise SystemExit(f'{PORT_ENV} 超出范围 1-65535：{port}')
    return port


def get_base_dir() -> str:
    """打包后 = 可执行文件所在目录；开发模式 = 项目根目录（data/ 所在处）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return PROJECT_ROOT


BASE_DIR = get_base_dir()


def find_data_file(*parts):
    """按优先级查找数据文件：PyInstaller 内置资源 > exe 同级目录 > 向上回溯（开发模式）> 当前工作目录。"""
    candidates = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(os.path.join(meipass, *parts))
    candidates.append(os.path.join(BASE_DIR, *parts))
    cur = BASE_DIR
    for _ in range(5):
        candidates.append(os.path.join(cur, *parts))
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    candidates.append(os.path.join(os.getcwd(), *parts))
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]
