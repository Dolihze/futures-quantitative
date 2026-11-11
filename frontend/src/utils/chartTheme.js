import { watch } from 'vue'
import { useThemeStore } from '@/stores/theme'

// ECharts 无法直接读取 CSS 变量，这里集中维护三套主题的图表配色。
// 涨跌色（up / down）不随主题变化，保持红涨绿跌。
const PALETTES = {
  gray: {
    bg: '#202024',
    panel: '#2e2e33',
    accent: '#38bdf8',
    accentRgb: '56, 189, 248',
    tooltipBg: 'rgba(0, 0, 0, 0.8)',
    tooltipBgLight: 'rgba(0, 0, 0, 0.6)',
    tooltipText: '#ffffff',
    axisLine: '#3f3f46',
    axisLineSoft: '#52525b',
    axisLabel: '#a1a1aa',
    splitLine: '#2e2e33',
    splitLineSoft: 'rgba(113, 113, 122, 0.3)',
    sliderBorder: '#3f3f46',
    text: '#a1a1aa',
    textStrong: '#d4d4d8',
    muted: '#71717a',
    divider: '#52525b',
    neutral: '#ffffff',
    area: 'rgba(161, 161, 170, 0.14)',
    markerBorder: '#ffffff',
    markerFill: '#ffffff',
    crossColor: '#b9bec9',
    crossLabelBg: '#6a7985',
    axisPointerLabelText: '#ffffff',
    sky: '#7dd3fc',
    amber: '#fbbf24'
  },
  blue: {
    bg: '#16213e',
    panel: '#0f3460',
    accent: '#00d4ff',
    accentRgb: '0, 212, 255',
    tooltipBg: 'rgba(0, 0, 0, 0.8)',
    tooltipBgLight: 'rgba(0, 0, 0, 0.6)',
    tooltipText: '#ffffff',
    axisLine: '#333333',
    axisLineSoft: '#475569',
    axisLabel: '#aaaaaa',
    splitLine: '#2a2a3e',
    splitLineSoft: 'rgba(71, 85, 105, 0.3)',
    sliderBorder: '#334155',
    text: '#94a3b8',
    textStrong: '#cbd5e1',
    muted: '#64748b',
    divider: '#475569',
    neutral: '#ffffff',
    area: 'rgba(148, 163, 184, 0.14)',
    markerBorder: '#ffffff',
    markerFill: '#ffffff',
    crossColor: '#b9bec9',
    crossLabelBg: '#6a7985',
    axisPointerLabelText: '#ffffff',
    sky: '#7dd3fc',
    amber: '#fbbf24'
  },
  light: {
    bg: '#ffffff',
    panel: '#eef2f7',
    accent: '#2563eb',
    accentRgb: '37, 99, 235',
    tooltipBg: 'rgba(255, 255, 255, 0.96)',
    tooltipBgLight: 'rgba(255, 255, 255, 0.96)',
    tooltipText: '#1e293b',
    axisLine: '#cbd5e1',
    axisLineSoft: '#94a3b8',
    axisLabel: '#64748b',
    splitLine: '#e2e8f0',
    splitLineSoft: 'rgba(148, 163, 184, 0.3)',
    sliderBorder: '#cbd5e1',
    text: '#475569',
    textStrong: '#334155',
    muted: '#64748b',
    divider: '#cbd5e1',
    neutral: '#0f172a',
    area: 'rgba(100, 116, 139, 0.14)',
    markerBorder: '#334155',
    markerFill: '#334155',
    crossColor: '#64748b',
    crossLabelBg: '#475569',
    axisPointerLabelText: '#ffffff',
    sky: '#0284c7',
    amber: '#b45309'
  }
}

// 当前主题的图表配色
export function chartColors() {
  const theme = useThemeStore().theme
  return PALETTES[theme] || PALETTES.gray
}

// 主题变化时执行回调（用于重绘图表）。需在组件 setup 中调用，随组件自动销毁。
export function onThemeChange(callback) {
  const store = useThemeStore()
  watch(
    () => store.theme,
    () => callback(chartColors())
  )
}
