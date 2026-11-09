<template>
  <div class="kline-view">
    <div class="kline-toolbar">
      <el-select v-model="day" placeholder="选择交易日" size="small" style="width: 150px" :disabled="!days.length">
        <el-option v-for="d in daysDesc" :key="d" :label="d" :value="d" />
      </el-select>
      <el-select
        v-model="symbol"
        placeholder="选择合约"
        size="small"
        style="width: 150px"
        :disabled="!symbols.length"
      >
        <el-option v-for="s in symbols" :key="s.symbol" :label="`${s.symbol}（${s.trades.length} 笔）`" :value="s.symbol" />
      </el-select>
      <span class="kline-legend">
        <i class="lg lg-buy">▲</i>买开/买平
        <i class="lg lg-sell">▼</i>卖开/卖平
        <i class="lg lg-win">━</i>盈利
        <i class="lg lg-loss">━</i>亏损
      </span>
    </div>

    <div v-if="notice" class="kline-notice">⚠ {{ notice }}</div>

    <div class="kline-body">
      <div ref="chartRef" class="kline-chart"></div>

      <div v-if="!days.length" class="chart-empty">
        <div class="empty-icon">🕯️</div>
        <div class="empty-title">还没有数据</div>
        <div class="empty-desc">先在左侧导入交易记录</div>
      </div>
      <div v-else-if="!loading && !symbols.length" class="chart-empty">
        <div class="empty-icon">🔍</div>
        <div class="empty-title">{{ day }} 没有成交记录</div>
        <div class="empty-desc">请换一个交易日，或检查左侧的交易品种筛选</div>
      </div>
      <div v-else-if="!loading && klineUnavailable" class="chart-empty">
        <div class="empty-icon">🕯️</div>
        <div class="empty-title">取不到这一天的 1 分钟 K 线</div>
        <div class="empty-desc">{{ klineUnavailable }}</div>
      </div>
      <div v-if="loading" class="chart-loading">
        <div class="loading-spinner"></div>
        <div class="loading-text">正在加载 K 线和交易...</div>
      </div>
    </div>

    <div v-if="hiddenTrades.length" class="kline-hidden">
      <div class="kline-hidden-title">以下交易有一端不在当天的 K 线上，只标出了当天的那一端：</div>
      <div v-for="(t, i) in hiddenTrades" :key="i" class="kline-hidden-item">{{ t }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getReviewDayTrades, getReviewDayKline } from '@/api'

const props = defineProps({
  reviewId: { type: String, default: '' },
  products: { type: Array, default: () => [] },   // 左侧筛选的品种，空 = 全部
  days: { type: Array, default: () => [] }        // 文件里有成交的全部交易日（升序）
})

const chartRef = ref(null)
let chart = null

const day = ref('')
const symbol = ref('')
const symbols = ref([])          // [{ symbol, trades }]
const loading = ref(false)
const notice = ref('')
const klineUnavailable = ref('')
const hiddenTrades = ref([])
const kline = ref([])            // 当前合约当天的 K 线
const period = ref(1)            // 实际取到的 K 线周期（分钟）
const daysDesc = computed(() => [...props.days].reverse())

const currentTrades = computed(() => symbols.value.find((s) => s.symbol === symbol.value)?.trades || [])

// ---------- 数据加载 ----------
// 防止快速切换日期/合约时，旧请求的结果覆盖新请求
let seq = 0

async function loadDay() {
  if (!props.reviewId || !day.value) return
  const my = ++seq
  loading.value = true
  notice.value = ''
  klineUnavailable.value = ''
  try {
    const res = await getReviewDayTrades({ reviewId: props.reviewId, day: day.value, products: props.products.join(',') })
    if (my !== seq) return
    symbols.value = res.symbols || []
    // 保持已选合约；没有或不在当天的合约里时选第一个
    if (!symbols.value.some((s) => s.symbol === symbol.value)) symbol.value = symbols.value[0]?.symbol || ''
    if (!symbol.value) {
      kline.value = []
      renderChart()
      return
    }
    await loadKline(my)
  } catch (e) {
    if (my !== seq) return
    notice.value = e?.response?.data?.message || '加载交易失败，请重试'
    symbols.value = []
    kline.value = []
    renderChart()
  } finally {
    if (my === seq) loading.value = false
  }
}

async function loadKline(my) {
  try {
    const res = await getReviewDayKline({ symbol: symbol.value, day: day.value })
    if (my !== seq) return
    if (!res.available) {
      kline.value = []
      klineUnavailable.value = res.message || '没有 K 线数据'
    } else {
      kline.value = res.data
      period.value = res.period || 1
      // 新浪的 K 线接口没有日期参数，每个周期只给最近 1023 根：1 分钟线只有最近约 3 个交易日。
      // 取不到 1 分钟线时后端自动换成更长的周期，这里要告诉用户现在看到的不是 1 分钟线。
      const msgs = []
      if (period.value !== 1) {
        msgs.push(`这一天的 1 分钟 K 线已经取不到（新浪只保留最近约 3 个交易日），当前显示的是 ${period.value} 分钟 K 线，成交点仍按真实成交时间标在所在的那根 K 线上`)
      }
      if (res.partial) msgs.push('这一天的开头部分可能缺失')
      notice.value = msgs.join('；')
    }
  } catch (e) {
    if (my !== seq) return
    kline.value = []
    klineUnavailable.value = e?.response?.data?.message || '获取 K 线失败，请检查网络后重试'
  }
  renderChart()
}

// 只换合约时不用重新取交易，只取这个合约的 K 线
async function onSymbolChange() {
  if (!symbol.value) return
  const my = ++seq
  loading.value = true
  notice.value = ''
  klineUnavailable.value = ''
  try {
    await loadKline(my)
  } finally {
    if (my === seq) loading.value = false
  }
}

// ---------- 绘图 ----------
const pad2 = (n) => String(n).padStart(2, '0')
const toMs = (s) => new Date(s.replace(' ', 'T')).getTime()

// 红涨绿跌（和项目其它页面一致）
const UP = '#ef4444'
const DOWN = '#22c55e'

function renderChart() {
  if (!chart) return
  const bars = kline.value
  if (!bars.length) {
    chart.clear()
    hiddenTrades.value = []
    return
  }
  // 横轴用类目轴（第几根 K 线），夜盘到日盘之间的休市时间不留空白。
  // 新浪 K 线的时间戳是这根 K 线的“结束时间”（1 分钟线第一根是 09:01，5 分钟线第一根是 09:05，区间右闭），
  // 所以成交放在“结束时间不早于成交时间的第一根”里：09:03 的成交在 5 分钟线的 09:05 那根，09:05:00 整也在 09:05 那根。
  // 用精确到秒的时间比较，不能截断到分钟（09:05:30 应该落在 09:10 那根）。
  const ends = bars.map((b) => toMs(b.time))
  const periodMs = Math.max(period.value, 1) * 60000
  const indexOf = (timeStr) => {
    const k = toMs(timeStr)
    let lo = 0
    let hi = ends.length - 1
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (ends[mid] < k) lo = mid + 1
      else hi = mid
    }
    return lo
  }
  // 超出这天 K 线范围（比如开仓在前一个交易日、或在集合竞价时段）的成交不画，列在图下面。
  // 第一根 K 线覆盖的区间是 (end - 周期, end]，之前一个周期以内的成交（集合竞价略早于开盘）仍然贴到第一根上
  const inRange = (timeStr) => {
    const k = toMs(timeStr)
    return k >= ends[0] - 2 * periodMs && k <= ends[ends.length - 1] + periodMs
  }

  const labels = bars.map((b, i) => {
    const t = b.time
    const hm = t.slice(11, 16)
    // 夜盘的第一根（日期和上一根不同）带上日期，方便看出跨日
    const newDay = i === 0 || t.slice(0, 10) !== bars[i - 1].time.slice(0, 10)
    return newDay ? `${t.slice(5, 10)}\n${hm}` : hm
  })

  const sideColor = (side, isOpen) => ((side === '多') === isOpen ? UP : DOWN)   // 买（开多 / 平空）红，卖绿
  const points = []   // 开、平仓标记
  const links = []    // 开仓到平仓的连线
  const hidden = []
  currentTrades.value.forEach((t, n) => {
    const openOk = t.openTime && inRange(t.openTime)
    const closeOk = t.closeTime && inRange(t.closeTime)
    const verb = `${t.side === '多' ? '买' : '卖'}开 → ${t.side === '多' ? '卖' : '买'}平`
    if (t.openTime && !openOk) hidden.push(`${symbol.value} ${t.side}单 ${t.lots} 手：开仓 ${t.openTime} @ ${t.openPrice}（不在当天） → 平仓 ${t.closeTime} @ ${t.closePrice}，盈亏 ${t.pnl}`)
    if (!t.openTime) hidden.push(`${symbol.value} ${t.side}单 ${t.lots} 手：平仓 ${t.closeTime} @ ${t.closePrice}（文件里找不到对应的开仓），盈亏 ${t.pnl}`)
    if (t.closeTime && !closeOk) hidden.push(`${symbol.value} ${t.side}单 ${t.lots} 手：开仓 ${t.openTime} @ ${t.openPrice} → 平仓 ${t.closeTime} @ ${t.closePrice}（不在当天），盈亏 ${t.pnl}`)
    const winColor = t.pnl > 0 ? UP : t.pnl < 0 ? DOWN : '#94a3b8'
    const info = { n, t, verb }
    if (openOk) {
      points.push({
        name: 'open',
        value: [indexOf(t.openTime), t.openPrice],
        symbol: 'triangle',
        symbolRotate: t.side === '多' ? 0 : 180,
        symbolSize: 12,
        itemStyle: { color: sideColor(t.side, true), borderColor: '#fff', borderWidth: 1 },
        info: { ...info, kind: '开仓', time: t.openTime, price: t.openPrice }
      })
    }
    if (closeOk) {
      points.push({
        name: 'close',
        value: [indexOf(t.closeTime), t.closePrice],
        symbol: 'diamond',
        symbolSize: 12,
        itemStyle: { color: sideColor(t.side, false), borderColor: '#fff', borderWidth: 1 },
        info: { ...info, kind: '平仓', time: t.closeTime, price: t.closePrice }
      })
    }
    if (openOk && closeOk) {
      links.push({
        coords: [[indexOf(t.openTime), t.openPrice], [indexOf(t.closeTime), t.closePrice]],
        lineStyle: { color: winColor },
        info: { ...info, kind: '连线', time: t.closeTime, price: t.closePrice }
      })
    }
  })
  hiddenTrades.value = hidden

  const lows = bars.map((b) => b.low)
  const highs = bars.map((b) => b.high)
  // y 轴要把所有成交价也包进去（成交价理论上都在 K 线的高低之内，但取整/数据缺口时可能略超出）
  const prices = points.map((p) => p.value[1])
  const yMin = Math.min(...lows, ...prices)
  const yMax = Math.max(...highs, ...prices)
  const pad = (yMax - yMin) * 0.05 || 1

  chart.setOption(
    {
      backgroundColor: '#16213e',
      animation: false,
      grid: { left: 70, right: 40, top: 30, bottom: 90 },
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        borderColor: '#00d4ff',
        textStyle: { color: '#fff' },
        formatter: (p) => {
          if (p.seriesType === 'candlestick') {
            const b = bars[p.dataIndex]
            return `<div style="font-weight:bold;margin-bottom:4px">${b.time}</div>
              <div>开 ${b.open} · 高 ${b.high} · 低 ${b.low} · 收 ${b.close}</div>
              <div style="color:#94a3b8">成交量 ${b.volume}</div>`
          }
          const info = p.data?.info
          if (!info) return ''
          // 一笔平仓被拆成几笔、或几笔交易共用同一个开/平仓点时，点会重叠；把落在同一根 K 线、同一价位的全部列出来
          const same = (p.seriesType === 'scatter'
            ? points.filter((q) => q.value[0] === p.data.value[0] && q.value[1] === p.data.value[1] && q.name === p.data.name)
            : [p.data]
          ).map((q) => q.info)
          const block = ({ t, kind, verb, price }) => {
            const pc = t.pnl > 0 ? UP : t.pnl < 0 ? DOWN : '#fff'
            const pnl = `${t.pnl > 0 ? '+' : ''}${t.pnl.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            const head = kind === '连线' ? `${verb} · ${t.lots} 手` : `${kind} · ${verb.split(' → ')[kind === '开仓' ? 0 : 1]} ${t.lots} 手 @ ${price}`
            return `<div style="font-weight:bold;margin-bottom:4px">${head}</div>
              <div>开：${t.openTime ?? '—'} @ ${t.openPrice ?? '—'}</div>
              <div>平：${t.closeTime} @ ${t.closePrice}</div>
              <div>盈亏：<b style="color:${pc}">${pnl}</b></div>`
          }
          return same.map(block).join('<div style="height:1px;background:#475569;margin:6px 0"></div>')
        }
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: true,
        axisLine: { lineStyle: { color: '#475569' } },
        axisLabel: { color: '#94a3b8', fontSize: 11, lineHeight: 15, hideOverlap: true },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        scale: true,
        min: Math.floor(yMin - pad),
        max: Math.ceil(yMax + pad),
        axisLine: { show: true, lineStyle: { color: '#475569' } },
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: 'rgba(71, 85, 105, 0.3)' } }
      },
      // 默认只显示全天；一天有 300~500 根 1 分钟线，鼠标滚轮 / 拖滑块放大看细节
      dataZoom: [
        { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
        { type: 'slider', xAxisIndex: 0, filterMode: 'none', height: 24, bottom: 20, borderColor: '#334155', textStyle: { color: '#94a3b8' } }
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          // ECharts 的 candlestick 数据顺序是 [开, 收, 低, 高]；红涨绿跌
          data: bars.map((b) => [b.open, b.close, b.low, b.high]),
          itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN }
        },
        {
          name: '交易连线',
          type: 'lines',
          coordinateSystem: 'cartesian2d',
          z: 5,
          lineStyle: { width: 2, opacity: 0.9 },
          data: links
        },
        {
          name: '成交点',
          type: 'scatter',
          z: 10,
          data: points
        }
      ]
    },
    true
  )
}

// ---------- 生命周期 ----------
const handleResize = () => chart && chart.resize()

// 日期列表变化（导入了新文件）：默认选最近一个交易日
watch(
  () => props.days,
  (list) => {
    if (!list.length) {
      day.value = ''
      symbols.value = []
      kline.value = []
      symbol.value = ''
      renderChart()
      return
    }
    if (!list.includes(day.value)) day.value = list[list.length - 1]
  },
  { immediate: true }
)
watch(() => [props.reviewId, props.products.join(','), day.value], () => loadDay())
watch(symbol, (n, o) => {
  // loadDay 里改合约不要重复请求；用户手动切合约才单独取 K 线
  if (n && o && n !== o && !loading.value) onSymbolChange()
})

onMounted(async () => {
  await nextTick()
  chart = echarts.init(chartRef.value)
  window.addEventListener('resize', handleResize)
  loadDay()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
/* 空状态 / 加载中的样式（chart-empty、chart-loading 等）和复盘页共用同一份 */
@import '@/styles/Review.css';

.kline-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.kline-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 0 10px;
}
.kline-legend {
  margin-left: auto;
  color: #94a3b8;
  font-size: 12px;
}
.kline-legend .lg {
  font-style: normal;
  margin: 0 4px 0 12px;
}
.lg-buy,
.lg-win {
  color: #ef4444;
}
.lg-sell,
.lg-loss {
  color: #22c55e;
}
.kline-notice {
  color: #fbbf24;
  font-size: 12px;
  padding: 0 0 8px;
}
.kline-body {
  position: relative;
  flex: 1;
  min-height: 420px;
}
.kline-chart {
  width: 100%;
  height: 100%;
  min-height: 420px;
}
.kline-hidden {
  margin-top: 10px;
  padding: 8px 12px;
  background: rgba(251, 191, 36, 0.08);
  border-radius: 6px;
  font-size: 12px;
  color: #cbd5e1;
  max-height: 120px;
  overflow: auto;
}
.kline-hidden-title {
  color: #fbbf24;
  margin-bottom: 4px;
}
.kline-hidden-item {
  line-height: 1.7;
}
</style>
