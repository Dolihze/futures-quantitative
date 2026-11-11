import { defineStore } from 'pinia'
import { ref } from 'vue'

export const THEMES = [
  { value: 'gray', label: '深灰', color: '#27272a' },
  { value: 'blue', label: '深蓝', color: '#16213e' },
  { value: 'light', label: '白色', color: '#ffffff' }
]

const STORAGE_KEY = 'app-theme'
const DEFAULT_THEME = 'gray'

function readStored() {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return THEMES.some((t) => t.value === v) ? v : DEFAULT_THEME
  } catch (e) {
    return DEFAULT_THEME
  }
}

// 把主题应用到 <html>：data-theme 驱动自定义变量；非白色主题加 .dark 让 Element Plus 使用暗色变量
function applyTheme(theme, animate) {
  const root = document.documentElement
  if (animate) {
    root.classList.add('theme-transition')
    window.setTimeout(() => root.classList.remove('theme-transition'), 300)
  }
  root.setAttribute('data-theme', theme)
  root.classList.toggle('dark', theme !== 'light')
}

export const useThemeStore = defineStore('theme', () => {
  const theme = ref(readStored())

  // 首次应用（不做过渡动画）
  applyTheme(theme.value, false)

  function setTheme(next) {
    if (!THEMES.some((t) => t.value === next) || next === theme.value) return
    theme.value = next
    applyTheme(next, true)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch (e) {
      // 忽略存储失败
    }
  }

  return { theme, setTheme }
})
