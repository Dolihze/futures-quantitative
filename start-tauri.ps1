# Tauri 开发环境启动脚本
# 此脚本用于快速启动 Tauri 开发环境

Write-Host "================================" -ForegroundColor Cyan
Write-Host "  期货量化交易系统 - Tauri 2.x" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Rust 工具链
Write-Host "正在验证环境..." -ForegroundColor Yellow
try {
    $rustVersion = rustc --version 2>&1
    Write-Host "✓ Rust: $rustVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Rust 未安装，请先安装 Rust" -ForegroundColor Red
    Write-Host "  安装命令: winget install Rustlang.Rustup" -ForegroundColor Gray
    pause
    exit 1
}

# 检查 Node.js
try {
    $nodeVersion = node --version 2>&1
    Write-Host "✓ Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Node.js 未安装，请先安装 Node.js" -ForegroundColor Red
    Write-Host "  安装命令: winget install OpenJS.NodeJS" -ForegroundColor Gray
    pause
    exit 1
}

# 检查前端依赖
Write-Host ""
Write-Host "检查前端依赖..." -ForegroundColor Yellow
$frontendDir = Join-Path $PSScriptRoot "frontend"
$nodeModules = Join-Path $frontendDir "node_modules"

if (-not (Test-Path $nodeModules)) {
    Write-Host "首次运行，正在安装前端依赖..." -ForegroundColor Yellow
    Set-Location $frontendDir
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "前端依赖安装失败" -ForegroundColor Red
        Set-Location $PSScriptRoot
        pause
        exit 1
    }
    Set-Location $PSScriptRoot
    Write-Host "✓ 前端依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "✓ 前端依赖已安装" -ForegroundColor Green
}

# 检查 Python sidecar
Write-Host ""
Write-Host "检查 Python Sidecar..." -ForegroundColor Yellow
$sidecarPath = Join-Path $PSScriptRoot "src-tauri\sidecar\python-backend.exe"

if (-not (Test-Path $sidecarPath)) {
    Write-Host "⚠ Python Sidecar 未找到" -ForegroundColor Yellow
    Write-Host "  将自动打包 Python 后端..." -ForegroundColor Yellow
    
    # 检查 Python 依赖
    Write-Host "  检查 Python 依赖..." -ForegroundColor Yellow
    pip list | findstr "flask" > $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  安装 Python 依赖..." -ForegroundColor Yellow
        pip install flask flask-cors akshare pandas
    }
    
    # 打包 Python 后端
    Write-Host "  正在打包 Python 后端..." -ForegroundColor Yellow
    npm run backend:build
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Python 后端打包失败" -ForegroundColor Red
        pause
        exit 1
    }
    Write-Host "✓ Python 后端打包完成" -ForegroundColor Green
} else {
    Write-Host "✓ Python Sidecar 已存在" -ForegroundColor Green
}

# 检查 data 目录（开发模式下从源码目录读取）
Write-Host ""
Write-Host "检查数据文件..." -ForegroundColor Yellow
$dataPath = Join-Path $PSScriptRoot "data\brokers.json"

if (-not (Test-Path $dataPath)) {
    Write-Host "⚠ 数据文件未找到: $dataPath" -ForegroundColor Red
    Write-Host "  请确保 data\brokers.json 存在" -ForegroundColor Red
    pause
    exit 1
} else {
    Write-Host "✓ 数据文件就绪" -ForegroundColor Green
}

# 启动 Tauri
Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  准备启动 Tauri 开发环境" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "启动提示：" -ForegroundColor Yellow
Write-Host "  - 首次启动需要编译 Rust 依赖（3-5 分钟）" -ForegroundColor Gray
Write-Host "  - 按 F12 打开开发者工具" -ForegroundColor Gray
Write-Host "  - 按 Ctrl+C 停止服务" -ForegroundColor Gray
Write-Host ""

$choice = Read-Host "是否启动？(Y/N)"
if ($choice -ne 'Y' -and $choice -ne 'y') {
    Write-Host "已取消启动" -ForegroundColor Yellow
    pause
    exit 0
}

Write-Host ""
Write-Host "正在启动 Tauri..." -ForegroundColor Green
Write-Host ""

# 运行 npm run dev
npm run dev

# 等待用户确认
Write-Host ""
Write-Host "Tauri 已停止" -ForegroundColor Yellow
pause
