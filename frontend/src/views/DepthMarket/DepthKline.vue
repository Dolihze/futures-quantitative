<template>
  <div class="depth-kline">
    <div ref="chartRef" class="depth-kline-chart"></div>

    <!-- 鼠标所在 K 线的信息，固定在图表左上角（不跟随鼠标），避免遮挡价格 -->
    <div v-if="hoverBar" class="depth-kline-info">
      <span class="info-time">{{ hoverBar.time }}</span>
      <span>开 <b :class="cls(hoverBar.open)">{{ hoverBar.open }}</b></span>
      <span>高 <b :class="cls(hoverBar.high)">{{ hoverBar.high }}</b></span>
      <span>低 <b :class="cls(hoverBar.low)">{{ hoverBar.low }}</b></span>
      <span>收 <b :class="cls(hoverBar.close)">{{ hoverBar.close }}</b></span>
      <span>量 <b>{{ hoverBar.volume }}</b></span>
      <span v-if="hoverBar.position != null">仓 <b>{{ hoverBar.position }}</b></span>
      <span class="info-ticks">{{ hoverBar.ticks }} 笔</span>
      <!-- 成交性质（多开 / 空开 / 多平 / 空平…）：文件里有 BS 列才显示。多方动作红、空方动作绿 -->
      <span v-if="bsList.length" class="info-bs">
        <i v-for="x in bsList" :key="x.name" :class="x.name.startsWith('多') ? 'up' : x.name.startsWith('空') ? 'down' : ''">
          {{ x.name }} {{ x.volume }}
        </i>
      </span>
    </div>

    <div v-if="!bars.length" class="chart-empty">
      <div class="empty-icon">🕯️</div>
      <div class="empty-title">{{ emptyTitle }}</div>
      <div class="empty-desc">{{ emptyDesc }}</div>
    </div>
    <div v-if="loading" class="chart-loading">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在生成 K 线...</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { chartColors, onThemeChange } from '@/utils/chartTheme'

const props = defineProps({
  bars: { type: /** @type {import('vue').PropType<import('@/api/types').DepthKlineBar[]>} */ (Array), default: () => [] },         // [{time, open, high, low, close, volume, position, ticks, ti0, ti1, ...}]
  loading: { type: Boolean, default: false },
  selectedIndex: { type: Number, default: -1 },     // 当前选中（点击/回放所在）的 K 线序号，图上高亮
  emptyTitle: { type: String, default: '还没有数据' },
  emptyDesc: { type: String, default: '先在左侧导入历史 tick CSV' }
})
// hover：鼠标悬停某根 K 线（序号，-1 = 离开）；select：点击某根 K 线
const emit = defineEmits(['hover', 'select'])

// 红涨绿跌，与项目其它页面一致
const UP = '#dc2626'
const DOWN = '#16a34a'

const chartRef = ref(null)
let chart = null
let resizeObserver = null
const hoverIndex = ref(-1)
const hoverBar = computed(() => props.bars[hoverIndex.value] || null)

// 悬停 K 线里各类成交性质的手数，按手数从大到小；0 手的不显示
const bsList = computed(() => {
  const bs = hoverBar.value?.bs
  if (!bs) return []
  return Object.entries(bs)
    .filter(([, v]) => v)
    .map(([name, volume]) => ({ name, volume }))
    .sort((a, b) => b.volume - a.volume)
})

// 价格涨跌色：相对当前悬停 K 线的开盘价
const cls = (v) => {
  const o = hoverBar.value?.open
  if (o == null || v == null || v === o) return ''
  return v > o ? 'up' : 'down'
}

// X 轴：多交易日时显示 “MM-DD HH:mm”，单日只显示 “HH:mm”；日线显示日期
function axisLabels(bars) {
  const multiDay = new Set(bars.map((b) => b.time.slice(0, 10))).size > 1
  return bars.map((b) => {
    const t = b.time
    if (t.length <= 10) return t              // 日线
    return multiDay ? t.slice(5) : t.slice(11)
  })
}

function buildOption(c) {
  const bars = props.bars
  const labels = axisLabels(bars)
  const candle = bars.map((b) => [b.open, b.close, b.low, b.high])   // ECharts 顺序：开、收、低、高
  const vols = bars.map((b, i) => ({
    value: b.volume,
    itemStyle: { color: b.close >= b.open ? UP : DOWN }
  }))
  const poses = bars.map((b) => b.position)
  const total = bars.length
  // 默认显示最后 150 根，更早的用滑块/滚轮查看
  const start = total > 150 ? Math.round((1 - 150 / total) * 100) : 0

  const axisCommon = {
    axisLine: { lineStyle: { color: c.axisLine } },
    axisLabel: { color: c.axisLabel },
    axisTick: { show: false }
  }
  return {
    animation: false,
    backgroundColor: c.bg,
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
      label: { backgroundColor: c.crossLabelBg, color: c.axisPointerLabelText }
    },
    // 不用 ECharts 自带 tooltip：信息固定显示在左上角，同时驱动右侧盘口
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross', lineStyle: { color: c.crossColor } }, showContent: false },
    grid: [
      { left: 64, right: 56, top: 44, height: '52%' },
      { left: 64, right: 56, top: '68%', height: '10%' },
      { left: 64, right: 56, top: '81%', height: '9%' }
    ],
    xAxis: [0, 1, 2].map((gi) => ({
      type: 'category',
      gridIndex: gi,
      data: labels,
      boundaryGap: true,
      ...axisCommon,
      axisLabel: { ...axisCommon.axisLabel, show: gi === 2, hideOverlap: true },
      splitLine: { show: false }
    })),
    yAxis: [
      { scale: true, gridIndex: 0, ...axisCommon, splitLine: { lineStyle: { color: c.splitLine } },
        axisLabel: { color: c.axisLabel, margin: 6 } },
      { scale: true, gridIndex: 1, ...axisCommon, splitNumber: 2, splitLine: { show: false },
        axisLabel: { color: c.axisLabel, margin: 6 } },
      { scale: true, gridIndex: 2, ...axisCommon, splitNumber: 2, splitLine: { show: false },
        axisLabel: { color: c.axisLabel, margin: 6 } }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2], start, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, 2], bottom: 6, height: 18, start, end: 100,
        borderColor: c.sliderBorder, textStyle: { color: c.axisLabel } }
    ],
    series: [
      {
        name: 'K线', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0, data: candle,
        itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN }
      },
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: vols, barMaxWidth: 12 },
      {
        name: '持仓量', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: poses, showSymbol: false,
        lineStyle: { width: 1.2, color: c.amber }, itemStyle: { color: c.amber },
        areaStyle: { color: c.area }, silent: true
      }
    ]
  }
}

// 选中 K 线的高亮：用一条竖向 markLine（比改单根样式稳，缩放时不会错位）
function applySelection() {
  if (!chart) return
  const i = props.selectedIndex
  const bar = props.bars[i]
  const c = chartColors()
  chart.setOption({
    series: [{
      name: 'K线',
      markLine: bar
        ? {
            silent: true, symbol: 'none', animation: false,
            lineStyle: { color: c.accent, type: 'dashed', width: 1 },
            label: { show: false },
            data: [{ xAxis: i }]
          }
        : { data: [] }
    }]
  })
}

function render() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (p) => {
      if (p.componentType === 'series' && p.dataIndex != null) emit('select', p.dataIndex)
    })
    // 鼠标移动：axisPointer 的 dataIndex 即当前十字线所在 K 线
    chart.on('updateAxisPointer', (/** @type {any} */ e) => {
      const idx = e?.axesInfo?.[0]?.value
      const n = typeof idx === 'number' ? idx : -1
      if (n !== hoverIndex.value) {
        hoverIndex.value = n
        emit('hover', n)
      }
    })
    chart.getZr().on('globalout', () => {
      hoverIndex.value = -1
      emit('hover', -1)
    })
  }
  chart.setOption(buildOption(chartColors()), true)
  applySelection()
}

watch(() => props.bars, () => {
  hoverIndex.value = -1
  nextTick(render)
})
watch(() => props.selectedIndex, applySelection)
onThemeChange(() => render())

onMounted(() => {
  render()
  // 容器尺寸变化（窗口缩放、Tab 切换显示）时重新量尺寸
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartRef.value)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

defineExpose({ resize: () => chart?.resize() })
</script>

<style scoped>
.depth-kline {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.depth-kline-chart {
  width: 100%;
  height: 100%;
  border-radius: 8px;
}

.depth-kline-info {
  position: absolute;
  top: 8px;
  left: 70px;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-overlay-chart);
  border-radius: 4px;
  pointer-events: none;
}

.depth-kline-info b {
  color: var(--text-body);
  font-weight: 600;
}

.depth-kline-info b.up {
  color: var(--up);
}

.depth-kline-info b.down {
  color: var(--down);
}

.info-time {
  color: var(--accent2);
  font-weight: 600;
}

.info-ticks {
  color: var(--text-muted);
}

.info-bs {
  display: inline-flex;
  gap: 8px;
}

.info-bs i {
  font-style: normal;
  color: var(--text-secondary);
}

.info-bs i.up {
  color: var(--up);
}

.info-bs i.down {
  color: var(--down);
}

.chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 40px;
  text-align: center;
  background: var(--bg-chart);
  border-radius: 8px;
}

.empty-icon {
  font-size: 44px;
}

.empty-title {
  color: var(--text-body);
  font-size: 17px;
  font-weight: 600;
}

.empty-desc {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.chart-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg-overlay-chart);
  border-radius: 8px;
  z-index: 10;
}

.loading-spinner {
  border: 4px solid var(--spinner-track);
  border-top: 4px solid var(--primary);
  border-radius: 50%;
  width: 44px;
  height: 44px;
  animation: depth-spin 1s linear infinite;
  margin-bottom: 14px;
}

.loading-text {
  color: var(--primary);
  font-size: 14px;
  font-weight: 600;
}

@keyframes depth-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
