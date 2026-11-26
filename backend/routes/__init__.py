"""HTTP 路由层：每个业务域一个 Blueprint，只做参数解析与响应组装，业务逻辑在 services / core。

命名约定：三层里同一业务域的文件名带各自层的后缀，保证在整个项目里文件名唯一
（标签页、搜索结果、报错堆栈里一眼能看出是哪一层）：
    routes/review_routes.py  ->  services/review_service.py  ->  core/review.py
core 是最底层的领域逻辑，沿用业务本身的名字（review、depth_market、ctp_service ...），不加后缀。
Blueprint 的名字（'review'、'depth' ...）不带后缀，它是路由 endpoint 的前缀，会出现在 OpenAPI 的 operationId / tags 里。
"""
from flask import Flask


def register_blueprints(app: Flask) -> None:
    from backend.routes import (account_routes, backtest_routes, calendar_routes, depth_routes,
                                monitor_routes, review_routes, trading_routes)

    for module in (account_routes, trading_routes, backtest_routes, review_routes, monitor_routes, depth_routes,
                   calendar_routes):
        app.register_blueprint(module.bp)


def init_runtime() -> None:
    """加载磁盘上的配置（期货公司列表、CTP 接入参数）。

    刻意不放在 import 或 create_app() 里：测试 / 打包分析只需要路由，不应读取用户磁盘上的配置。
    由入口（app.py 的 main()）显式调用。
    """
    from backend.routes import account_routes

    account_routes.init()
