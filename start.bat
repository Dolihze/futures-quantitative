@echo off
chcp 65001 >nul
echo ==========================================
echo 期货量化交易系统 - 量化回测
echo ==========================================
echo.

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python环境，请先安装Python
    pause
    exit /b 1
)

echo [提示] 正在启动量化回测系统...
echo.

REM 启动应用
python app.py

pause
