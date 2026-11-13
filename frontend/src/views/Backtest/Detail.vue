<template>
  <div class="backtest-container">
    <!-- 顶部导航栏 -->
    <nav class="navbar">
      <div class="nav-left">
        <router-link :to="backTo" class="back-btn">
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
            {{ result?.symbolName || params.product + '主连' }} · {{ result?.strategy.period || '-' }}分钟线 · {{ result?.stats.timeSpan || '--' }} ·
            每笔 {{ params.lots }} 手 · 不含手续费与滑点
          </span>
        </div>
        <div class="toolbar-controls">
          <el-radio-group v-model="params.days" :disabled="loading" @change="load">
            <el-radio-button v-for="o in dayOptions" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
          </el-radio-group>
          <el-button :loading="loading" @click="load">刷新</el-button>
        </div>
      </div>

      <el-alert v-if="errorMsg" class="overview-alert" type="error" :title="errorMsg" show-icon :closable="false" />
      <!-- 数据范围说明：新浪每个周期只给最近约 1023 根 K 线，数据不够所选天数时必须明说 -->
      <el-alert
        v-if="coverageNotice"
        class="overview-alert"
        type="info"
        :title="coverageNotice"
        show-icon
        :closable="false"
      />

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
            :data="pagedTrades"
            class="trade-table"
            size="small"
            highlight-current-row
            empty-text="该时间范围内没有产生交易"
            @row-click="focusTrade"
          >
            <!-- 序号只是表格里从上往下的行号（跨页连续），不是真实下单顺序 -->
            <el-table-column label="序号" width="64">
              <template #default="{ $index }">{{ (page - 1) * PAGE_SIZE + $index + 1 }}</template>
            </el-table-column>
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
          <div class="trade-pagination">
            <!-- 小号分页；「共 N 条」用 slot 自己渲染，避免为了改一句文案去引入全局中文语言包而影响其它页面 -->
            <el-pagination
              v-model:current-page="page"
              size="small"
              :page-size="PAGE_SIZE"
              :total="result.trades.length"
              layout="slot, prev, pager, next"
              background
            >
              <span class="trade-pagination-total">共 {{ result.trades.length }} 条</span>
            </el-pagination>
          </div>
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
import { buildDayOptions, clampDays } from './range'

// 成交明细每页条数
const PAGE_SIZE = 10
// 红涨绿跌（和复盘页的 K 线一致）
const UP = '#dc2626'
const DOWN = '#16a34a'

const route = useRoute()
const loading = ref(false)
const errorMsg = ref('')
const result = ref(null)
// 回测对象是总览页选中的品种主连（URL 的 product 参数），缺省为燃料油
const params = reactive({
  product: String(route.query.product || 'FU'),
  days: Number(route.query.days) || 30,
  lots: Number(route.query.lots) || 5
})
// 返回总览时带上品种和时间范围，保持用户刚才的选择
const backTo = computed(() => ({ path: '/backtest', query: { product: params.product, days: params.days } }))

// 时间范围选项按该策略周期实际可得的数据天数收敛（0 = 还没请求过）
const availableDays = ref(0)
const requestedDays = ref(0) // 最近一次请求时用户选的天数（收敛到「全部」之前）
const dayOptions = computed(() => buildDayOptions(availableDays.value))
const coverageNotice = computed(() => {
  const c = result.value?.coverage
  if (!c || !c.truncated) return ''
  return `所选 ${requestedDays.value} 天超出了可获取的数据范围，已使用全部可得数据（${c.dataFrom.slice(0, 10)} ~ ${c.dataTo.slice(0, 10)}，共 ${c.availableDays} 天）。新浪每个周期只提供最近约 1000 根 K 线（${result.value.strategy.period} 分钟线）。`
})

// 成交明细按时间倒序（最新的在最上面），再分页取当前页的 10 条。
// 序号 # 仍是回测里的第几笔（按时间正序编号），倒序只影响显示顺序。
// 回测结果本身按平仓时间升序产生，这里复制后反转，不改动原数组（K 线标记、盈利曲线都依赖原顺序）。
const page = ref(1)
const sortedTrades = computed(() => [...(result.value?.trades || [])].reverse())
const pagedTrades = computed(() => sortedTrades.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

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
      page.value = 1
      availableDays.value = res.coverage?.availableDays || 0
      // 所选天数超出可得数据时，选中项落到「全部」（结果本来就是全部数据，不必重新请求）
      requestedDays.value = params.days
      params.days = clampDays(params.days, availableDays.value)
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
    name: `${sideText(t.side)}开`,
    value: [t.entryIndex, t.entryPrice],
    symbol: 'triangle',
    symbolRotate: t.side === 'long' ? 0 : 180,
    symbolSize: 14,
    itemStyle: { color: sideColor(t.side) },
    trade: t,
    kind: 'entry'
  }))
  const exitPoints = trades.map((t) => ({
    name: '平',
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
            html += `<div style="margin-top:4px">${sideText(t.side)}单 ${open ? '开仓 @ ' + t.entryPrice.toFixed(2) : `平仓(${t.reason}) @ ${t.exitPrice.toFixed(2)}，盈亏 ${fmtMoney(t.profit)}`}</div>`
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
  const labels = curve.map((p) => (p.tradeNo === 0 ? '起点' : `第${p.tradeNo}笔 ${p.time.slice(5, 16)}`))
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
