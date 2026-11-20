"""统一的接口错误：路由里 `raise ApiError(...)`，由 app.py 注册的处理器转成 JSON。

响应格式保持和以前手写的 `jsonify({"success": False, "message": ...}), status` 完全一致，
额外字段（exists / fileMissing / expired ...）通过 **extra 传入，前端据此做分支处理。
"""
import functools
import traceback

from flask import jsonify


class ApiError(Exception):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra

    def to_response(self):
        return jsonify({"success": False, "message": self.message, **self.extra}), self.status


def bad_request(message, **extra):
    return ApiError(message, 400, **extra)


def not_found(message, **extra):
    return ApiError(message, 404, **extra)


def wrap_errors(prefix, *, log_tag, sep='：', status=500, trace=False, log_prefix=None):
    """把路由里未预期的异常统一转成 `<prefix><sep><原因>` 的 JSON 错误并记日志。

    - ApiError 原样放行（它自己就是要返回的错误，由 app.py 的处理器转响应）。
    - sep 是前缀和原因之间的分隔符，默认全角冒号；个别接口历史上用的是 ASCII 冒号，保持不变以免前端文案变化。
    - log_prefix 默认等于 prefix，用于日志和用户提示文案不同的接口。
    - trace=True 时在后端日志里附带堆栈。
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ApiError:
                raise
            except Exception as e:  # noqa: BLE001
                print(f"{log_tag} {log_prefix or prefix}: {e}")
                if trace:
                    traceback.print_exc()
                return ApiError(f"{prefix}{sep}{e}", status).to_response()
        return wrapper
    return decorator
