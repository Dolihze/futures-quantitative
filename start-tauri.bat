@echo off
chcp 65001 >nul
title 期货量化交易系统 - Tauri

echo ================================
echo   期货量化交易系统 - Tauri 2.x
echo ================================
echo.

echo 正在验证环境...

REM 检查 Rust
rustc --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Rust 未安装
    echo 请先安装 Rust: winget install Rustlang.Rustup
    pause
    exit /b 1
)
echo [√] Rust 已安装

REM 检查 Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Node.js 未安装
    echo 请先安装 Node.js: winget install OpenJS.NodeJS
    pause
    exit /b 1
)
echo [√] Node.js 已安装

echo.
echo 检查前端依赖...

REM 检查 node_modules
if not exist "frontend\node_modules" (
    echo 首次运行，正在安装前端依赖...
    cd frontend
    call npm install
    if errorlevel 1 (
        echo [错误] 前端依赖安装失败
        cd ..
        pause
        exit /b 1
    )
    cd ..
    echo [√] 前端依赖安装完成
) else (
    echo [√] 前端依赖已安装
)

echo.
echo 检查 Python Sidecar...

REM 检查 sidecar
if not exist "src-tauri\sidecar\python-backend.exe" (
    echo [警告] Python Sidecar 未找到
    echo 正在打包 Python 后端...
    
    REM 安装 Python 依赖
    pip list | findstr "flask" >nul
    if errorlevel 1 (
        echo 安装 Python 依赖...
        pip install flask flask-cors akshare pandas
    )
    
    REM 打包
    call npm run backend:build
    if errorlevel 1 (
        echo [错误] Python 后端打包失败
        pause
        exit /b 1
    )
    echo [√] Python 后端打包完成
) else (
    echo [√] Python Sidecar 已存在
)

echo.
echo 检查数据文件...
if not exist "data\brokers.json" (
    echo [错误] 数据文件未找到: data\brokers.json
    pause
    exit /b 1
)
echo [√] 数据文件就绪

echo.
echo ================================
echo   准备启动 Tauri 开发环境
echo ================================
echo.
echo 启动提示：
echo   - 首次启动需要编译 Rust 依赖（3-5 分钟）
echo   - 按 F12 打开开发者工具
echo   - 按 Ctrl+C 停止服务
echo.

set /p choice="是否启动？(Y/N): "
if /i not "%choice%"=="Y" (
    echo 已取消启动
    pause
    exit /b 0
)

echo.
echo 正在启动 Tauri...
echo.

call npm run dev

echo.
echo Tauri 已停止
pause
