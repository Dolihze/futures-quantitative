# 🗑️ pywebview 卸载与清理指南

## ⚠️ 重要提醒

在卸载 pywebview 之前，请确保：
1. ✅ Tauri 开发环境已成功启动并运行正常
2. ✅ 所有功能在 Tauri 模式下测试通过
3. ✅ 已备份重要代码和数据

---

## 📋 卸载步骤

### 第一步：验证 Tauri 工作正常

```bash
# 运行验证脚本
verify-tauri.bat

# 或手动启动
npm run dev
```

**确认清单：**
- [ ] Tauri 窗口正常打开
- [ ] Vue 前端页面加载正常
- [ ] Python 后端 API 可访问
- [ ] 所有业务功能正常
- [ ] F12 开发者工具可用

### 第二步：停止 pywebview 相关进程

```bash
# 如果 app.py 正在运行，按 Ctrl+C 停止
# 或结束相关进程
taskkill /F /IM python.exe
```

### 第三步：卸载 pywebview

```bash
# 卸载 pywebview 包
pip uninstall pywebview -y

# 验证卸载
pip list | findstr pywebview
# 应无输出
```

### 第四步：清理旧代码（可选）

#### 4.1 备份 app.py

```bash
# 备份旧的 pywebview 入口
copy app.py app.py.bak.pywebview
```

#### 4.2 删除或归档 app.py

**选项 A：保留但重命名（推荐）**
```bash
# 重命名，避免误用
ren app.py app.pywebview.old
```

**选项 B：完全删除（确认不需要后）**
```bash
# 删除文件
del app.py
```

#### 4.3 清理 requirements.txt

如果有 `requirements.txt`，移除 pywebview：

```txt
# 删除这一行
pywebview>=x.x.x
```

### 第五步：更新文档

在项目 README 中标注迁移完成：

```markdown
## 架构说明

⚠️ **重要**：本项目已从 pywebview 迁移到 Tauri 2.x

- ❌ 旧架构：`app.py` + pywebview（已废弃）
- ✅ 新架构：Tauri 2.x + Vue + Python Sidecar

启动方式：
```bash
npm run dev
```
```

---

## 🔍 验证清理结果

### 检查 pywebview 是否已卸载

```bash
# 检查 pip 包
pip list | findstr pywebview
# 应无输出

# 尝试导入（应失败）
python -c "import webview"
# 应报错: ModuleNotFoundError
```

### 检查 Tauri 独立性

```bash
# 启动 Tauri（不需要 pywebview）
npm run dev

# 确认能正常启动
```

---

## 🗂️ 清理后的项目结构

```
futures-quantitative/
├── frontend/                 # Vue 前端 ✅
├── src-tauri/               # Tauri Rust 后端 ✅
│   ├── sidecar/
│   │   ├── python-backend.exe  # Python 后端 ✅
│   │   └── data/            # 数据文件
│   ├── tauri.json
│   ├── Cargo.toml
│   └── src/main.rs
│
├── backend.py               # Python 后端源码 ✅
├── data/
│   └── brokers.json
│
├── package.json             # npm 脚本 ✅
├── start-tauri.bat          # Tauri 启动脚本 ✅
├── verify-tauri.bat         # 验证脚本 ✅
│
└── app.pywebview.old        # 旧入口（备份）🗑️
```

---

## 🐛 常见问题

### Q1: 卸载 pywebview 后 Tauri 无法启动

**原因**：Tauri 不依赖 pywebview，应该独立运行

**解决**：
```bash
# 确认使用正确的启动命令
npm run dev

# 不要运行 python app.py
```

### Q2: 误删了 app.py

**解决**：
```bash
# 从备份恢复
copy app.py.bak.pywebview app.py

# 或从 Git 恢复
git checkout app.py
```

### Q3: 还有其他文件引用了 webview

**检查**：
```bash
# 搜索所有引用
findstr /s "import webview" *.py
findstr /s "webview\." *.py

# 找到的文件需要清理或移除引用
```

### Q4: 想同时保留 pywebview 和 Tauri

**可行但不推荐**：
- 保留两个版本会导致维护负担
- 建议完成迁移后专注于 Tauri 版本
- 如需保留，使用不同入口文件

---

## 📊 清理效果对比

| 项目 | 清理前 | 清理后 |
|------|--------|--------|
| 依赖包 | pywebview + Flask | Flask only |
| 入口文件 | app.py + backend.py | backend.py only |
| 启动方式 | 2种混用 | Tauri only |
| 维护成本 | 高 | 低 |
| 代码清晰度 | 中等 | 高 |

---

## ✅ 清理完成检查清单

- [ ] pywebview 已卸载
- [ ] app.py 已备份或归档
- [ ] Tauri 能正常独立启动
- [ ] 所有功能测试通过
- [ ] requirements.txt 已更新（如有）
- [ ] 项目文档已更新
- [ ] Git 提交清理后的代码

---

## 🚀 下一步

清理完成后，专注于 Tauri 版本的开发和优化：

1. **性能优化**
   - 减少 Python 后端内存占用
   - 优化前端打包体积
   - 提升启动速度

2. **功能增强**
   - 添加 Tauri 插件（系统托盘、通知等）
   - 实现自动更新功能
   - 添加原生功能（文件对话框等）

3. **部署准备**
   - 配置代码签名
   - 创建安装包
   - 准备发布文档

---

**清理完成时间**：_________  
**验证人**：_________  
**迁移状态**：✅ 已完成 → 🗑️ 已清理 → 🚀 生产中
