# HTML模板迁移清理报告

> **历史文档**：本文记录 2026-10-18 将纯 HTML 页面迁移到 Vue 的清理工作（当时为 pywebview + `app.py`）。
> 项目现已迁移到 **Tauri 2.x**，`app.py` 已移除，其 API 全部保留在 `backend.py` 中。
> 最新的启动与构建方式请见根目录 [`README.md`](README.md)。

## 清理时间
2026-10-18

## 概述
已将早期Python开发中的纯HTML页面完全迁移到Vue框架，清理了不再使用的HTML模板文件。

## 删除的文件

### templates目录（已删除）
以下HTML模板文件已被删除：
- `templates/backtest.html` (62.3KB) - 回测页面
- `templates/home.html` (11.1KB) - 首页
- `templates/index.html` (31.1KB) - 主页面
- `templates/login.html` (36.6KB) - 登录页面
- `templates/trading.html` (43.5KB) - 交易页面

**总计：5个HTML文件，约184.6KB**

## Vue前端替代方案

### 已实现的Vue组件（✅ 完全迁移）
所有页面已使用Vue 3 + Element Plus重新实现：

1. **登录页面** → `frontend/src/views/Login.vue`
   - 使用Element Plus表单组件
   - Pinia状态管理
   - 响应式设计

2. **首页** → `frontend/src/views/Home.vue`
   - 功能卡片导航
   - 现代化UI设计
   - 路由跳转

3. **交易页面** → `frontend/src/views/Trading.vue`
   - 实时行情数据
   - 下单交易功能
   - ECharts图表集成

4. **回测页面** → `frontend/src/views/Backtest.vue`
   - K线图表展示
   - 回测参数配置
   - 结果分析

### Vue路由配置
```javascript
// frontend/src/router/index.js
{
  path: '/login',
  name: 'Login',
  component: () => import('@/views/Login.vue')
},
{
  path: '/',
  name: 'Home',
  component: () => import('@/views/Home.vue')
},
{
  path: '/trading',
  name: 'Trading',
  component: () => import('@/views/Trading.vue')
},
{
  path: '/backtest',
  name: 'Backtest',
  component: () => import('@/views/Backtest.vue')
}
```

## 后端修改

### app.py 变更（当时的记录，现为 backend.py）

#### 移除的内容
1. `render_template` 导入（不再需要渲染HTML模板）
2. HTML页面路由：
   - `/login` (GET) - 渲染登录页面
   - `/` - 渲染首页
   - `/trading` - 渲染交易页面
   - `/backtest` - 渲染回测页面
3. 页面重定向逻辑（`redirect(url_for('login_page'))`等）

#### 保留的API接口
所有API接口保持不变，继续为前端提供服务：
- `/api/brokers` - 获取期货公司列表
- `/api/login` (POST) - 用户登录
- `/api/logout` (POST) - 退出登录
- `/api/backtest/kline` - 获取K线数据
- `/api/quant-login` (POST) - 量化账号登录

#### 当时新增的功能（pywebview 时期，已被 Tauri 取代）
1. 由 `app.py` 自动安装前端依赖并启动 Vue 开发服务器
2. 自动检测前端端口（5173 / 3000 / 5174 / 5175）并用 pywebview 窗口打开

这些职责现在由 Tauri 承担：`tauri.conf.json` 的 `beforeDevCommand` 启动前端，
`src-tauri/src/main.rs` 启动 Python sidecar 并创建窗口。

## 启动方式

现在只有一种桌面启动方式：

```bash
npm run dev
```

调试时可单独运行后端或前端（不会打开窗口）：

```bash
npm run backend:dev    # 仅 Flask，端口 5000
npm run frontend:dev   # 仅 Vite，端口 5173
```

详见根目录 [`README.md`](README.md)。

## 技术栈对比

### 旧方案（已废弃）
- **前端**: 纯HTML + CSS + JavaScript
- **后端**: Flask + Jinja2模板渲染
- **耦合度**: 高（前后端混合）
- **开发效率**: 低
- **维护性**: 差

### 新方案（当前使用）
- **前端**: Vue 3 + Element Plus + Pinia + ECharts
- **后端**: Flask (仅提供API)
- **耦合度**: 低（前后端分离）
- **开发效率**: 高
- **维护性**: 优

## 迁移收益

1. **开发效率提升**
   - 组件化开发，代码复用性高
   - 热重载，实时预览
   - TypeScript支持（可选）

2. **用户体验提升**
   - 单页应用，无刷新体验
   - Element Plus专业UI组件
   - 更好的交互反馈

3. **维护性提升**
   - 前后端分离，职责清晰
   - 代码结构更清晰
   - 易于扩展和测试

4. **构建部署优化**
   - 前端可独立构建和部署
   - 支持CDN加速
   - 静态资源优化

## 注意事项

1. **首次运行**需要安装前端依赖：
   ```bash
   cd frontend
   npm install
   ```

2. **前端依赖安装失败**时，可尝试使用国内镜像：
   ```bash
   npm install --registry=https://registry.npmmirror.com
   ```

3. **端口冲突**：Vite 现在固定使用 5173（`strictPort`），不会自动切换端口；
   残留进程占用端口时，`npm run dev` 会自动清理本项目的残留 Vite，详见 `README.md` 的故障排除

4. **开发环境**需要单独调试后端或前端时，可使用 `npm run backend:dev` / `npm run frontend:dev`

5. **生产环境**建议构建前端静态文件，通过Nginx等Web服务器部署

## 后续计划

1. ✅ 完成Vue前端开发
2. ✅ 清理旧HTML模板
3. ⏳ 添加单元测试
4. ⏳ 生产环境构建配置
5. ⏳ Docker容器化部署
6. ⏳ CI/CD自动化部署

## 相关文档

- [Vue迁移评估标准](./DEVELOPMENT_REPORT.md)
- [项目启动指南](./README.md)
- [前端开发文档](./frontend/README.md)
- [API接口文档](./README_BACKTEST.md)
