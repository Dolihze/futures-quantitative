# 期货量化交易系统 - 前端

基于 Vue3 + Element Plus 构建的现代化前端应用。

## 📦 技术栈

- **框架**: Vue 3.4+
- **UI 组件库**: Element Plus 2.5+
- **构建工具**: Vite 5.0+
- **路由**: Vue Router 4.2+
- **状态管理**: Pinia 2.1+
- **HTTP 客户端**: Axios 1.6+
- **图表库**: ECharts 5.4+

## 🚀 快速开始

### 安装依赖

```bash
cd frontend
npm install
```

### 开发模式

```bash
npm run dev
```

访问 http://localhost:3000

### 构建生产版本

```bash
npm run build
```

### 预览生产构建

```bash
npm run preview
```

## 📁 项目结构

```
frontend/
├── src/
│   ├── api/               # API 接口
│   │   └── index.js
│   ├── assets/            # 静态资源
│   ├── components/        # 公共组件
│   ├── router/            # 路由配置
│   │   └── index.js
│   ├── stores/            # Pinia 状态管理
│   │   └── user.js
│   ├── utils/             # 工具函数
│   │   └── request.js
│   ├── views/             # 页面组件
│   │   ├── Login.vue
│   │   ├── Home.vue
│   │   ├── Trading.vue
│   │   └── Backtest.vue
│   ├── App.vue            # 根组件
│   └── main.js            # 入口文件
├── public/                # 公共静态资源
├── index.html             # HTML 模板
├── package.json           # 依赖配置
└── vite.config.js         # Vite 配置
```

## 🎨 页面说明

### 登录页面 (Login.vue)
- 期货交易账户登录
- 期货公司选择（支持搜索）
- 记住密码功能
- 调试模式快捷入口

### 首页 (Home.vue)
- 功能模块导航
- 交易和回测入口卡片
- 用户信息展示

### 交易页面 (Trading.vue)
- 实时行情数据展示（开发中）
- 下单操作（开发中）
- 持仓管理（开发中）

### 回测页面 (Backtest.vue)
- 历史数据回测（开发中）
- 策略验证（开发中）
- 绩效分析（开发中）

## 🔌 API 配置

开发环境下，API 请求会自动代理到后端 Flask 服务器 `http://127.0.0.1:5000`

详见 `vite.config.js` 中的 proxy 配置。

## 📝 开发规范

- 使用 Composition API
- 使用 `<script setup>` 语法
- 组件命名使用 PascalCase
- API 请求统一使用 axios 封装
- 状态管理使用 Pinia

## 🔐 认证机制

- 登录后将用户信息存储到 localStorage
- 路由守卫检查登录状态
- 未登录用户自动跳转到登录页

## 🌙 主题

采用深色主题设计，主色调：
- 背景色: #0f172a
- 主蓝色: #3b82f6
- 成功色: #22c55e
- 危险色: #ef4444

## 📌 注意事项

1. 确保后端 Flask 服务运行在 `http://127.0.0.1:5000`
2. 开发时 Vite 会自动代理 API 请求
3. 生产构建需要配置正确的 API 地址
4. Element Plus 组件按需自动导入

## 🔄 后续开发计划

- [ ] 完成交易页面完整功能
- [ ] 完成回测页面完整功能
- [ ] 添加实时行情推送
- [ ] 优化移动端适配
- [ ] 添加更多技术指标图表
- [ ] 实现策略编辑器

## 📄 License

仅供内部测试使用
