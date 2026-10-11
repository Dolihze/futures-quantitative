@echo off
chcp 65001 >nul
color 0B
echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║                                                           ║
echo ║         期货量化交易系统 - 一键启动脚本                  ║
echo ║                                                           ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.

REM ========================================
REM 检查 Python 环境
REM ========================================
echo [1/4] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python
    echo.
    pause
    exit /b 1
)
echo [✓] Python 已安装
echo.

REM ========================================
REM 检查 Node.js 环境
REM ========================================
echo [2/4] 检查 Node.js 环境...
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js
    echo.
    pause
    exit /b 1
)
echo [✓] Node.js 已安装
echo.

REM ========================================
REM 检查前端依赖
REM ========================================
echo [3/4] 检查前端依赖...
if not exist "frontend\node_modules" (
    echo [提示] 首次运行，正在安装前端依赖（可能需要几分钟）...
    cd frontend
    npm install
    if errorlevel 1 (
        echo [错误] 前端依赖安装失败
        cd ..
        pause
        exit /b 1
    )
    cd ..
    echo [✓] 前端依赖安装完成
) else (
    echo [✓] 前端依赖已存在
)
echo.

REM ========================================
REM 启动前后端服务
REM ========================================
echo [4/4] 正在启动前后端服务...
echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║  提示：                                                   ║
echo ║  - 后端将在新窗口启动（Flask + 桌面窗口）                ║
echo ║  - 前端将在另一个新窗口启动（Vue 开发服务器）            ║
echo ║  - 关闭此窗口不会停止服务                                 ║
echo ║  - 要停止服务，请关闭对应的命令行窗口                    ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.

REM 启动后端（新窗口）
echo [启动后端] Flask 服务器 + 桌面窗口...
start "期货量化 - 后端服务" cmd /k "title 期货量化 - 后端服务 && color 0A && echo. && echo ══════════════════════════════════════════ && echo   后端服务已启动 && echo   Flask: http://127.0.0.1:5000 && echo   桌面窗口已创建 && echo ══════════════════════════════════════════ && echo. && python app.py"

REM 等待2秒让后端先启动
timeout /t 2 /nobreak >nul

REM 启动前端（新窗口）
echo [启动前端] Vue 开发服务器...
start "期货量化 - 前端服务" cmd /k "title 期货量化 - 前端服务 && color 0E && cd frontend && echo. && echo ══════════════════════════════════════════ && echo   前端服务已启动 && echo   访问地址: http://localhost:5173 && echo   按 Ctrl+C 可停止服务 && echo ══════════════════════════════════════════ && echo. && npm run dev"

echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║                                                           ║
echo ║   ✓ 前后端服务启动成功！                                 ║
echo ║                                                           ║
echo ║   前端访问地址：                                          ║
echo ║   → http://localhost:5173                                ║
echo ║                                                           ║
echo ║   后端 API 地址：                                         ║
echo ║   → http://127.0.0.1:5000                                ║
echo ║                                                           ║
echo ║   提示：                                                  ║
echo ║   - 请等待几秒让服务完全启动                             ║
echo ║   - 可以关闭此窗口，服务会继续运行                         ║
echo ║   - 要停止服务，请关闭对应的命令行窗口                    ║
echo ║                                                           ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.
echo 按任意键关闭此窗口（服务会继续运行）...
pause >nul
