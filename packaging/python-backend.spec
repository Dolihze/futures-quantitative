# -*- mode: python ; coding: utf-8 -*-
# 后端打包定义（onedir）。入口：npm run backend:build
#
# 为什么用 onedir 而不是 onefile：
#   onefile 每次启动都要把全部依赖解压到临时目录（pandas/vnpy 体积大，要十几秒到几十秒）；
#   onedir 在安装时就已展开，启动只是加载，几秒内可用。
#
# 输出：src-tauri/backend-dist/python-backend[.exe] 及其 _internal/，由 tauri.conf.json 的 resources 打进安装包。
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

# SPECPATH 是本 spec 所在目录（packaging/），项目根在上一级
ROOT = Path(SPECPATH).resolve().parent

datas = [(str(ROOT / 'data'), 'data')]
binaries = []
hiddenimports = ['vnpy.trader.engine', 'vnpy.trader.setting', 'vnpy.trader.event']
hiddenimports += collect_submodules('talib')
tmp_ret = collect_all('vnpy_ctp')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
# 交易日历（backend/services/calendar_service.py）：akshare 的 tool_trade_date_hist_sina 用 py_mini_racer 执行 JS 解码，
# 需要它的 mini_racer.dll / icudtl.dat。akshare 的 __init__ 会导入全部子模块，所以用 collect_all 带全依赖；
# 它在 calendar_service 里是延迟导入的，只有真联网拉日历时才会加载，不拖慢后端启动。
for _pkg in ('akshare', 'py_mini_racer'):
    _ret = collect_all(_pkg)
    datas += _ret[0]
    binaries += _ret[1]
    hiddenimports += _ret[2]

a = Analysis(
    [str(ROOT / 'backend' / 'app.py')],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'tensorflow', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir：二进制与数据交给下面的 COLLECT
    name='python-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX 压缩会拖慢加载，还常触发杀软误报
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='python-backend',
)
