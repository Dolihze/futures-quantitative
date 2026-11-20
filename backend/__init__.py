"""期货量化交易系统 Python 后端（Tauri sidecar）。

分层：
  app.py       应用工厂与入口（装配 CORS、错误处理、Blueprint、监听端口）
  config.py    路径、端口等运行环境配置
  routes/      HTTP 路由（Blueprint），按业务域拆分，文件名 <域>_routes.py
  services/    文件夹扫描、内存缓存等应用服务，文件名 <域>_service.py
  core/        与 Flask 无关的领域逻辑（复盘、深度行情、回测、CTP、跟单、凭据），沿用业务名

依赖方向只能是 routes -> services -> core，不能反过来。
同一业务域的文件名各带本层后缀，保证全项目文件名唯一：
  routes/review_routes.py -> services/review_service.py -> core/review.py
"""
