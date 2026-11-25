#!/usr/bin/env python3
"""Flask 后端入口（Tauri sidecar）：只负责装配，业务在 routes / services / core。"""
import os
import sys

# 直接以脚本运行（python backend/app.py）时，把项目根目录加入 sys.path，
# 这样 `from backend import ...` 在开发、测试、PyInstaller 打包三种场景下都能工作。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from flask import Flask, Request, jsonify, request  # noqa: E402
from flask_cors import CORS  # noqa: E402

from backend import config  # noqa: E402
from backend.errors import ApiError  # noqa: E402
from backend.core import copy_trading  # noqa: E402
from backend.routes import init_runtime as routes_init_runtime  # noqa: E402
from backend.routes import register_blueprints  # noqa: E402
from backend.services import depth_service  # noqa: E402

MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB（复盘 Excel）


class _DepthRequest(Request):
    """MAX_CONTENT_LENGTH 是全局的（20MB，给复盘 Excel 用）；tick CSV 很大，只对深度行情上传放宽。
    新版 Flask 里 request.max_content_length 是只读属性，所以用子类按路径返回上限。"""

    @property
    def max_content_length(self):
        if self.path == '/api/depth/upload':
            return depth_service.DEPTH_MAX_UPLOAD
        if self.path == '/api/depth/upload-archive':
            return depth_service.DEPTH_MAX_ARCHIVE_UPLOAD
        return super().max_content_length

    @max_content_length.setter
    def max_content_length(self, value):   # 旧版 Flask 的基类构造里可能会赋值，忽略即可
        pass


def _api_error(status, message):
    return jsonify({"success": False, "message": message}), status


def _register_error_handlers(app):
    # 路由里 raise ApiError(...) 的统一出口，格式同以前手写的 jsonify({"success": False, "message": ...})
    @app.errorhandler(ApiError)
    def api_error(e):
        return e.to_response()

    # /api/ 下的 404、405、500 也统一返回 JSON + message。Flask 默认返回 HTML 页面，前端读不到 message，
    # 界面就只剩一句笼统的“xx失败”（比如后端是没重启的旧版本，缺少新接口时会返回 405）。
    @app.errorhandler(413)
    def too_large(_e):
        if request.path == '/api/depth/upload-archive':
            return jsonify({"success": False, "message": "压缩包过大，请上传 10GB 以内的文件"}), 413
        return jsonify({"success": False, "message": "文件过大，请上传 20MB 以内的文件"}), 413

    @app.errorhandler(404)
    def api_not_found(e):
        if request.path.startswith('/api/'):
            return _api_error(404, f"接口 {request.path} 不存在，可能是后端版本过旧，请重启后端")
        return e

    @app.errorhandler(405)
    def api_method_not_allowed(e):
        if request.path.startswith('/api/'):
            return _api_error(405, f"后端不支持 {request.method} {request.path}，可能是后端版本过旧，请重启后端")
        return e

    @app.errorhandler(500)
    def api_server_error(e):
        if request.path.startswith('/api/'):
            print(f"[Backend] 500 {request.method} {request.path}: {e}")
            return _api_error(500, "服务器内部错误，详细原因见后端日志")
        return e


def create_app():
    app = Flask(__name__)
    app.secret_key = os.urandom(24)
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
    app.request_class = _DepthRequest

    # 启用 CORS 支持（允许 Tauri WebView 访问）
    CORS(app, supports_credentials=True, origins=[
        'tauri://localhost',
        'https://tauri.localhost',
        'http://tauri.localhost',   # Tauri 2 在 Windows 上默认使用 http://tauri.localhost
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ])

    _register_error_handlers(app)
    register_blueprints(app)
    return app


# WSGI 应用对象：导入 backend.app 只会创建它（注册路由、错误处理），不读磁盘配置、不打印。
# 测试直接用 app.test_client()；需要期货公司列表 / CTP 参数的接口请先调用 init_runtime()。
app = create_app()


def init_runtime():
    """加载磁盘上的配置并恢复上次状态。只由入口调用，导入本模块不会触发。"""
    print(f"[Backend] 基础路径: {config.BASE_DIR}")
    routes_init_runtime()
    copy_trading.engine.load_saved_config()   # 恢复上次保存的跟单配置
    copy_trading.engine.load_saved_logs()     # 恢复历史运行日志（并清理 30 天前的）


class _SafeStream:
    """包一层 stdout / stderr：写失败（读端已关闭）时吞掉异常，而不是让进程崩溃。

    后端由 Tauri 拉起，stdout / stderr 是管道，Rust 侧的读取线程只要退出（应用被 `tauri dev` 重新编译时杀掉、
    窗口关闭、管道读端被回收），管道就变成「没人读」，之后任何一次 print / click.echo 都会抛
    `OSError: [Errno 22] Invalid argument`。Flask 的启动横幅（show_server_banner）就是这样把后端带崩的，
    表现为 `npm run dev` 里后端刚起来就退出、前端一直连不上。
    日志只是辅助信息，输出失败不应该影响服务本身，所以统一吞掉。
    """

    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        try:
            return self._stream.write(text)
        except (OSError, ValueError):   # ValueError: I/O operation on closed file
            return len(text)

    def flush(self):
        try:
            self._stream.flush()
        except (OSError, ValueError):
            pass

    def __getattr__(self, name):        # isatty / encoding / fileno 等其余属性原样转发
        return getattr(self._stream, name)


def _protect_stdio():
    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name, None)
        if stream is not None and not isinstance(stream, _SafeStream):
            setattr(sys, name, _SafeStream(stream))


def main():
    _protect_stdio()           # 必须在第一次 print 之前（init_runtime 里就会打印）
    port = config.get_port()   # 先校验端口，配置错误时尽早退出
    init_runtime()
    print("[Backend] Flask 后端启动中...")
    print(f"[Backend] 监听地址: http://{config.HOST}:{port}")
    app.run(host=config.HOST, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
