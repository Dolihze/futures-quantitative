# Tauri 2.x 快速开始指南

## 📋 前置要求

### 1. 安装 Rust

```bash
# Windows
# 下载并运行 rustup-init.exe
# 访问: https://rustup.rs/

# 验证安装
rustc --version
cargo --version
```

### 2. 安装 Node.js

```bash
# 推荐 Node.js 18+
node --version
npm --version
```

### 3. 安装 Python 依赖

```bash
# 在项目根目录执行
pip install -r requirements.txt
```

## 🚀 开发模式

### 步骤 1: 安装项目依赖

```bash
# 安装 Tauri CLI
npm install

# 安装前端依赖
cd frontend
npm install
cd ..
```

### 步骤 2: 打包 Python Sidecar

```bash
# Windows
pyinstaller --onefile --name python-backend --distpath src-tauri/sidecar backend.py

# 或使用 npm 脚本
npm run backend:build
```

### 步骤 3: 启动开发服务器

```bash
# 启动 Tauri 开发模式（自动启动前端、后端和桌面应用）
npm run dev

# 或
npx tauri dev
```

### 步骤 4: 打开开发者工具

应用启动后，按 **F12** 即可打开开发者工具！

- ✅ 原生支持，无需复杂配置
- ✅ 稳定可靠，不会断开连接
- ✅ 完整的 Chrome DevTools 功能

## 📦 构建生产版本

```bash
# 构建前端
cd frontend
npm run build
cd ..

# 打包 Python sidecar
pyinstaller --onefile --name python-backend --distpath src-tauri/sidecar backend.py

# 构建 Tauri 应用
npx tauri build
```

构建产物位于：`src-tauri/target/release/`

## 🔧 常用命令

```bash
# 开发模式
npm run dev              # 启动完整开发环境
npm run frontend:dev     # 仅启动前端
npm run backend:build    # 打包 Python sidecar

# 构建
npm run build            # 构建生产版本

# Tauri CLI
npx tauri dev           # 开发模式
npx tauri build         # 构建生产版本
npx tauri info          # 查看环境信息
npx tauri doctor        # 诊断环境配置
```

## 🐛 故障排查

### 问题 1: Rust 编译失败

```bash
# 更新 Rust 工具链
rustup update

# 清理缓存
cd src-tauri
cargo clean
```

### 问题 2: Sidecar 无法启动

```bash
# 检查 sidecar 是否存在
dir src-tauri\sidecar\python-backend.exe

# 手动测试 sidecar
src-tauri\sidecar\python-backend.exe
# 应看到: Flask Sidecar 启动中...
```

### 问题 3: 前端无法连接后端

```bash
# 检查 Flask 是否运行
curl http://127.0.0.1:5000/api/brokers

# 查看 Tauri 控制台日志
# 在开发者工具的 Console 中查看
```

### 问题 4: F12 无法打开开发者工具

```bash
# 确保在开发模式下运行
# release 版本默认禁用开发者工具

# 检查 Tauri 配置
# src-tauri/tauri.json 中 "withGlobalTauri": true
```

## 📂 项目结构

```
futures-quantitative/
├── frontend/              # Vue 前端项目
│   ├── src/
│   ├── package.json
│   └── vite.config.js
├── src-tauri/             # Tauri Rust 后端
│   ├── src/
│   │   └── main.rs       # Rust 主程序
│   ├── sidecar/          # Python sidecar 可执行文件
│   ├── Cargo.toml        # Rust 依赖
│   └── tauri.json        # Tauri 配置
├── backend.py            # Python Flask 后端源码
├── requirements.txt      # Python 依赖
├── package.json          # 项目根配置
└── README.md             # 本文件
```

## 🎯 对比 pywebview

| 功能 | pywebview | Tauri 2.x |
|------|-----------|-----------|
| 开发者工具 | ❌ 复杂配置 | ✅ F12 直接打开 |
| 打包体积 | ~200MB | ~10-20MB |
| 启动速度 | 慢 | 快 |
| 内存占用 | 高 | 低 |
| 稳定性 | EdgeChromium 依赖 | 系统 WebView2 |

## 📚 学习资源

- [Tauri 2.x 官方文档](https://beta.tauri.app/)
- [Vue 3 文档](https://vuejs.org/)
- [Rust Book](https://doc.rust-lang.org/book/)
- [Flask 文档](https://flask.palletsprojects.com/)

## 💡 提示

1. **首次编译较慢**：Rust 首次编译需要下载依赖，后续增量编译很快
2. **保持 sidecar 更新**：修改 Python 代码后需重新打包 sidecar
3. **开发时可用 debug 模式**：`Cargo.toml` 中 `debug_assertions` 启用开发者工具
4. **数据文件路径**：确保 `data/brokers.json` 相对于可执行文件路径正确

---

**祝您开发愉快！** 🎉
