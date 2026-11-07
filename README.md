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
├── review.py                 # 交易复盘：Excel 解析与盈亏曲线计算（不依赖 Flask，可单独测试）
├── tests/                    # review 的单元测试与 API 测试（python tests/test_review.py）
├── data/brokers.json         # 期货公司数据
├── scripts/
│   ├── setup.mjs             # 首次准备：装前端依赖、装 Python 依赖、打包 sidecar
│   ├── dev-frontend.mjs      # beforeDevCommand：清理残留 Vite 后启动前端
│   ├── copy-sidecar.mjs      # 生成带目标三元组后缀的 sidecar 副本
│   └── gen-icon.py           # 生成应用图标
├── requirements.txt          # Python 依赖
└── package.json              # npm 脚本
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
# 1. 首次准备（根目录 npm install 之后只需执行一次）
npm install
npm run setup     # 装前端依赖 + 装 Python 依赖 + 打包后端 sidecar

# 2. 启动
npm run dev
```

`npm run setup` 等价于手动执行：

```bash
cd frontend && npm install && cd ..
python -m pip install -r requirements.txt
npm run backend:build
```

`npm run dev` 会依次：启动 Vue 前端（5173）→ 编译并运行 Tauri → Tauri 拉起 Python sidecar（5000）→ 打开桌面窗口。
首次编译 Rust 依赖需要几分钟，之后增量编译很快。

之后每次修改 `backend.py`，需要单独重新执行 `npm run backend:build`。

## 常用命令

| 命令 | 作用 |
|---|---|
| `npm run setup` | 首次准备：安装前端、Python 依赖并打包 sidecar |
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
| `/api/review/upload` | POST | 交易复盘：上传交易记录（multipart，字段 `file`，≤20MB），返回 `reviewId`、品种列表、数据时间范围、解析提示 |
| `/api/review/curve` | GET | 交易复盘：按 `reviewId`、`products`（逗号分隔，空=全部）、`start`、`end`、`fee`（1=扣手续费）返回累计盈亏曲线和统计 |

> 前端所有请求路径都必须以 `/api` 开头，否则不会被 Vite 代理转发。

## 交易复盘

首页第三个模块。导入期货公司结算单里的「成交明细」，绘制**累计平仓盈亏曲线**（x 轴时间，y 轴金额，红涨绿跌），可按时间范围和交易品种筛选，并显示累计盈亏、胜率、最大回撤、手续费等统计。

**支持的文件**：`.xlsx` / `.xls` / `.csv`。表头上方有标题、账户信息行也可以（会自动找表头行），文件末尾的“合计”行会被忽略。

**读取哪张工作表**：优先读名为「**成交明细**」的工作表，其余工作表（资金状况、平仓明细等）忽略；没有这张表时，依次尝试每张工作表，用第一张能识别出必需列的表。

**「成交明细」表头**（单元格里有换行也能识别）：

`合约`、`成交序号`、`成交时间`、`买/卖`、`投机（一般）/套保/套利`、`成交价`、`手数`、`成交额`、`开/平`、`手续费`、`平仓盈亏`、`实际成交日期`

其中 `投机/套保/套利`、`成交额` 不使用。必需的列是：成交时间（或「成交日期」+「成交时间」）、合约、买/卖、成交价、手数；`开/平`、`手续费`、`平仓盈亏` 建议有。其他叫法也能识别：

| 含义 | 可识别的列名 |
|---|---|
| 成交时间 | 成交时间 / 交易时间 / 时间；日期可以在另一列「实际成交日期」「成交日期」 |
| 合约 | 合约 / 合约代码 / 品种 |
| 买卖方向 | 买卖 / 买/卖 / 买卖方向 / 方向 |
| 成交价 | 成交价 / 成交价格 / 成交均价 |
| 手数 | 手数 / 成交量 / 成交手数 |
| 开平 | 开/平 / 开平 / 开平仓 / 开平标志 |
| 手续费 | 手续费 / 费用 |
| 平仓盈亏 | 平仓盈亏 / 盈亏 / 实现盈亏 |

> 文件里**只有日期、没有具体成交时间**（例如结算单里的「平仓明细」）会被拒绝并给出提示：同一天的成交分不出先后，按成交时间聚合会把不相干的成交并在一起。请导入带「成交时间」列的「成交明细」。

### 曲线怎么算

- **只统计平**：`开/平` 为「平」的成交才是曲线上的点和平仓笔数；开仓不产生盈亏，不算一笔。
- **成交时间相同的合并为一笔**：成交时间、合约、买/卖都相同的几行合并，手数、平仓盈亏、手续费相加，成交价取按手数加权的均价。同一时刻但合约不同、或买卖方向不同的不合并（合并后要显示合约、方向，混在一起没有意义）。
- **盈亏**：直接累加「平仓盈亏」列。文件里没有这一列时，按“合约 + 先进先出”自行配对开平仓，用内置的合约乘数计算（会提示“仅供参考”；没收录的品种按 10 计算并提示）。
- **手续费**：「扣除手续费」勾选时，**开仓和平仓的手续费都会扣**，不会因为“只统计平”而漏掉开仓的手续费。开仓手续费记在同一合约之后的第一笔平仓上（那一刻才实现盈亏）；后面一直没有平仓的开仓（仍持仓），其手续费计入最后一笔。所以曲线终点 = 平仓盈亏合计 − 全部手续费。统计里的「手续费合计」也包含开仓。文件里没有手续费数据时该选项不可用。
- **平仓笔数**是合并后的笔数，包含盈亏恰好为 0 的平仓；胜率只在盈利/亏损的平仓里计算。
- **交易品种**按合约去掉月份后的品种代码区分（`FU2611` → `FU`）。

### 日期约定：「实际成交日期」是交易日

结算单里的「实际成交日期」是**交易日**，不是成交真正发生的日历日期：同一个交易日的所有行（夜盘、凌晨、白天）都标同一个日期。例如交易日 10-16 的所有行都写 10-16，但其中 21:00 ~ 23:00 的夜盘实际发生在 **10-15 晚上**，其余才是 10-16 当天。

导入时按这个约定还原成真实发生的时刻：

| 文件里一行 | 交易日 | 还原后的真实时间 |
|---|---|---|
| `10-16  22:30:00` | 10-16 | **10-15** 22:30:00（晚上，往前挪一天） |
| `10-16  00:40:00` | 10-16 | 10-16 00:40:00（凌晨，夜盘延续，不变） |
| `10-16  09:20:00` | 10-16 | 10-16 09:20:00（白天，不变） |

规则：时间在 **20:00 之后**的往前挪一天，凌晨和白天不动。之后的排序、合并、画图、悬停显示的都是还原后的**真实时间**。

- **时间范围筛选按交易日**，和 Excel 日期列同一个语义：选“10-16 到 10-16”，包含 10-16 这个交易日的夜盘（真实在 10-15 晚上）、凌晨和白天，和 Excel 里按这天汇总的数字对得上。日期选择器里能选的日期也都是 Excel 日期列里存在的日期。
- **前提**：这个约定假设你的 Excel 把夜盘也标成了交易日（你描述的就是这样）。如果有的文件把夜盘标成了真实的日历日期（10-15 晚上就写 10-15），按这个约定会把夜盘多挪一天，需要告诉我。**夜盘延续到凌晨的成交，也必须标同一个交易日**（00:40 标 10-16，和它前面的 22:30 同一天），否则会被拆到两个交易日里。

### 时间轴

横轴是**固定的四个交易时段**，从左到右依次是：

| 顺序 | 时段 | 时间 |
|---|---|---|
| 1 | 夜盘（昨晚） | 21:00 ~ 23:00 |
| 2 | 早盘（上） | 09:00 ~ 10:15 |
| 3 | 早盘（下） | 10:30 ~ 11:30 |
| 4 | 午盘 | 13:30 ~ 15:00 |

- **全部数据都显示**：成交落在哪一段就画在哪一段。夜盘是**这个交易日的第一段**（它真实发生在前一天晚上），所以排在这个交易日的最前面。
- **段与段首尾相接，休息时间不画**（夜盘到 09:00、10:15 到 10:30、11:30 到 13:30 都去掉）。**段宽与真实时长成正比**（夜盘 120 分钟、早盘一 75、早盘二 60、午盘 90），所以横轴仍然是时间。
- **每个有成交的交易日都画完整的四段**，哪怕某一段没有成交（例如早盘二）。没有任何成交的交易日不画。
- **段内的位置与真实时间成正比**：09:15 的成交在早盘一起点右边 15 分钟处。
- **落在四个时段之外的成交不会丢**，归入距离最近的时段、贴在该段的边界上，悬停里显示的仍是真实成交时间：集合竞价（08:59）归早盘一，两场之间的休息（10:19）归早盘一，收盘后的撮合延迟（11:31、15:05）归所在场次，午休正中间两边一样远时归午盘。**夜盘延续到凌晨的成交（23:20、00:30 等）也归夜盘、贴在 23:00 处**，这些成交在轴上分不出先后（会叠在同一个位置，悬停时一起列出）。如果你交易的品种夜盘晚于 23:00 收盘，需要调整 `review.py` 里 `SESSIONS` 的夜盘结束时间。
- **不画背景色块**。交易日与交易日之间用一条竖向虚线分隔；一个交易日内部四段之间的虚线，只在放大到一两个交易日、每段够宽时才出现，避免多天视图里密密麻麻像一张网格。

**X 轴标签**

- 相邻两段的交界处只写**一个**标签，把上一段的终点和下一段的起点并排写在一起：`终点（黄）| 起点（蓝）`，如 `10:15 | 10:30`、`11:30 | 13:30`、`23:00 | 09:00`。分开写成两个标签的话，两个刻度点只隔十几个像素，文字会叠在一起。
- 日期标的是**交易日**，写在 `23:00 | 09:00` 这个交界标签的上面一行（如 `10-15`）。夜盘本身不写日期——它的真实日历日期是交易日的前一天，写上去会让人以为数据错了。
- 标签数量按**当前可见范围**自动控制：多个交易日同时显示时每段只有几十个像素，放不下的交界标签隔一个丢一个，只保留每个交易日的日期；用滚轮或下方滑块**放大**到一两个交易日后，所有边界时间和段名才会出现；缩回去又恢复。

**曲线**

- 相邻两笔之间用**斜线**直接连接，每个拐点都落在一笔真实的平仓上。没有用阶梯线（只有水平和垂直，看不出趋势），也没有用平滑曲线（会在拐点处画出数据里不存在的圆弧和超调）。
- 夜盘没有成交时，曲线在夜盘段是一条水平线：那是前一段累计盈亏的延续，表示这段时间账户没有变化。
- 缩放：滚轮缩放、拖动下方滑块查看局部，默认显示全部。

### 鼠标悬停

悬停到某一笔会显示：成交时间、合约、方向（`卖平` / `买平`）、手数、成交价、（如果是合并的）合并了几笔成交、本笔盈亏、手续费（含对应开仓）、累计盈亏。

同一时刻有几笔不能合并的平仓（合约不同或买卖方向不同）时，它们的横坐标相同，悬停提示会把这几笔**一起列出来**（标题写“此位置共 N 笔平仓”），不会漏掉其中的某一笔；被归入最近时段而叠在同一个位置的几笔也一样，各自显示真实的成交时间。

**数据与隐私**：上传的记录只保存在后端内存中（最多保留最近 5 份），不会写入磁盘，应用重启后需重新导入。

**测试**：`python tests/test_review.py`（解析与计算）、`python tests/test_review_api.py`（接口，含 Excel 上传）。

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
| 交易复盘提示“没有识别到必需的列” | 导出文件的列名不在识别范围内。提示里会列出已识别的列（有多张工作表时会说明是哪一张）；把表头改成上面表格里的常见叫法，或把文件发给开发者适配。 |
| 交易复盘提示“文件里只有日期，没有具体的成交时间” | 导入的是只有日期的表（例如结算单里的「平仓明细」）。同一天的成交分不出先后，无法按成交时间聚合。请导入带「成交时间」列的「成交明细」工作表。 |
| 交易复盘提示“当前筛选下只有开仓，没有平仓” | 曲线只统计「平」的成交。这个筛选范围里的成交都还没有平仓，把时间范围拉长，或换一个有平仓的品种。 |
| 交易复盘打开后，X 轴只有几个日期、没有时间 | 正常：多个交易日同时显示时每段只有几十个像素，放不下时间标签。用滚轮或下方滑块放大到一两个交易日，边界时间和段名就会出现。 |
| 交易复盘里有几笔成交叠在同一个位置（夜盘 23:00 处、或某段的边界上） | 这些成交落在四个固定时段之外（夜盘延续到凌晨、集合竞价、撮合延迟），被归入最近的时段、贴在该段边界上，悬停时一起列出，各自显示真实时间。夜盘晚于 23:00 收盘的品种，需调整 `review.py` 里 `SESSIONS` 的夜盘结束时间。 |
| 交易复盘提示“交易记录已失效” | sidecar 重启过（内存里的记录已清空），重新导入文件即可。 |
| 修改了 `review.py` 但没有效果 | 同 `backend.py`：sidecar 是打包后的 exe，需要重新执行 `npm run backend:build`。 |
| sidecar 找不到 | 确认 `src-tauri/sidecar/` 下同时有 `python-backend.exe` 和 `python-backend-<triple>.exe`，没有则重新执行 `npm run backend:build`。 |
| Rust 编译失败 | `rustup update`，必要时 `cd src-tauri && cargo clean`。 |
| 前端白屏 | 先 `npm run frontend:dev`，浏览器访问 http://localhost:5173 确认前端本身正常。 |
| 每次启动直接进入主页 | 登录态应在 `sessionStorage`，若仍出现，清理应用的 WebView 缓存目录后重试。 |

## 更多文档

- [`README_BACKTEST.md`](README_BACKTEST.md)：回测功能使用说明
- [`frontend/README.md`](frontend/README.md)：前端说明
- [`src-tauri/sidecar/README.md`](src-tauri/sidecar/README.md)：sidecar 打包说明
- [`DEVELOPMENT_REPORT.md`](DEVELOPMENT_REPORT.md)、[`MIGRATION_COMPLETE.md`](MIGRATION_COMPLETE.md)、[`HTML_MIGRATION_CLEANUP.md`](HTML_MIGRATION_CLEANUP.md)：早期开发与 Vue 迁移记录（历史文档）
