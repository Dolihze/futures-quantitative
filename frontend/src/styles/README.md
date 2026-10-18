# 样式目录

本目录包含期货量化交易系统的所有页面样式文件。

## 目录结构

```
styles/
├── index.css          # 样式入口文件（可选，用于全局导入）
├── Trading.css        # 交易页面样式
├── Home.css           # 首页样式
├── Backtest.css       # 回测页面样式
├── Login.css          # 登录页面样式
└── README.md          # 本说明文档
```

## 样式隔离说明

每个页面的样式都实现了**作用域隔离**，通过以下方式确保样式不会相互影响：

1. **Vue Scoped CSS**: 在 Vue 组件中使用 `<style scoped>`，确保样式只作用于当前组件
2. **独立文件**: 每个页面的样式都存储在独立的 CSS 文件中
3. **类名语义化**: 使用语义化的类名，避免全局样式冲突

## 使用方法

### 在 Vue 组件中引入样式

每个 Vue 组件已经通过以下方式引入了对应的样式文件：

```vue
<style scoped>
@import '@/styles/页面名称.css';
</style>
```

例如：
- `Trading.vue` → `@import '@/styles/Trading.css';`
- `Home.vue` → `@import '@/styles/Home.css';`
- `Backtest.vue` → `@import '@/styles/Backtest.css';`
- `Login.vue` → `@import '@/styles/Login.css';`

### 添加新页面样式

如果需要添加新页面的样式，请遵循以下步骤：

1. 在本目录下创建新的 CSS 文件，如 `NewPage.css`
2. 在对应的 Vue 组件中引入该样式文件
3. 更新本文档的目录结构说明

### 修改现有样式

1. 找到对应页面的 CSS 文件
2. 直接在 CSS 文件中修改样式
3. 保存后，Vite 开发服务器会自动热更新

## 样式规范

### 命名规范

- 使用 **kebab-case**（短横线分隔）命名类名
- 类名应具有语义化，反映元素的功能或内容
- 避免使用过于简短或含义不明的类名

示例：
```css
/* ✅ 推荐 */
.trading-container { }
.nav-left { }
.user-avatar { }

/* ❌ 不推荐 */
.tc { }
.nl { }
.div1 { }
```

### 选择器规范

- 优先使用类选择器，避免使用 ID 选择器
- 避免使用过于复杂的选择器链（层级不超过 3 层）
- 使用 `:deep()` 伪类覆盖 Element Plus 组件样式

示例：
```css
/* ✅ 推荐 */
.input-wrapper { }
.input-wrapper:focus-within { }
:deep(.el-button--primary) { }

/* ❌ 不推荐 */
#app > div > .container > .wrapper > input { }
```

### 颜色规范

系统采用深色主题，主要颜色包括：

- **背景色**: `#0f172a`（深蓝黑）、`#1a1a2e`（深紫黑）
- **卡片色**: `rgba(30, 41, 59, 0.6)`（半透明深灰）
- **边框色**: `rgba(71, 85, 105, 0.3)`（半透明灰）
- **主色调**: `#3b82f6`（蓝色）、`#00d4ff`（青色）
- **盈利色**: `#ef4444`（红色）
- **亏损色**: `#22c55e`（绿色）
- **文字色**: `#f1f5f9`（主文字）、`#94a3b8`（次要文字）

### 响应式设计

- 使用 `min-width`、`max-width` 等属性实现响应式布局
- 使用 CSS Grid 和 Flexbox 实现弹性布局
- 避免使用固定像素值，优先使用相对单位（rem、em、%）

## 样式覆盖说明

对于 Element Plus 组件的样式覆盖，使用 Vue 3 的 `:deep()` 伪类：

```css
:deep(.el-button--primary) {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border: none;
}
```

这样可以确保样式能够穿透到子组件内部。

## 动画规范

- 动画时长：过渡动画 `0.2s`，复杂动画 `0.3s`
- 缓动函数：`ease`（默认）、`linear`（旋转动画）
- 避免同时触发大量动画，影响性能

## 维护指南

1. **定期清理**: 删除不再使用的样式规则
2. **注释说明**: 为复杂的样式规则添加注释
3. **分组管理**: 相关样式规则放在一起，使用注释分隔不同模块
4. **复用优先**: 发现重复样式时，考虑提取为公共样式

## 注意事项

⚠️ **重要提示**：
- 不要删除 Vue 组件中的 `<style scoped>` 标签
- 修改样式后，确保验证页面显示效果
- 新增样式时，考虑与现有样式的兼容性
- 避免在 CSS 中使用 `!important`，除非确实需要覆盖内联样式

---

**最后更新**: 2026-10-18  
**维护者**: 开发团队
