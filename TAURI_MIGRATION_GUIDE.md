# Tauri 2.x 迁移指南

## 📦 架构对比

### 当前架构 (pywebview)
```
┌─────────────────────────────────────┐
│   pywebview (EdgeChromium)          │
│   ├─ Vue Frontend (端口 5173)       │
│   └─ Flask Backend (端口 5000)      │
└─────────────────────────────────────┘
        ↓ F12 调试复杂，连接易断开
```

### 目标架构 (Tauri 2.x)
```
┌─────────────────────────────────────┐
│   Tauri 2.x (Rust + WebView2)       │
│   ├─ Vue Frontend (内置)            │
│   └─ Flask Sidecar (端口 5000)      │
└─────────────────────────────────────┘
        ↓ 原生 F12 支持，稳定可靠
```

## 🚀 迁移步骤

### 步骤 1: 安装 Rust 和 Tauri CLI

```bash
# 1. 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 2. 安装 Tauri 2.x CLI
cargo install tauri-cli --version "^2.0.0"

# 或使用 npm
npm install --save-dev @tauri-apps/cli@latest
```

### 步骤 2: 初始化 Tauri 项目

```bash
cd e:\workspace\futures-quantitative
npx tauri init
```

配置选项：
- **App name**: `futures-quantitative`
- **Window title**: `期货量化交易系统`
- **Web assets relative path**: `../frontend/dist`
- **Dev server URL**: `http://localhost:5173`
- **Frontend dev command**: `npm run dev`
- **Frontend build command**: `npm run build`

### 步骤 3: 配置 Python Sidecar

Tauri 2.x 支持将 Python 打包为 sidecar 进程，Flask 服务将在应用启动时自动运行。

#### 3.1 创建 sidecar 配置

在 `src-tauri/tauri.conf.json` 中添加：

```json
{
  "bundle": {
    "externalBin": [
      "sidecar/python-backend"
    ]
  }
}
```

#### 3.2 修改 Python 代码为 sidecar 模式

创建独立的 `backend.py` 文件：

```python
#!/usr/bin/env python3
"""
Flask Backend as Tauri Sidecar
"""
from flask import Flask, request, jsonify, session
from flask_cors import CORS
import json
import os
import sys

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 启用 CORS
CORS(app, supports_credentials=True)

# 加载数据... (保持原有代码)

if __name__ == '__main__':
    # Sidecar 模式下监听 5000 端口
    app.run(host='127.0.0.1', port=5000, debug=False)
```

#### 3.3 打包 Python 为可执行文件

使用 PyInstaller：

```bash
pip install pyinstaller
pyinstaller --onefile --name python-backend app.py
```

将生成的可执行文件放入 `src-tauri/sidecar/` 目录。

### 步骤 4: 修改 Tauri Rust 代码启动 Sidecar

在 `src-tauri/src/main.rs` 中添加 sidecar 启动逻辑：

```rust
use tauri::process::{Command, CommandEvent};
use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // 启动 Python sidecar
            let sidecar = app
                .shell()
                .sidecar("python-backend")
                .expect("Failed to find sidecar");
            
            let (mut rx, child) = sidecar
                .spawn()
                .expect("Failed to spawn sidecar");
            
            // 存储子进程引用
            app.manage(SidecarChild(std::sync::Mutex::new(child)));
            
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Error while running tauri application");
}

struct SidecarChild(std::sync::Mutex<tauri::process::CommandChild>);
```

### 步骤 5: 配置开发环境

在 `src-tauri/tauri.conf.json` 中配置开发工具：

```json
{
  "build": {
    "beforeDevCommand": "cd ../frontend && npm run dev",
    "beforeBuildCommand": "cd ../frontend && npm run build",
    "devPath": "http://localhost:5173",
    "distDir": "../frontend/dist"
  },
  "app": {
    "withGlobalTauri": true,
    "windows": [
      {
        "title": "期货量化交易系统",
        "width": 1280,
        "height": 800,
        "resizable": true,
        "fullscreen": false
      }
    ],
    "security": {
      "csp": null
    }
  }
}
```

### 步骤 6: 启动开发环境

```bash
# 启动 Tauri 开发服务器（自动启动前端和 Python sidecar）
npx tauri dev

# 按 F12 打开开发者工具（原生支持！）
```

## ✅ 迁移优势

| 功能 | pywebview | Tauri 2.x |
|------|-----------|-----------|
| 开发者工具 | ❌ 复杂配置，易断开 | ✅ 原生 F12 支持 |
| 打包体积 | ~200MB | ~10-20MB |
| 性能 | 中等 | 优秀 |
| 内存占用 | 较高 | 低 |
| 系统 API | 有限 | 丰富 |
| 跨平台 | 依赖 WebView | 内置 WebView2 |

## 📝 注意事项

1. **前端代码无需大改**：现有的 Vue 代码几乎可以直接复用
2. **API 调用路径**：保持相对路径，Tauri 会自动代理
3. **Python 依赖**：确保 PyInstaller 打包包含所有依赖（如 akshare）
4. **首次编译**：Rust 首次编译较慢，后续增量编译很快

## 🔧 故障排查

### 问题 1: Rust 编译失败
```bash
# 更新 Rust 工具链
rustup update
```

### 问题 2: Sidecar 无法启动
- 检查 `python-backend.exe` 是否在 `src-tauri/sidecar/` 目录
- 查看 Tauri 控制台日志

### 问题 3: 前端无法连接后端
- 确认 Flask 在 `127.0.0.1:5000` 监听
- 检查 CORS 配置

## 📚 参考资源

- [Tauri 2.x 官方文档](https://beta.tauri.app/)
- [Tauri Sidecar 指南](https://beta.tauri.app/develop/sidecar/)
- [Rust 入门](https://doc.rust-lang.org/book/)
