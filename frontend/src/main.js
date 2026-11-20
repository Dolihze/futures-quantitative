import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './styles/theme.css'
import './styles/base.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import { useThemeStore } from './stores/theme'
import { setBackendBase } from './utils/request'
import { resolveBackendBase, waitBackendReady } from './utils/backend'

function mount() {
  const app = createApp(App)
  const pinia = createPinia()

  // 注册所有 Element Plus 图标
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }

  app.use(pinia)
  app.use(router)
  app.use(ElementPlus, { size: 'default', zIndex: 3000 })

  // 初始化主题（读取本地偏好并应用到 <html>）
  useThemeStore()

  app.mount('#app')
}

async function bootstrap() {
  const root = document.getElementById('app')
  // Tauri 打包后后端端口是运行时随机选的：先取地址，再等后端就绪，避免首屏请求 ECONNREFUSED
  if (root) root.textContent = '正在启动后端服务…'
  setBackendBase(await resolveBackendBase())
  const ready = await waitBackendReady()
  if (!ready && root) {
    root.textContent = '后端服务启动超时，请重启应用或查看日志'
    return
  }
  if (root) root.textContent = ''
  mount()
}

bootstrap()
