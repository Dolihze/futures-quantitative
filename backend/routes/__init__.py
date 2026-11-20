"""HTTP 路由层：每个业务域一个 Blueprint，只做参数解析与响应组装，业务逻辑在 services / core。"""
from flask import Flask


def register_blueprints(app: Flask) -> None:
    from backend.routes import account, backtest, depth, monitor, review, trading

    for module in (account, trading, backtest, review, monitor, depth):
        app.register_blueprint(module.bp)


def init_runtime() -> None:
    """加载磁盘上的配置（期货公司列表、CTP 接入参数）。

    刻意不放在 import 或 create_app() 里：测试 / 打包分析只需要路由，不应读取用户磁盘上的配置。
    由入口（app.py 的 main()）显式调用。
    """
    from backend.routes import account

    account.init()
