@echo off
chcp 65001 >nul
color 0C
echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║                                                           ║
echo ║         期货量化交易系统 - 一键停止脚本                  ║
echo ║                                                           ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.

echo [提示] 正在停止所有服务...
echo.

REM 关闭后端窗口
echo [1/2] 停止后端服务...
taskkill /FI "WINDOWTITLE eq 期货量化 - 后端服务*" /F >nul 2>&1
if errorlevel 1 (
    echo [×] 后端服务未运行或已停止
) else (
    echo [✓] 后端服务已停止
)

REM 关闭前端窗口
echo [2/2] 停止前端服务...
taskkill /FI "WINDOWTITLE eq 期货量化 - 前端服务*" /F >nul 2>&1
if errorlevel 1 (
    echo [×] 前端服务未运行或已停止
) else (
    echo [✓] 前端服务已停止
)

REM 关闭可能残留的 webview 窗口
taskkill /FI "WINDOWTITLE eq 期货量化交易系统" /F >nul 2>&1
if errorlevel 1 (
    echo [×] 桌面窗口未运行或已停止
) else (
    echo [✓] 桌面窗口已停止
)

echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║                                                           ║
echo ║   ✓ 所有服务已停止                                        ║
echo ║                                                           ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.
echo 按任意键关闭此窗口...
pause >nul
