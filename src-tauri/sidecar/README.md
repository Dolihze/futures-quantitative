# Python Sidecar 目录

此目录用于存放 Python 后端打包后的可执行文件。

## 打包步骤

### 1. 安装 PyInstaller

```bash
pip install pyinstaller
```

### 2. 打包 Python 后端

在项目根目录执行：

```bash
npm run backend:build
```

该脚本使用 `backend.py` 作为入口，并自动：
- 通过 `--add-data "data;data"` 打包 `data/brokers.json`
- 通过 `--collect-data akshare` 打包 akshare 自带的数据文件（缺失会导致 K 线接口 500）
- 运行 `scripts/copy-sidecar.mjs`，生成 Tauri 要求的带目标三元组后缀的副本

### 3. 验证打包结果

打包完成后，应在此目录看到：
- `python-backend.exe` (Windows)
- `python-backend-x86_64-pc-windows-msvc.exe`（带目标三元组后缀的副本，Tauri 实际使用它）

这些 exe 属于构建产物，已在 `.gitignore` 中，不会提交。

### 4. 开发模式

`npm run dev` 时，Tauri 会启动此目录中的 sidecar。注意 sidecar 是**打包后的 exe**：
修改 `backend.py` 后必须重新执行 `npm run backend:build`，改动才会生效。

## 注意事项

1. **依赖安装**：先执行 `pip install -r requirements.txt`
2. **数据文件**：已通过 PyInstaller 打进 exe，`backend.py` 会依次在 PyInstaller 临时目录、exe 同级目录和项目目录中查找
3. **跨平台**：不同操作系统需要分别打包（脚本会按当前 `rustc` 的 host 三元组命名）
4. **残留进程**：若编译报 `PermissionDenied`，说明有残留的 `python-backend.exe` 锁住了文件，结束该进程后重试（详见根目录 `README.md`）
