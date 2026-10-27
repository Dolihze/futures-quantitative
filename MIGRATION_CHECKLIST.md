# Tauri 2.x 迁移检查清单

## ✅ 已完成

- [x] 创建 `backend.py` - Flask sidecar 源码
- [x] 创建 `requirements.txt` - Python 依赖清单
- [x] 创建 `package.json` - 项目根配置
- [x] 创建 `src-tauri/tauri.json` - Tauri 配置
- [x] 创建 `src-tauri/src/main.rs` - Rust 主程序
- [x] 创建 `src-tauri/Cargo.toml` - Rust 依赖
- [x] 创建 `src-tauri/build.rs` - Tauri 构建脚本
- [x] 创建 `src-tauri/sidecar/README.md` - Sidecar 说明
- [x] 创建 `.gitignore` - 排除构建产物
- [x] 创建 `QUICKSTART.md` - 快速开始指南
- [x] 创建 `TAURI_MIGRATION_GUIDE.md` - 迁移指南

## 🔄 待完成

### 1. 环境安装

- [ ] 安装 Rust
  ```bash
  # 访问 https://rustup.rs/ 下载安装
  rustc --version  # 验证安装
  ```

- [ ] 安装 Tauri CLI
  ```bash
  npm install
  npx tauri --version  # 验证安装
  ```

- [ ] 安装 Python 依赖
  ```bash
  pip install -r requirements.txt
  ```

### 2. Python Sidecar 打包

- [ ] 打包 Python 后端
  ```bash
  pyinstaller --onefile --name python-backend --distpath src-tauri/sidecar backend.py
  ```

- [ ] 验证打包结果
  ```bash
  dir src-tauri\sidecar\python-backend.exe
  ```

- [ ] 测试 sidecar 运行
  ```bash
  src-tauri\sidecar\python-backend.exe
  # 应看到: [Backend] Flask Sidecar 启动中...
  ```

### 3. 前端依赖安装

- [ ] 安装前端依赖
  ```bash
  cd frontend
  npm install
  ```

- [ ] 验证前端开发服务器
  ```bash
  npm run dev
  # 访问 http://localhost:5173
  ```

### 4. Tauri 开发环境

- [ ] 检查 Tauri 环境
  ```bash
  npx tauri info
  ```

- [ ] 诊断环境配置
  ```bash
  npx tauri doctor
  ```

- [ ] 首次编译 Tauri
  ```bash
  npx tauri dev
  # 首次编译可能需要 5-10 分钟
  ```

### 5. 功能验证

- [ ] 应用窗口正常显示
- [ ] F12 打开开发者工具
- [ ] 前端页面正常加载
- [ ] API 请求正常工作
  ```bash
  # 在开发者工具 Console 中测试
  fetch('http://127.0.0.1:5000/api/brokers')
    .then(r => r.json())
    .then(console.log)
  ```

- [ ] 登录功能正常
- [ ] K线数据获取正常
- [ ] 图表渲染正常

### 6. 生产构建

- [ ] 构建前端
  ```bash
  cd frontend
  npm run build
  ```

- [ ] 构建 Tauri 应用
  ```bash
  npx tauri build
  ```

- [ ] 验证构建产物
  ```bash
  dir src-tauri\target\release\
  ```

- [ ] 测试生产版本
  ```bash
  src-tauri\target\release\futures-quantitative.exe
  ```

## 🐛 常见问题

### 问题 1: Rust 编译失败

**症状**: `cargo build` 失败

**解决**:
```bash
rustup update
cd src-tauri
cargo clean
```

### 问题 2: Sidecar 找不到

**症状**: `Failed to find sidecar`

**解决**:
1. 检查 `python-backend.exe` 是否在 `src-tauri/sidecar/` 目录
2. 重新打包: `npm run backend:build`

### 问题 3: F12 无法打开

**症状**: 按 F12 无反应

**解决**:
1. 确保在 `dev` 模式下运行
2. 检查 `tauri.json` 中 `withGlobalTauri: true`
3. 查看 Rust 控制台日志

### 问题 4: API 请求失败

**症状**: `fetch` 返回错误

**解决**:
1. 确认 Flask sidecar 已启动（查看控制台日志）
2. 检查 CORS 配置
3. 在开发者工具 Network 标签查看详情

## 📊 迁移进度跟踪

| 阶段 | 任务数 | 完成数 | 进度 |
|------|--------|--------|------|
| 环境安装 | 3 | 0 | 0% |
| Sidecar 打包 | 3 | 0 | 0% |
| 前端依赖 | 2 | 0 | 0% |
| Tauri 开发 | 3 | 0 | 0% |
| 功能验证 | 7 | 0 | 0% |
| 生产构建 | 4 | 0 | 0% |
| **总计** | **22** | **0** | **0%** |

## 📝 备注

- 首次编译 Rust 需要 5-10 分钟，后续增量编译很快
- 遇到错误时查看 Tauri 控制台输出
- 参考 `QUICKSTART.md` 和 `TAURI_MIGRATION_GUIDE.md`
- 开发者工具只能在 debug 模式下使用

---

**祝您迁移顺利！** 🎉
