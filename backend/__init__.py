"""期货量化交易系统 Python 后端（Tauri sidecar）。

分层：
  app.py       应用工厂与入口（装配 CORS、错误处理、Blueprint、监听端口）
  config.py    路径、端口等运行环境配置
  routes/      HTTP 路由（Blueprint），按业务域拆分
  services/    文件夹扫描、内存缓存等应用服务
  core/        与 Flask 无关的领域逻辑（复盘、深度行情、回测、CTP、跟单、凭据）
"""
