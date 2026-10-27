# ⚡ Tauri 快速启动指南

## 🎯 立即开始

### 第一步：验证环境

```bash
# 1. 验证 Rust 工具链
rustc --version
# 应输出: rustc 1.xx.x

# 2. 验证 Node.js
node --version
# 应输出: v18.x 或更高

# 3. 验证 Tauri CLI
npx tauri --version
# 应输出: 2.x.x

# 4. 验证 Python
python --version
# 应输出: Python 3.x
```

### 第二步：安装依赖（首次运行）

```bash
# 安装前端依赖（如未安装）
cd frontend
npm install

# 安装 Python 依赖（如未安装）
pip install flask flask-cors akshare pandas
```

### 第三步：启动开发环境

```bash
# 在项目根目录运行
npm run dev
```

**启动后会发生：**
1. ✅ Tauri 启动 Rust 主进程
2. ✅ 自动启动 Vue 前端开发服务器（5173 端口）
3. ✅ 自动启动 Python sidecar 后端（5000 端口）
4. ✅ 创建原生桌面窗口

**首次启动需要等待：**
- Rust 编译依赖（3-5 分钟）
- 后续启动会很快（秒级）

---

## 🔧 开发工作流

### 日常开发

```bash
# 启动完整系统
npm run dev

# 按 F12 打开开发者工具
# 或右键 -> 打开开发者工具
```

### 修改代码后

```bash
# 前端代码（Vue）：自动热更新，无需重启
# 后端代码（Python）：需要重启
#   - 在终端按 Ctrl+C 停止
#   - 重新运行 npm run dev

# Rust 代码修改：自动重新编译（较慢）
```

### 调试技巧

1. **前端调试**
   - 按 F12 打开 DevTools
   - 查看 Console、Network、Elements
   - 使用 Vue DevTools 扩展

2. **后端调试**
   - Python 输出会显示在终端
   - 查看 `[Backend STDOUT]` 日志
   - API 访问日志会打印请求参数

3. **Rust 调试**
   - 查看终端输出
   - 使用 `println!()` 打印调试信息

---

## 📦 打包发布

### 准备 data 文件（重要！）

```bash
# 复制 data 目录到 sidecar
xcopy /E /I data src-tauri\sidecar\data
```

### 打包 Python 后端

```bash
# 重新打包（如有代码更新）
npm run backend:build
```

### 构建完整应用

```bash
# 构建安装包
npm run build

# 输出位置：
# src-tauri\target\release\futures-quantitative.exe
# src-tauri\target\release\bundle\msi\*.msi
# src-tauri\target\release\bundle\nsis\*.exe
```

---

## 🐛 快速故障排除

### 问题 1：端口被占用

```bash
# 查找占用端口的进程
netstat -ano | findstr :5000
netstat -ano | findstr :5173

# 结束进程（替换 PID）
taskkill /PID <PID> /F
```

### 问题 2：Rust 编译错误

```bash
# 清理缓存
cd src-tauri
cargo clean

# 重新编译
cd ..
npm run dev
```

### 问题 3：前端白屏

```bash
# 手动启动前端
cd frontend
npm run dev

# 访问 http://localhost:5173 验证
# 确认后再运行 npm run dev
```

### 问题 4：后端 API 失败

```bash
# 手动测试后端
python backend.py

# 在浏览器访问
# http://localhost:5000/api/brokers
```

### 问题 5：sidecar 找不到

```bash
# 检查 python-backend.exe 是否存在
dir src-tauri\sidecar\python-backend.exe

# 如不存在，重新打包
npm run backend:build
```

---

## 📂 项目结构

```
futures-quantitative/
├── frontend/                 # Vue 前端
│   ├── src/
│   │   ├── views/           # 页面组件
│   │   ├── api/             # API 调用
│   │   └── router/          # 路由配置
│   └── package.json
│
├── src-tauri/               # Tauri Rust 后端
│   ├── src/
│   │   └── main.rs          # Rust 入口
│   ├── sidecar/
│   │   ├── python-backend.exe  # Python 后端
│   │   └── data/            # 数据文件（打包后）
│   ├── tauri.json           # Tauri 配置
│   └── Cargo.toml           # Rust 依赖
│
├── backend.py               # Python 后端源码
├── data/
│   └── brokers.json         # 期货公司数据
│
└── package.json             # npm 脚本
```

---

## 🌐 API 端点

开发模式下，所有 API 可通过以下方式访问：

| API | 地址 | 说明 |
|-----|------|------|
| 期货公司列表 | http://localhost:5000/api/brokers | GET |
| 用户登录 | http://localhost:5000/api/login | POST |
| K线数据 | http://localhost:5000/api/backtest/kline | GET |
| 量化登录 | http://localhost:5000/api/quant-login | POST |
| 退出登录 | http://localhost:5000/api/logout | POST |

---

## 💡 最佳实践

### 开发时

1. ✅ **保持终端可见**：查看后端日志和错误
2. ✅ **使用 DevTools**：F12 调试前端问题
3. ✅ **频繁测试**：修改后立即验证
4. ✅ **备份代码**：使用 Git 版本控制

### 打包时

1. ✅ **更新 data 文件**：确保最新数据
2. ✅ **测试打包版本**：运行打包后的 exe
3. ✅ **清理缓存**：删除 target 目录减小体积
4. ✅ **版本标记**：使用 Git tag 标记版本

---

## 📚 更多信息

- 完整迁移报告：[TAURI_MIGRATION_COMPLETE.md](TAURI_MIGRATION_COMPLETE.md)
- Tauri 官方文档：https://tauri.app/
- 项目问题记录：[DEVELOPMENT_REPORT.md](DEVELOPMENT_REPORT.md)

---

**准备就绪？现在运行：**

```bash
npm run dev
```

**祝您开发愉快！🎉**
