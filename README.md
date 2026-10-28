# 期货量化交易系统

基于 **Tauri 2.x + Vue 3 + Flask** 的桌面端期货量化交易系统。

- **客户端**：Tauri 2.x（Rust + 系统 WebView2）
- **前端**：Vue 3 + Vite + Element Plus + Pinia + ECharts
- **后端**：Flask，打包成 PyInstaller 可执行文件，作为 Tauri **sidecar** 子进程运行
- **行情数据**：akshare（新浪财经）

## 架构

```
┌──────────────────────────────────────────────┐
│ Tauri 主进程（Rust）  src-tauri/src/main.rs   │
│   ├─ WebView2 窗口 ── Vue 前端 (dev: :5173)   │
│   └─ Python sidecar（独立进程）               │
│        └─ Flask 后端 (127.0.0.1:5000)         │
└──────────────────────────────────────────────┘
```

- 开发模式下，前端的 `/api/*` 请求由 Vite 代理到 `http://127.0.0.1:5000`。
- 应用启动时 Rust 会先拉起 sidecar，并**等待 5000 端口就绪后再加载页面**，避免启动瞬间的 `ECONNREFUSED`。
- 应用进程被放进 Windows Job Object：无论正常退出、被 `tauri dev` 重编译杀掉还是崩溃，系统都会一并结束 sidecar，不会残留 `python-backend.exe`。

## 项目结构

```
futures-quantitative/
├── frontend/                 # Vue 3 前端（入口 index.html → src/main.js）
│   ├── src/{views,api,router,stores,utils,styles}
│   ├── public/favicon.ico
│   └── vite.config.js        # 端口 5173（strictPort）+ /api 代理
├── src-tauri/                # Tauri 客户端
│   ├── src/main.rs           # 启动 sidecar、devtools 命令、Job Object
│   ├── tauri.conf.json       # Tauri 配置
│   ├── capabilities/         # Tauri 2 权限（shell / sidecar）
│   ├── icons/                # 应用图标（由 scripts/gen-icon.py 生成）
│   └── sidecar/              # PyInstaller 打包出的后端（构建产物）
├── backend.py                # Flask 后端源码（sidecar 入口）
├── data/brokers.json         # 期货公司数据
├── scripts/
│   ├── dev-frontend.mjs      # beforeDevCommand：清理残留 Vite 后启动前端
│   ├── copy-sidecar.mjs      # 生成带目标三元组后缀的 sidecar 副本
│   └── gen-icon.py           # 生成应用图标
├── requirements.txt          # Python 依赖
├── package.json              # npm 脚本
├── start-tauri.bat / .ps1    # 一键启动（含环境检查）
└── verify-tauri.bat          # 环境与文件完整性检查
```

## 环境要求

| 工具 | 说明 |
|---|---|
| Rust (MSVC 工具链) | `rustc --version`，安装：`winget install Rustlang.Rustup` |
| Node.js 18+ | `node --version` |
| Python 3.x | `python --version` |
| WebView2 运行时 | Windows 11 已预装；Windows 10 需 [手动安装](https://developer.microsoft.com/microsoft-edge/webview2/) |

## 快速开始

```bash
# 1. 安装依赖（首次）
npm install
cd frontend && npm install && cd ..
pip install -r requirements.txt

# 2. 打包后端 sidecar（首次，以及每次修改 backend.py 后）
npm run backend:build

# 3. 启动
npm run dev
```

`npm run dev` 会依次：启动 Vue 前端（5173）→ 编译并运行 Tauri → Tauri 拉起 Python sidecar（5000）→ 打开桌面窗口。
首次编译 Rust 依赖需要几分钟，之后增量编译很快。

也可以使用 `start-tauri.bat` / `start-tauri.ps1`（自动检查环境并安装缺失依赖，最终同样执行 `npm run dev`）。
`verify-tauri.bat` 用于检查环境和关键文件是否齐全。

## 常用命令

| 命令 | 作用 |
|---|---|
| `npm run dev` | 启动完整开发环境（Tauri + 前端 + sidecar） |
| `npm run build` | 构建安装包 |
| `npm run backend:build` | 用 PyInstaller 打包 `backend.py` 并生成 sidecar |
| `npm run backend:dev` | 仅运行 Flask（调试 API，端口 5000，不打开窗口） |
| `npm run frontend:dev` | 仅运行 Vite（浏览器访问 http://localhost:5173） |
| `npx tauri info` | 查看 Tauri 环境信息 |

## 开发说明

- **前端**：改动自动热更新，无需重启。
- **Python 后端**：改动 `backend.py` 后需重新执行 `npm run backend:build`，再重启 `npm run dev`（sidecar 是打包后的 exe，不会读取源码）。
- **Rust**：改动 `src-tauri/` 会自动重新编译。
- **开发者工具**：debug 模式下按 **F12**（或右键 → 检查）。`main.rs` 另外提供 `open_devtools` / `close_devtools` / `toggle_devtools` 命令。
- **登录态**：保存在 `sessionStorage`，关闭窗口即失效，每次启动都从登录页开始。登录页的「记住账号」使用 `localStorage`。
- **后端日志**：Python 输出会以 `[Backend STDOUT]` / `[Backend STDERR]` 前缀显示在 `tauri dev` 的终端里。

### API

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/brokers` | GET | 期货公司列表 |
| `/api/login` | POST | 账号登录（目前为调试模式，放行任意账号） |
| `/api/logout` | POST | 退出登录 |
| `/api/quant-login` | POST | 量化账号登录（目前为调试模式） |
| `/api/backtest/kline` | GET | K 线数据，参数 `symbol` `period` `days` |

> 前端所有请求路径都必须以 `/api` 开头，否则不会被 Vite 代理转发。

## 构建发布

```bash
npm run backend:build   # 1. 打包后端（已内置 data/ 与 akshare 数据文件）
npm run build           # 2. 构建前端并生成安装包
```

产物位于 `src-tauri/target/release/`（可执行文件）和 `src-tauri/target/release/bundle/`（MSI / NSIS 安装包）。

### 关于 sidecar 打包

`npm run backend:build` 做了这些事，修改时请注意保持：

- 入口是 **`backend.py`**（不是其它文件）。
- `--add-data "data;data"`：把 `data/brokers.json` 打进 exe；`backend.py` 会在 PyInstaller 临时目录、exe 同级目录和项目目录中依次查找数据文件。
- `--collect-data akshare`：akshare 自带的 `file_fold/calendar.json` 等数据文件必须打包，否则 `/api/backtest/kline` 会 500。
- `scripts/copy-sidecar.mjs`：Tauri 要求 sidecar 文件名带目标三元组后缀（如 `python-backend-x86_64-pc-windows-msvc.exe`），脚本会自动生成。
- 构建产物 `src-tauri/sidecar/*.exe` 已在 `.gitignore` 中，不会提交。

## 故障排除

| 现象 | 原因与处理 |
|---|---|
| `Port 5173 is already in use` | 上次 `tauri dev` 异常结束，残留 Vite 占着端口。`npm run dev` 的 `beforeDevCommand` 会自动清理本项目的残留 Vite；若被其它程序占用会提示 pid，手动结束即可。 |
| 编译报 `PermissionDenied` / `拒绝访问`（tauri-build） | 有残留的 `python-backend.exe` 锁住了 `src-tauri/target/debug/python-backend.exe`。结束进程后重试：`Stop-Process -Name python-backend -Force`。应用内已用 Job Object 避免此问题。 |
| 前端报 `ECONNREFUSED 127.0.0.1:5000` | sidecar 没起来或崩溃。看终端里的 `[Backend STDERR]`；单独运行 `src-tauri\sidecar\python-backend.exe` 验证；或 `npm run backend:dev` 排查源码。 |
| `/api/backtest/kline` 返回 500 | 通常是 sidecar 缺 akshare 数据文件，确认用最新的 `npm run backend:build` 打包。 |
| sidecar 找不到 | 确认 `src-tauri/sidecar/` 下同时有 `python-backend.exe` 和 `python-backend-<triple>.exe`，没有则重新执行 `npm run backend:build`。 |
| Rust 编译失败 | `rustup update`，必要时 `cd src-tauri && cargo clean`。 |
| 前端白屏 | 先 `npm run frontend:dev`，浏览器访问 http://localhost:5173 确认前端本身正常。 |
| 每次启动直接进入主页 | 登录态应在 `sessionStorage`，若仍出现，清理应用的 WebView 缓存目录后重试。 |

## 更多文档

- [`README_BACKTEST.md`](README_BACKTEST.md)：回测功能使用说明
- [`frontend/README.md`](frontend/README.md)：前端说明
- [`src-tauri/sidecar/README.md`](src-tauri/sidecar/README.md)：sidecar 打包说明
- [`DEVELOPMENT_REPORT.md`](DEVELOPMENT_REPORT.md)、[`MIGRATION_COMPLETE.md`](MIGRATION_COMPLETE.md)、[`HTML_MIGRATION_CLEANUP.md`](HTML_MIGRATION_CLEANUP.md)：早期开发与 Vue 迁移记录（历史文档）
