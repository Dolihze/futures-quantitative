<template>
  <div class="backtest-container">
    <!-- 顶部导航栏 -->
    <nav class="navbar">
      <div class="nav-left">
        <router-link to="/backtest" class="back-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          返回策略总览
        </router-link>
        <span class="nav-title">{{ result?.strategy.name || '策略详情' }}</span>
      </div>
      <div class="nav-right">
        <UserMenu />
      </div>
    </nav>

    <div class="detail-page">
      <!-- 工具条 -->
      <div class="overview-toolbar">
        <div class="toolbar-title">
          <h2>{{ result?.strategy.name || '--' }}</h2>
          <span class="toolbar-sub">
            {{ params.symbol }} · {{ result?.strategy.period || '-' }}分钟线 · {{ result?.stats.timeSpan || '--' }} ·
            每笔 {{ params.lots }} 手 · 不含手续费与滑点
          </span>
        </div>
        <div class="toolbar-controls">
          <el-radio-group v-model="params.days" @change="load">
            <el-radio-button v-for="d in DAY_OPTIONS" :key="d" :value="d">{{ d }}天</el-radio-button>
          </el-radio-group>
          <el-button :loading="loading" @click="load">刷新</el-button>
        </div>
      </div>

      <el-alert v-if="errorMsg" class="overview-alert" type="error" :title="errorMsg" show-icon :closable="false" />

      <div v-if="result" class="detail-body">
        <p class="detail-desc">{{ result.strategy.description }}</p>

        <!-- 核心指标 -->
        <div class="stat-grid">
          <div v-for="item in statItems" :key="item.label" class="stat-item">
            <div class="stat-label">{{ item.label }}</div>
            <div class="stat-value" :class="item.cls">{{ item.value }}</div>
            <div v-if="item.sub" class="stat-sub">{{ item.sub }}</div>
          </div>
        </div>

        <!-- K 线 + 买卖点 -->
        <section class="detail-card">
          <div class="detail-card-head">
            <h3>K线与买卖点</h3>
            <div class="legend">
              <span class="legend-item"><i class="lg-tri up"></i>多头开仓</span>
              <span class="legend-item"><i class="lg-tri down"></i>空头开仓</span>
              <span class="legend-item"><i class="lg-dot"></i>平仓</span>
              <span class="legend-item"><i class="lg-line up"></i>盈利</span>
              <span class="legend-item"><i class="lg-line down"></i>亏损</span>
            </div>
          </div>
          <div ref="klineRef" class="detail-kline"></div>
        </section>

        <!-- 盈利曲线 -->
        <section class="detail-card">
          <div class="detail-card-head">
            <h3>盈利曲线</h3>
            <span class="detail-card-sub">累计盈亏（元），起始资金 {{ result.initialCapital }}</span>
          </div>
          <div ref="equityRef" class="detail-equity"></div>
        </section>

        <!-- 成交明细 -->
        <section class="detail-card">
          <div class="detail-card-head">
            <h3>成交明细</h3>
            <span class="detail-card-sub">共 {{ result.trades.length }} 笔，点击一行可在 K 线上定位</span>
          </div>
          <el-table
            :data="result.trades"
            class="trade-table"
            size="small"
            max-height="420"
            highlight-current-row
            empty-text="该时间范围内没有产生交易"
            @row-click="focusTrade"
          >
            <el-table-column prop="no" label="#" width="56" />
            <el-table-column label="方向" width="64">
              <template #default="{ row }">
                <span :class="row.side === 'long' ? 'positive' : 'negative'">{{ sideText(row.side) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="entryTime" label="开仓时间" min-width="150" />
            <el-table-column label="开仓价" width="90" align="right">
              <template #default="{ row }">{{ row.entryPrice.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="exitTime" label="平仓时间" min-width="150" />
            <el-table-column label="平仓价" width="90" align="right">
              <template #default="{ row }">{{ row.exitPrice.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="lots" label="手数" width="60" align="right" />
            <el-table-column label="止盈 / 止损价" min-width="130" align="right">
              <template #default="{ row }">{{ row.takeProfit.toFixed(2) }} / {{ row.stopLoss.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="reason" label="平仓原因" width="90" />
            <el-table-column label="持仓K线" width="80" align="right">
              <template #default="{ row }">{{ row.holdBars }}</template>
            </el-table-column>
            <el-table-column label="盈亏(元)" width="100" align="right">
              <template #default="{ row }">
                <span :class="pnlClass(row.profit)">{{ fmtMoney(row.profit) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="账户权益" width="100" align="right">
              <template #default="{ row }">{{ row.capital.toFixed(2) }}</template>
            </el-table-column>
          </el-table>
        </section>
      </div>
    </div>

    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在回测...</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import { runBacktest } from '@/api'
import { chartColors, onThemeChange } from '@/utils/chartTheme'
import { fmtMoney, fmtRatio, pnlClass, sideText } from './format'

const DAY_OPTIONS = [7, 30, 60, 90]
// 红涨绿跌（和复盘页的 K 线一致）
const UP = '#dc2626'
const DOWN = '#16a34a'

const route = useRoute()
const loading = ref(false)
const errorMsg = ref('')
const result = ref(null)
const params = reactive({
  symbol: String(route.query.symbol || 'FU2611'),
  days: Number(route.query.days) || 30,
  lots: Number(route.query.lots) || 5
})

const klineRef = ref(null)
const equityRef = ref(null)
let klineChart = null
let equityChart = null

// ---------- 数据 ----------
let seq = 0

async function load() {
  const my = ++seq
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await runBacktest({ strategy: route.params.strategyId, ...params })
    if (my !== seq) return
    if (!res.success) {
      errorMsg.value = res.message || '回测失败'
      result.value = null
    } else {
      result.value = res
    }
  } catch (e) {
    if (my !== seq) return
    errorMsg.value = e?.response?.data?.message || e?.message || '加载失败，请检查后端是否启动'
    result.value = null
  } finally {
    if (my === seq) loading.value = false
  }
  if (my === seq) {
    await nextTick()
    renderAll()
  }
}

// ---------- 统计面板 ----------
const statItems = computed(() => {
  const s = result.value?.stats
  if (!s) return []
  const has = s.tradeCount > 0
  return [
    { label: '胜率', value: has ? `${s.winRate.toFixed(2)}%` : '--', sub: `${s.winCount} 胜 / ${s.lossCount} 负`, cls: !has ? 'neutral' : s.winRate >= 50 ? 'positive' : 'negative' },
    { label: '盈亏比', value: fmtRatio(s), sub: `均盈 ${s.avgWin.toFixed(0)} / 均亏 ${s.avgLoss.toFixed(0)}`, cls: s.plRatio === null ? 'neutral' : s.plRatio >= 1 ? 'positive' : 'negative' },
    { label: '总盈亏(元)', value: fmtMoney(s.totalProfit), sub: `收益率 ${s.returnPct.toFixed(2)}%`, cls: pnlClass(s.totalProfit) },
    { label: '交易笔数', value: String(s.tradeCount), sub: `多 ${s.longCount} / 空 ${s.shortCount}`, cls: 'neutral' },
    { label: '最大回撤', value: `${s.maxDrawdown.toFixed(0)}`, sub: `${s.maxDrawdownPct.toFixed(2)}%`, cls: s.maxDrawdown > 0 ? 'negative' : 'neutral' },
    { label: '盈利因子', value: s.profitFactor === null ? (s.winCount > 0 ? '∞' : '--') : s.profitFactor.toFixed(2), sub: '总盈利 / 总亏损', cls: 'neutral' },
    { label: '单笔最大盈 / 亏', value: `${fmtMoney(s.maxWin)}`, sub: `亏 ${s.maxLoss.toFixed(2)}`, cls: pnlClass(s.maxWin) },
    { label: '最大连胜 / 连亏', value: `${s.maxWinStreak} / ${s.maxLossStreak}`, sub: `平均持仓 ${s.avgHoldBars} 根K线`, cls: 'neutral' },
    { label: '多头胜率', value: s.longCount ? `${s.longWinRate.toFixed(1)}%` : '--', sub: `盈亏 ${fmtMoney(s.longProfit)}`, cls: 'neutral' },
    { label: '空头胜率', value: s.shortCount ? `${s.shortWinRate.toFixed(1)}%` : '--', sub: `盈亏 ${fmtMoney(s.shortProfit)}`, cls: 'neutral' }
  ]
})

// ---------- 图表 ----------
// 容器在 v-if 里：失败后再成功时 DOM 是新建的，旧图表实例还绑在已销毁的节点上，需要重建
function ensureCharts() {
  if (klineChart && klineChart.getDom() !== klineRef.value) {
    klineChart.dispose()
    klineChart = null
  }
  if (equityChart && equityChart.getDom() !== equityRef.value) {
    equityChart.dispose()
    equityChart = null
  }
  if (klineRef.value && !klineChart) klineChart = echarts.init(klineRef.value)
  if (equityRef.value && !equityChart) equityChart = echarts.init(equityRef.value)
}

function renderAll() {
  if (!result.value) return
  ensureCharts()
  renderKline()
  renderEquity()
}

// 开仓三角：尖朝上 = 多头，尖朝下 = 空头；平仓圆点。颜色都按这笔交易的方向（多红空绿），
// 连线颜色按这笔交易的盈亏（盈利红、亏损绿）。
function renderKline() {
  if (!klineChart || !result.value) return
  const c = chartColors()
  const bars = result.value.kline
  const trades = result.value.trades
  const sideColor = (side) => (side === 'long' ? UP : DOWN)

  const entryPoints = trades.map((t) => ({
    name: `#${t.no} ${sideText(t.side)}开`,
    value: [t.entryIndex, t.entryPrice],
    symbol: 'triangle',
    symbolRotate: t.side === 'long' ? 0 : 180,
    symbolSize: 14,
    itemStyle: { color: sideColor(t.side) },
    trade: t,
    kind: 'entry'
  }))
  const exitPoints = trades.map((t) => ({
    name: `#${t.no} 平`,
    value: [t.exitIndex, t.exitPrice],
    symbol: 'circle',
    symbolSize: 9,
    itemStyle: { color: sideColor(t.side), borderColor: c.markerBorder, borderWidth: 1 },
    trade: t,
    kind: 'exit'
  }))
  const links = trades.map((t) => [
    {
      coord: [t.entryIndex, t.entryPrice],
      lineStyle: { color: t.profit > 0 ? UP : t.profit < 0 ? DOWN : c.text, width: 1.5, type: 'dashed' }
    },
    { coord: [t.exitIndex, t.exitPrice] }
  ])

  const axisLabelFmt = (idx) => {
    const t = bars[idx]?.time
    if (!t) return ''
    return `${t.slice(5, 10)}\n${t.slice(11, 16)}`
  }

  klineChart.setOption(
    {
      animation: false,
      backgroundColor: c.bg,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        backgroundColor: c.tooltipBg,
        borderColor: c.accent,
        textStyle: { color: c.tooltipText },
        formatter: (ps) => {
          const k = ps.find((p) => p.seriesType === 'candlestick')
          if (!k) return ''
          const b = bars[k.dataIndex]
          const here = trades.filter((t) => t.entryIndex === k.dataIndex || t.exitIndex === k.dataIndex)
          let html = `<div style="font-weight:bold;margin-bottom:4px">${b.time}</div>
            <div>开 ${b.open.toFixed(2)} · 高 ${b.high.toFixed(2)} · 低 ${b.low.toFixed(2)} · 收 ${b.close.toFixed(2)}</div>
            <div>成交量 ${b.volume}</div>`
          for (const t of here) {
            const open = t.entryIndex === k.dataIndex
            html += `<div style="margin-top:4px">#${t.no} ${sideText(t.side)}单 ${open ? '开仓 @ ' + t.entryPrice.toFixed(2) : `平仓(${t.reason}) @ ${t.exitPrice.toFixed(2)}，盈亏 ${fmtMoney(t.profit)}`}</div>`
          }
          return html
        }
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: { left: 70, right: 40, top: 20, bottom: 70 },
      xAxis: {
        type: 'category',
        data: bars.map((_, i) => i),
        axisLine: { lineStyle: { color: c.axisLine } },
        axisTick: { show: false },
        axisLabel: { color: c.axisLabel, formatter: axisLabelFmt, hideOverlap: true }
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLine: { lineStyle: { color: c.axisLine } },
        axisLabel: { color: c.axisLabel },
        splitLine: { lineStyle: { color: c.splitLine } }
      },
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        {
          type: 'slider',
          bottom: 10,
          height: 20,
          borderColor: c.sliderBorder,
          backgroundColor: c.panel,
          dataBackground: { lineStyle: { color: c.accent }, areaStyle: { color: `rgba(${c.accentRgb}, 0.2)` } }
        }
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          // ECharts 顺序：[开, 收, 低, 高]
          data: bars.map((b) => [b.open, b.close, b.low, b.high]),
          itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN },
          markLine: { silent: true, symbol: 'none', label: { show: false }, data: links }
        },
        {
          name: '开仓',
          type: 'scatter',
          data: entryPoints,
          z: 10,
          tooltip: { show: false }
        },
        {
          name: '平仓',
          type: 'scatter',
          data: exitPoints,
          z: 10,
          tooltip: { show: false }
        }
      ]
    },
    true
  )
}

function renderEquity() {
  if (!equityChart || !result.value) return
  const c = chartColors()
  const base = result.value.initialCapital
  const curve = result.value.equity
  // 曲线按「第几笔交易」画：每笔平仓后的累计盈亏，不用时间轴，避免休市时间拉出长直线
  const labels = curve.map((p) => (p.tradeNo === 0 ? '起点' : `#${p.tradeNo} ${p.time.slice(5, 16)}`))
  const values = curve.map((p) => +(p.equity - base).toFixed(2))
  const last = values[values.length - 1] || 0
  const color = last > 0 ? UP : last < 0 ? DOWN : c.muted

  equityChart.setOption(
    {
      animation: false,
      backgroundColor: c.bg,
      tooltip: {
        trigger: 'axis',
        backgroundColor: c.tooltipBg,
        borderColor: c.accent,
        textStyle: { color: c.tooltipText },
        formatter: (ps) => `${ps[0].axisValue}<br/>累计盈亏 ${fmtMoney(ps[0].value)} 元<br/>账户权益 ${(base + ps[0].value).toFixed(2)}`
      },
      grid: { left: 70, right: 40, top: 20, bottom: 40 },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: false,
        axisLine: { lineStyle: { color: c.axisLine } },
        axisLabel: { color: c.axisLabel, hideOverlap: true },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLine: { lineStyle: { color: c.axisLine } },
        axisLabel: { color: c.axisLabel },
        splitLine: { lineStyle: { color: c.splitLine } }
      },
      dataZoom: [{ type: 'inside' }],
      series: [
        {
          type: 'line',
          data: values,
          symbol: 'circle',
          symbolSize: 5,
          lineStyle: { width: 2, color },
          itemStyle: { color },
          areaStyle: { color, opacity: 0.12, origin: 0 },
          markLine: {
            silent: true,
            symbol: 'none',
            label: { show: false },
            lineStyle: { color: c.muted, type: 'dashed' },
            data: [{ yAxis: 0 }]
          }
        }
      ]
    },
    true
  )
}

// 点击成交明细：把 K 线窗口移到这笔交易附近，并弹出提示
function focusTrade(row) {
  if (!klineChart || !result.value) return
  const total = result.value.kline.length
  const span = Math.max(row.exitIndex - row.entryIndex, 10)
  const from = Math.max(row.entryIndex - span, 0)
  const to = Math.min(row.exitIndex + span, total - 1)
  klineChart.dispatchAction({ type: 'dataZoom', startValue: from, endValue: to })
  klineChart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: row.entryIndex })
  klineRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function handleResize() {
  klineChart?.resize()
  equityChart?.resize()
}

onThemeChange(() => renderAll())

onMounted(() => {
  window.addEventListener('resize', handleResize)
  load()
})

onUnmounted(() => {
  seq++
  window.removeEventListener('resize', handleResize)
  klineChart?.dispose()
  equityChart?.dispose()
  klineChart = equityChart = null
})
</script>

<style scoped>
@import '@/styles/Backtest.css';
</style>
