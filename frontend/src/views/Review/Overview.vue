<template>
  <div class="ov-container">
    <!-- 顶部导航栏 -->
    <nav class="navbar">
      <div class="nav-left">
        <router-link to="/" class="back-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          返回首页
        </router-link>
        <span class="ov-nav-title">交易复盘 · 账户分析</span>
      </div>
      <div class="nav-right">
        <UserMenu />
      </div>
    </nav>

    <div class="ov-body">
      <!-- 时间范围：近1周 / 近1月 / 近3月 / 近6月 / 全部 / 指定 -->
      <div class="ov-range">
        <button
          v-for="r in ranges"
          :key="r.key"
          type="button"
          class="ov-range-btn"
          :class="{ active: rangeKey === r.key }"
          @click="selectRange(r.key)"
        >{{ r.label }}</button>
        <el-date-picker
          v-if="rangeKey === 'custom'"
          v-model="customRange"
          type="daterange"
          size="small"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          :clearable="false"
          class="ov-range-picker"
          @change="loadOverview"
        />
        <span class="ov-spacer"></span>
        <router-link to="/database" class="ov-link">导入 / 管理交易记录 →</router-link>
        <a class="ov-link" :class="{ disabled: loading }" @click="loadOverview">刷新</a>
      </div>

      <div v-if="errorMsg" class="ov-error">{{ errorMsg }}</div>
      <div v-for="(w, i) in warnings" :key="i" class="ov-warning">⚠ {{ w }}</div>
      <div v-if="skipped.length" class="ov-warning">
        ⚠ {{ skipped.length }} 个文件无法解析，已跳过：{{ skipped.map((s) => s.name).join('、') }}
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && !hasData" class="ov-empty">
        <div class="empty-icon">📈</div>
        <div class="empty-title">{{ fileCount ? '所选时间范围内没有成交记录' : '还没有交易记录' }}</div>
        <div class="empty-desc">
          {{ fileCount ? '请换一个时间范围' : '请先到「数据库管理 → 历史交易记录管理」导入期货公司的成交明细' }}
        </div>
        <router-link v-if="!fileCount" to="/database" class="ov-empty-btn">去导入</router-link>
      </div>

      <template v-if="hasData">
        <!-- 总盈亏头部 -->
        <section class="ov-hero">
          <div class="ov-hero-label">全部盈亏{{ hasFee ? '（已扣手续费）' : '' }}</div>
          <div class="ov-hero-range">{{ overview.start }} 至 {{ overview.end }}</div>
          <div class="ov-hero-value" :class="pnlClass(stats.totalPnl)">{{ plain(stats.totalPnl) }}</div>
          <div class="ov-hero-sub">
            共 {{ fileCount }} 个文件 · {{ stats.tradingDays }} 个交易日 · 手续费合计 {{ plain(stats.totalFee) }}
          </div>
        </section>

        <!-- 交易统计 -->
        <section class="ov-card">
          <h3 class="ov-card-title">交易统计 <small>（{{ rangeLabel }}）</small></h3>
          <div class="ov-stats">
            <div class="ov-stat">
              <div class="ov-stat-label">胜率</div>
              <div class="ov-stat-value" :class="stats.winRate >= 50 ? 'up' : 'down'">{{ stats.winRate.toFixed(2) }}%</div>
            </div>
            <div class="ov-stat">
              <div class="ov-stat-label">盈亏比</div>
              <div class="ov-stat-value neutral">{{ stats.profitLossRatio.toFixed(2) }}%</div>
            </div>
            <div class="ov-stat">
              <div class="ov-stat-label">最大回撤</div>
              <div class="ov-stat-value neutral">{{ plain(stats.maxDrawdown) }}</div>
            </div>
            <div class="ov-stat">
              <div class="ov-stat-label">交易笔数</div>
              <div class="ov-stat-value neutral">{{ stats.closeCount }}</div>
            </div>
            <div class="ov-stat">
              <div class="ov-stat-label">盈利天数 / 亏损天数</div>
              <div class="ov-stat-value neutral">{{ stats.winDays }} / {{ stats.lossDays }}</div>
            </div>
            <div class="ov-stat">
              <div class="ov-stat-label">单笔最大盈利 / 亏损</div>
              <div class="ov-stat-value neutral small">
                <span class="up">{{ plain(stats.maxProfit) }}</span> / <span class="down">{{ plain(stats.maxLoss) }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 收益走势 -->
        <section class="ov-card">
          <div class="ov-card-head">
            <h3 class="ov-card-title">收益走势 <small>（{{ rangeLabel }}）</small></h3>
            <div class="ov-seg">
              <button type="button" :class="{ active: trendMode === 'cum' }" @click="trendMode = 'cum'">累计盈亏</button>
              <button type="button" :class="{ active: trendMode === 'day' }" @click="trendMode = 'day'">当日盈亏</button>
            </div>
          </div>
          <div class="ov-trend-tip" v-if="trendTip">
            {{ trendMode === 'cum' ? '累计盈亏' : '当日盈亏' }}：
            <b :class="pnlClass(trendTip.value)">{{ plain(trendTip.value) }}</b>
            <span class="ov-trend-date">{{ trendTip.day.replaceAll('-', '/') }}</span>
          </div>
          <div ref="trendRef" class="ov-chart ov-chart-trend"></div>
          <div class="ov-hint">点击图上的某一天，可进入当天的盈亏曲线和交易回放</div>
        </section>

        <!-- 品种结构 -->
        <section class="ov-card">
          <h3 class="ov-card-title">品种结构 <small>（{{ rangeLabel }}）</small></h3>
          <div class="ov-struct">
            <div ref="pieRef" class="ov-chart ov-chart-pie"></div>
            <table class="ov-legend">
              <thead>
                <tr><th></th><th>品种</th><th>成交额占比</th><th>盈亏</th></tr>
              </thead>
              <tbody>
                <tr v-for="(p, i) in products" :key="p.product">
                  <td><i class="ov-dot" :style="{ background: pieColor(i) }"></i></td>
                  <td>{{ p.product }}</td>
                  <td>{{ p.turnoverRatio.toFixed(2) }}%</td>
                  <td :class="pnlClass(p.pnl)">{{ plain(p.pnl) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- 品种盈亏与胜率 -->
        <section class="ov-card">
          <h3 class="ov-card-title">品种盈亏与胜率 <small>（{{ rangeLabel }}）</small></h3>
          <div class="ov-trend-tip" v-if="prodTip">
            {{ prodTip.product }}
            <span>盈亏 <b :class="pnlClass(prodTip.pnl)">{{ plain(prodTip.pnl) }}</b></span>
            <span>胜率 <b class="amber">{{ prodTip.winRate.toFixed(2) }}%</b></span>
            <span class="ov-trend-date">{{ prodTip.closeCount }} 笔</span>
          </div>
          <div ref="prodRef" class="ov-chart ov-chart-prod"></div>
        </section>

        <!-- 每月盈亏日历 -->
        <section class="ov-card">
          <div class="ov-card-head">
            <h3 class="ov-card-title">每月盈亏</h3>
            <div class="ov-month-nav">
              <button type="button" class="ov-nav-btn" :disabled="!canPrevMonth" @click="shiftMonth(-1)">‹</button>
              <select v-model="monthKey" class="ov-month-select">
                <option v-for="m in monthList" :key="m" :value="m">{{ m.slice(0, 4) }}年{{ Number(m.slice(5)) }}月</option>
              </select>
              <button type="button" class="ov-nav-btn" :disabled="!canNextMonth" @click="shiftMonth(1)">›</button>
            </div>
          </div>

          <div class="ov-cal">
            <div class="ov-cal-week" v-for="w in weekNames" :key="w">{{ w }}</div>
            <div
              v-for="(cell, i) in calendarCells"
              :key="i"
              class="ov-cal-cell"
              :class="[cell.cls, { clickable: cell.traded }]"
              @click="cell.traded && openDay(cell.date)"
            >
              <template v-if="cell.day">
                <div class="ov-cal-day">{{ cell.day }}</div>
                <div class="ov-cal-pnl" v-if="cell.traded">{{ cell.pnlText }}</div>
              </template>
            </div>
          </div>
          <div class="ov-month-total">
            {{ Number(monthKey.slice(5)) }}月累计收益：
            <b :class="pnlClass(monthPnl)">{{ plain(monthPnl) }}</b>
            <span class="ov-trend-date">{{ monthTradingDays }} 个交易日</span>
          </div>
        </section>

        <div class="ov-foot">以上数据仅供参考，盈亏 = 平仓盈亏 − 手续费，请以期货公司结算单为准。没有入金 / 权益数据，不提供收益率。</div>
      </template>

      <div v-if="loading" class="ov-loading">
        <div class="loading-spinner"></div>
        <div class="loading-text">正在合并并分析交易记录...</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { getReviewOverview } from '@/api'
import { chartColors, onThemeChange } from '@/utils/chartTheme'

const router = useRouter()

// ---------- 状态 ----------
const loading = ref(false)
const errorMsg = ref('')
const warnings = ref([])
const skipped = ref([])
const fileCount = ref(0)
const hasFee = ref(false)
/** @type {import('vue').Ref<Record<string, any>>} */
const overview = ref({ days: [], products: [], stats: {}, start: '', end: '' })
const allStart = ref('')
const allEnd = ref('')

const stats = computed(() => overview.value.stats || {})
const daysList = computed(() => overview.value.days || [])
const products = computed(() => overview.value.products || [])
const hasData = computed(() => daysList.value.length > 0)

// ---------- 时间范围 ----------
const ranges = [
  { key: 'week', label: '近1周', days: 7 },
  { key: 'month', label: '近1月', days: 30 },
  { key: 'm3', label: '近3月', days: 91 },
  { key: 'm6', label: '近6月', days: 182 },
  { key: 'all', label: '全部' },
  { key: 'custom', label: '指定' }
]
const rangeKey = ref('all')
const customRange = ref(null)
const rangeLabel = computed(() => ranges.find((r) => r.key === rangeKey.value)?.label || '全部')

const fmtDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// 「近N」以数据里最后一个交易日为终点（而不是今天）：导入的是历史文件，以今天为终点会得到空结果
function rangeParams() {
  if (rangeKey.value === 'all') return {}
  if (rangeKey.value === 'custom') {
    return customRange.value?.length === 2 ? { start: customRange.value[0], end: customRange.value[1] } : {}
  }
  const r = ranges.find((x) => x.key === rangeKey.value)
  if (!allEnd.value) return {}
  const end = new Date(`${allEnd.value}T00:00:00`)
  const start = new Date(end)
  start.setDate(start.getDate() - (r.days - 1))
  return { start: fmtDate(start), end: allEnd.value }
}

function selectRange(key) {
  rangeKey.value = key
  if (key === 'custom' && !customRange.value && allStart.value) customRange.value = [allStart.value, allEnd.value]
  loadOverview()
}

// ---------- 格式化（红涨绿跌：盈利红、亏损绿，与项目其它页面一致）----------
const plain = (v) => Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const pnlClass = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : 'neutral')
const compact = (v) => (Math.abs(v) >= 10000 ? `${(v / 10000).toFixed(2)}万` : String(Math.round(v)))

function errorText(error, fallback) {
  const data = error?.response?.data
  if (data?.message) return data.message
  if (error?.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (error?.request && !error?.response) return '无法连接后端服务，请确认应用已正常启动'
  const status = error?.response?.status
  if (status === 404 || status === 405) return `${fallback}：后端不支持这个操作（HTTP ${status}），可能是后端版本过旧，请重启后端（打包版需重新执行 npm run backend:build）`
  if (status) return `${fallback}（HTTP ${status}）`
  return error?.message ? `${fallback}：${error.message}` : fallback
}

// ---------- 数据 ----------
let loadSeq = 0
async function loadOverview() {
  const seq = ++loadSeq
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await getReviewOverview({ fee: 1, ...rangeParams() })
    if (seq !== loadSeq) return
    overview.value = res
    fileCount.value = res.fileCount || 0
    hasFee.value = !!res.hasFee
    warnings.value = res.warnings || []
    skipped.value = res.skipped || []
    allStart.value = res.allStart || ''
    allEnd.value = res.allEnd || ''
    const months = monthList.value
    if (!months.includes(monthKey.value)) monthKey.value = months[months.length - 1] || ''
    await nextTick()
    renderAll()
  } catch (error) {
    if (seq !== loadSeq) return
    errorMsg.value = errorText(error, '加载账户分析失败')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

// 点击某一天 -> 进入单日复盘（父子页面：/review -> /review/day/:day）
const openDay = (day) => router.push({ name: 'ReviewDay', params: { day } })

// ---------- 图表 ----------
const trendRef = ref(null)
const pieRef = ref(null)
const prodRef = ref(null)
let trendChart = null
let pieChart = null
let prodChart = null

const trendMode = ref('cum')          // cum = 累计盈亏，day = 当日盈亏
const trendTip = ref(null)            // { day, value }：悬停时显示在图表上方
const prodTip = ref(null)             // 当前悬停（默认第一个）的品种

const PIE_COLORS = ['#6685ff', '#3d6bff', '#4fd1c5', '#3b9dff', '#ffa94d', '#8e8e93', '#b197fc', '#f783ac']
const pieColor = (i) => PIE_COLORS[i % PIE_COLORS.length]

const upColor = () => getComputedStyle(document.documentElement).getPropertyValue('--up').trim() || '#ef4444'
const downColor = () => getComputedStyle(document.documentElement).getPropertyValue('--down').trim() || '#22c55e'

function renderTrend() {
  if (!trendChart) return
  const c = chartColors()
  const days = daysList.value
  const labels = days.map((d) => d.day)
  const values = days.map((d) => (trendMode.value === 'cum' ? d.cumPnl : d.pnl))
  const up = upColor()
  const down = downColor()
  trendTip.value = days.length ? { day: labels[labels.length - 1], value: values[values.length - 1] } : null

  const isCum = trendMode.value === 'cum'
  trendChart.setOption({
    animation: false,
    grid: { left: 64, right: 24, top: 24, bottom: days.length > 40 ? 64 : 36 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: isCum ? 'line' : 'shadow', lineStyle: { color: c.crossColor } },
      backgroundColor: c.tooltipBg,
      borderWidth: 0,
      textStyle: { color: c.tooltipText },
      formatter: (ps) => {
        const p = ps[0]
        const d = days[p.dataIndex]
        trendTip.value = { day: d.day, value: values[p.dataIndex] }
        return `${d.day}<br/>当日盈亏：${plain(d.pnl)}<br/>累计盈亏：${plain(d.cumPnl)}<br/>平仓 ${d.closeCount} 笔`
      }
    },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: !isCum,
      axisLine: { lineStyle: { color: c.axisLine } },
      axisLabel: { color: c.axisLabel, formatter: (v) => v.slice(5) },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      scale: false,
      axisLabel: { color: c.axisLabel, formatter: (v) => compact(v) },
      splitLine: { lineStyle: { color: c.splitLine } }
    },
    dataZoom: days.length > 40
      ? [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8, borderColor: c.sliderBorder }]
      : [],
    series: [
      isCum
        ? {
            type: 'line',
            data: values,
            showSymbol: days.length <= 60,
            symbolSize: 6,
            lineStyle: { width: 2, color: c.accent },
            itemStyle: { color: c.accent },
            areaStyle: { color: c.area },
            markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: c.text, type: 'dashed' }, data: [{ yAxis: 0 }] }
          }
        : {
            type: 'bar',
            data: values.map((v) => ({ value: v, itemStyle: { color: v >= 0 ? up : down } })),
            barMaxWidth: 22,
            markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: c.text, type: 'dashed' }, data: [{ yAxis: 0 }] }
          }
    ]
  }, true)
}

function renderPie() {
  if (!pieChart) return
  const c = chartColors()
  pieChart.setOption({
    animation: false,
    tooltip: {
      trigger: 'item',
      backgroundColor: c.tooltipBg,
      borderWidth: 0,
      textStyle: { color: c.tooltipText },
      formatter: (p) => `${p.name}<br/>成交额占比 ${p.value.toFixed(2)}%`
    },
    series: [{
      type: 'pie',
      radius: ['58%', '88%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: true,
      label: { show: false },
      itemStyle: { borderColor: c.bg, borderWidth: 2 },
      data: products.value.map((p, i) => ({ name: p.product, value: p.turnoverRatio, itemStyle: { color: pieColor(i) } }))
    }]
  }, true)
}

function renderProd() {
  if (!prodChart) return
  const c = chartColors()
  const list = [...products.value].sort((a, b) => b.pnl - a.pnl)
  const up = upColor()
  const down = downColor()
  prodTip.value = list[0] || null
  prodChart.setOption({
    animation: false,
    grid: { left: 64, right: 52, top: 24, bottom: 36 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: c.tooltipBg,
      borderWidth: 0,
      textStyle: { color: c.tooltipText },
      formatter: (ps) => {
        const p = list[ps[0].dataIndex]
        prodTip.value = p
        return `${p.product}<br/>盈亏：${plain(p.pnl)}<br/>胜率：${p.winRate.toFixed(2)}%（${p.winCount} 胜 / ${p.lossCount} 负）`
      }
    },
    xAxis: { type: 'category', data: list.map((p) => p.product), axisLine: { lineStyle: { color: c.axisLine } }, axisLabel: { color: c.axisLabel }, axisTick: { show: false } },
    yAxis: [
      { type: 'value', axisLabel: { color: c.axisLabel, formatter: (v) => compact(v) }, splitLine: { lineStyle: { color: c.splitLine } } },
      { type: 'value', min: 0, max: 100, axisLabel: { color: c.axisLabel, formatter: '{value}%' }, splitLine: { show: false } }
    ],
    series: [
      {
        name: '盈亏',
        type: 'bar',
        barMaxWidth: 28,
        data: list.map((p) => ({ value: p.pnl, itemStyle: { color: p.pnl >= 0 ? up : down } })),
        markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: c.text, type: 'dashed' }, data: [{ yAxis: 0 }] }
      },
      {
        name: '胜率',
        type: 'scatter',
        yAxisIndex: 1,
        symbolSize: 12,
        itemStyle: { color: c.amber },
        data: list.map((p) => p.winRate)
      }
    ]
  }, true)
}

function renderAll() {
  renderTrend()
  renderPie()
  renderProd()
}

function initCharts() {
  if (trendRef.value && !trendChart) {
    trendChart = echarts.init(trendRef.value)
    // 点击图上任意位置 -> 进入「离鼠标最近的那个交易日」的复盘。
    // 不依赖是否精确命中折线点 / 柱子：折线图点在线上、面积上都会命中别的图形，只监听数据点的 click 会让大部分点击没反应
    trendChart.getZr().on('click', (e) => {
      const pt = [e.offsetX, e.offsetY]
      if (!trendChart.containPixel('grid', pt)) return
      const idx = Math.round(trendChart.convertFromPixel({ xAxisIndex: 0 }, pt[0]))
      const d = daysList.value[Math.min(Math.max(idx, 0), daysList.value.length - 1)]
      if (d) openDay(d.day)
    })
  }
  if (pieRef.value && !pieChart) pieChart = echarts.init(pieRef.value)
  if (prodRef.value && !prodChart) prodChart = echarts.init(prodRef.value)
}

function resizeAll() {
  trendChart?.resize()
  pieChart?.resize()
  prodChart?.resize()
}

// 图表容器在 v-if="hasData" 里：数据来了才出现，所以数据加载完要补一次初始化
watch(hasData, async (v) => {
  if (!v) return
  await nextTick()
  initCharts()
  renderAll()
})
watch(trendMode, renderTrend)
onThemeChange(() => renderAll())

// ---------- 月历 ----------
const weekNames = ['日', '一', '二', '三', '四', '五', '六']
const monthKey = ref('')   // 'YYYY-MM'

const monthList = computed(() => {
  const set = new Set(daysList.value.map((d) => d.day.slice(0, 7)))
  return [...set].sort()
})
const monthIdx = computed(() => monthList.value.indexOf(monthKey.value))
const canPrevMonth = computed(() => monthIdx.value > 0)
const canNextMonth = computed(() => monthIdx.value >= 0 && monthIdx.value < monthList.value.length - 1)
const shiftMonth = (n) => {
  const m = monthList.value[monthIdx.value + n]
  if (m) monthKey.value = m
}

const dayMap = computed(() => new Map(daysList.value.map((d) => [d.day, d])))

const monthDays = computed(() => daysList.value.filter((d) => d.day.startsWith(monthKey.value)))
const monthPnl = computed(() => Math.round(monthDays.value.reduce((s, d) => s + d.pnl, 0) * 100) / 100)
const monthTradingDays = computed(() => monthDays.value.length)

// 当月网格：前面补上月的空格，后面补到整周。有成交的格子红盈绿亏，其余只显示日期
const calendarCells = computed(() => {
  if (!monthKey.value) return []
  const [y, m] = monthKey.value.split('-').map(Number)
  const first = new Date(y, m - 1, 1)
  const total = new Date(y, m, 0).getDate()
  const cells = []
  for (let i = 0; i < first.getDay(); i++) cells.push({ day: 0, cls: 'blank' })
  for (let d = 1; d <= total; d++) {
    const date = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const row = dayMap.value.get(date)
    const dow = new Date(y, m - 1, d).getDay()
    const weekend = dow === 0 || dow === 6
    if (row) {
      cells.push({
        day: d, date, traded: true,
        cls: row.pnl > 0 ? 'win' : row.pnl < 0 ? 'loss' : 'flat',
        pnlText: String(Math.round(row.pnl))
      })
    } else {
      cells.push({ day: d, date, traded: false, cls: weekend ? 'weekend' : 'idle' })
    }
  }
  while (cells.length % 7) cells.push({ day: 0, cls: 'blank' })
  return cells
})

// ---------- 生命周期 ----------
let ro = null
onMounted(() => {
  loadOverview()
  window.addEventListener('resize', resizeAll)
  // 容器宽度变化（侧边栏 / 窗口缩放）时重新量尺寸
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(resizeAll)
    ro.observe(document.querySelector('.ov-body'))
  }
})
onUnmounted(() => {
  window.removeEventListener('resize', resizeAll)
  ro?.disconnect()
  trendChart?.dispose()
  pieChart?.dispose()
  prodChart?.dispose()
  trendChart = pieChart = prodChart = null
})
</script>

<style scoped>
@import '@/styles/ReviewOverview.css';
</style>
