# Python Sidecar 目录

此目录用于存放 Python 后端打包后的可执行文件。

## 打包步骤

### 1. 安装 PyInstaller

```bash
pip install pyinstaller
```

### 2. 打包 Python 后端

```bash
# Windows
pyinstaller --onefile --name python-backend --distpath src-tauri/sidecar backend.py

# 或使用 npm 脚本
npm run backend:build
```

### 3. 验证打包结果

打包完成后，应在此目录看到：
- `python-backend.exe` (Windows)
- `python-backend` (Linux/macOS)

### 4. 开发模式

在开发模式下，Tauri 会自动查找并启动此目录中的 sidecar 程序。

## 注意事项

1. **依赖安装**：确保所有 Python 依赖已安装（akshare, flask, flask-cors 等）
2. **数据文件**：`data/brokers.json` 需要相对于可执行文件路径正确放置
3. **跨平台**：不同操作系统需要分别打包

## 依赖列表

```bash
pip install flask flask-cors akshare pandas
```

或创建 `requirements.txt`：

```
flask>=2.3.0
flask-cors>=4.0.0
akshare>=1.10.0
pandas>=2.0.0
```
