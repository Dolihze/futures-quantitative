@echo off
chcp 65001 >nul
title Tauri 迁移验证工具
echo ================================
echo   Tauri 迁移完整性验证
echo ================================
echo.

set PASS=0
set WARN=0
set FAIL=0

REM ===== 1. 环境检查 =====
echo [1/6] 检查开发环境...
echo.

rustc --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Rust 未安装
    set /a FAIL+=1
) else (
    for /f "tokens=*" %%i in ('rustc --version') do echo   [PASS] %%i
    set /a PASS+=1
)

cargo --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Cargo 未安装
    set /a FAIL+=1
) else (
    for /f "tokens=*" %%i in ('cargo --version') do echo   [PASS] %%i
    set /a PASS+=1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Node.js 未安装
    set /a FAIL+=1
) else (
    for /f "tokens=*" %%i in ('node --version') do echo   [PASS] Node.js %%i
    set /a PASS+=1
)

npm --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] npm 未安装
    set /a FAIL+=1
) else (
    for /f "tokens=*" %%i in ('npm --version') do echo   [PASS] npm %%i
    set /a PASS+=1
)

python --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Python 未安装
    set /a FAIL+=1
) else (
    for /f "tokens=*" %%i in ('python --version') do echo   [PASS] %%i
    set /a PASS+=1
)

echo.

REM ===== 2. Tauri 配置检查 =====
echo [2/6] 检查 Tauri 配置文件...
echo.

if exist "src-tauri\tauri.json" (
    echo   [PASS] tauri.json 存在
    set /a PASS+=1
) else (
    echo   [FAIL] tauri.json 缺失
    set /a FAIL+=1
)

if exist "src-tauri\Cargo.toml" (
    echo   [PASS] Cargo.toml 存在
    set /a PASS+=1
) else (
    echo   [FAIL] Cargo.toml 缺失
    set /a FAIL+=1
)

if exist "src-tauri\src\main.rs" (
    echo   [PASS] main.rs 存在
    set /a PASS+=1
) else (
    echo   [FAIL] main.rs 缺失
    set /a FAIL+=1
)

if exist "src-tauri\build.rs" (
    echo   [PASS] build.rs 存在
    set /a PASS+=1
) else (
    echo   [WARN] build.rs 缺失（可选）
    set /a WARN+=1
)

echo.

REM ===== 3. Python Sidecar 检查 =====
echo [3/6] 检查 Python Sidecar...
echo.

if exist "backend.py" (
    echo   [PASS] backend.py 存在
    set /a PASS+=1
) else (
    echo   [FAIL] backend.py 缺失
    set /a FAIL+=1
)

if exist "src-tauri\sidecar\python-backend.exe" (
    echo   [PASS] python-backend.exe 已打包
    set /a PASS+=1
    
    REM 检查文件大小
    for %%A in (src-tauri\sidecar\python-backend.exe) do (
        if %%~zA LSS 1000000 (
            echo   [WARN] python-backend.exe 文件过小
            set /a WARN+=1
        ) else (
            echo   [INFO] 文件大小: %%~zA bytes
        )
    )
) else (
    echo   [FAIL] python-backend.exe 未打包
    echo         运行: npm run backend:build
    set /a FAIL+=1
)

echo.

REM ===== 4. 前端文件检查 =====
echo [4/6] 检查前端文件...
echo.

if exist "frontend\package.json" (
    echo   [PASS] package.json 存在
    set /a PASS+=1
) else (
    echo   [FAIL] package.json 缺失
    set /a FAIL+=1
)

if exist "frontend\node_modules" (
    echo   [PASS] node_modules 已安装
    set /a PASS+=1
) else (
    echo   [WARN] node_modules 未安装
    echo         运行: cd frontend ^&^& npm install
    set /a WARN+=1
)

if exist "frontend\src\main.js" (
    echo   [PASS] main.js 存在
    set /a PASS+=1
) else (
    echo   [FAIL] main.js 缺失
    set /a FAIL+=1
)

if exist "frontend\vite.config.js" (
    echo   [PASS] vite.config.js 存在
    set /a PASS+=1
) else (
    echo   [WARN] vite.config.js 缺失
    set /a WARN+=1
)

echo.

REM ===== 5. 数据文件检查 =====
echo [5/6] 检查数据文件...
echo.

if exist "data\brokers.json" (
    echo   [PASS] brokers.json 存在
    set /a PASS+=1
) else (
    echo   [FAIL] brokers.json 缺失
    set /a FAIL+=1
)

REM 检查 sidecar 目录是否有 data（打包时需要）
if exist "src-tauri\sidecar\data\brokers.json" (
    echo   [PASS] sidecar\data\brokers.json 存在（打包模式）
    set /a PASS+=1
) else (
    echo   [INFO] sidecar\data\brokers.json 未找到
    echo         打包时需要复制 data 目录到 sidecar
    echo         运行: xcopy /E /I data src-tauri\sidecar\data
)

echo.

REM ===== 6. npm 脚本检查 =====
echo [6/6] 检查 npm 脚本...
echo.

findstr "tauri" package.json >nul
if errorlevel 1 (
    echo   [FAIL] package.json 缺少 tauri 脚本
    set /a FAIL+=1
) else (
    echo   [PASS] tauri 脚本已配置
    set /a PASS+=1
)

findstr "dev" package.json >nul
if errorlevel 1 (
    echo   [FAIL] package.json 缺少 dev 脚本
    set /a FAIL+=1
) else (
    echo   [PASS] dev 脚本已配置
    set /a PASS+=1
)

findstr "backend:build" package.json >nul
if errorlevel 1 (
    echo   [WARN] package.json 缺少 backend:build 脚本
    set /a WARN+=1
) else (
    echo   [PASS] backend:build 脚本已配置
    set /a PASS+=1
)

echo.

REM ===== 端口检查 =====
echo [附加] 检查端口占用...
echo.

netstat -ano | findstr ":5000" >nul
if errorlevel 1 (
    echo   [PASS] 端口 5000 未被占用
    set /a PASS+=1
) else (
    echo   [WARN] 端口 5000 已被占用
    echo         可能影响 Python 后端启动
    set /a WARN+=1
)

netstat -ano | findstr ":5173" >nul
if errorlevel 1 (
    echo   [PASS] 端口 5173 未被占用
    set /a PASS+=1
) else (
    echo   [WARN] 端口 5173 已被占用
    echo         可能影响前端启动
    set /a WARN+=1
)

echo.

REM ===== 汇总结果 =====
echo ================================
echo   验证结果汇总
echo ================================
echo.
echo   通过 (PASS): %PASS%
echo   警告 (WARN): %WARN%
echo   失败 (FAIL): %FAIL%
echo.

if %FAIL% GTR 0 (
    echo [结果] 存在 %FAIL% 个失败项，需要修复后才能启动
    echo.
    echo 建议操作：
    echo   1. 查看上方 FAIL 项目
    echo   2. 根据提示修复问题
    echo   3. 重新运行验证脚本
    pause
    exit /b 1
)

if %WARN% GTR 0 (
    echo [结果] 全部通过，但有 %WARN% 个警告
    echo.
    echo 可以启动，但建议处理警告项
    echo.
) else (
    echo [结果] 全部通过！迁移完成
    echo.
    echo 可以运行以下命令启动：
    echo   npm run dev
    echo   或运行 start-tauri.bat
    echo.
)

pause
