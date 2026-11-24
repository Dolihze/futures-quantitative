<template>
  <div class="backtest-container">
    <!-- 顶部导航栏 -->
    <nav class="navbar">
      <div class="nav-left">
        <router-link to="/" class="back-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          返回首页
        </router-link>
      </div>
      <div class="nav-right">
        <UserMenu />
      </div>
    </nav>

    <div class="overview-page">
      <!-- 工具条：合约、时间范围、手数 -->
      <div class="overview-toolbar">
        <div class="toolbar-title">
          <h2>策略总览</h2>
          <span class="toolbar-sub">
            {{ symbolName }} · 近 {{ params.days }} 天 · 每笔 {{ params.lots }} 手 · 不含手续费与滑点
          </span>
        </div>
        <div class="toolbar-controls">
          <el-select
            v-model="params.symbol"
            class="toolbar-select"
            filterable
            placeholder="选择合约（来自数据库管理）"
            :disabled="loading || !contracts.length"
            @change="load"
          >
            <el-option v-for="c in contracts" :key="c.symbol" :label="c.label" :value="c.symbol" />
          </el-select>
          <el-radio-group v-model="params.days" :disabled="loading" @change="load">
            <el-radio-button v-for="o in dayOptions" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
          </el-radio-group>
          <el-button :loading="loading" @click="load">刷新</el-button>
        </div>
      </div>

      <el-alert
        v-if="errorMsg"
        class="overview-alert"
        type="error"
        :title="errorMsg"
        show-icon
        :closable="false"
      />

      <!-- 本地行情库里还没有任何合约：引导去数据库管理导入 tick -->
      <el-alert
        v-if="contractsLoaded && !contracts.length"
        class="overview-alert"
        type="warning"
        title="本地历史行情库为空：回测使用「数据库管理 → 历史行情数据管理」里导入的 tick 数据，请先导入合约。"
        show-icon
        :closable="false"
      >
        <router-link to="/database?tab=market">去数据库管理导入 →</router-link>
      </el-alert>

      <!-- 数据范围说明：本地库里的 tick 只覆盖有限的交易日，数据不够所选天数时必须明说。
           宽度按内容自适应；可以手动关闭，关闭后到下一次加载（刷新 / 换合约 / 换时间范围）才会重新出现 -->
      <el-alert
        v-if="coverageNotice && !noticeClosed"
        class="overview-alert"
        type="info"
        :title="coverageNotice"
        show-icon
        @close="noticeClosed = true"
      />

      <!-- 策略卡片 -->
      <div v-if="loading && !strategies.length" class="overview-loading">
        <div class="loading-spinner"></div>
        <div class="loading-text">正在回测所有策略...</div>
      </div>

      <div v-else ref="gridRef" class="strategy-grid">
        <div
          v-for="s in strategies"
          :key="s.id"
          class="strategy-card"
          :class="{ 'is-disabled': !s.stats, 'is-loading': loading }"
          @click="openDetail(s)"
        >
          <div class="card-head">
            <div class="card-name">{{ s.name }}</div>
            <span class="card-tag">{{ s.category }}</span>
            <span class="card-tag muted">{{ s.period }}分钟线</span>
          </div>
          <div class="card-desc">{{ s.description }}</div>

          <template v-if="s.stats">
            <div class="card-metrics">
              <div class="metric">
                <div class="metric-label">胜率</div>
                <div class="metric-value" :class="winRateClass(s.stats)">
                  {{ s.stats.tradeCount ? s.stats.winRate.toFixed(1) + '%' : '--' }}
                </div>
              </div>
              <div class="metric">
                <div class="metric-label">盈亏比</div>
                <div class="metric-value" :class="ratioClass(s.stats)">{{ fmtRatio(s.stats) }}</div>
              </div>
              <div class="metric">
                <div class="metric-label">模拟盈亏</div>
                <div class="metric-value" :class="pnlClass(s.stats.totalProfit)">
                  {{ fmtMoney(s.stats.totalProfit) }}
                </div>
              </div>
              <div class="metric">
                <div class="metric-label">交易笔数</div>
                <div class="metric-value neutral">{{ s.stats.tradeCount }}</div>
              </div>
            </div>
            <div v-if="!s.stats.tradeCount" class="card-empty-hint">
              所选时间范围内没有触发任何交易（该策略的开仓条件在此品种上未出现，例如品种没有对应的开盘时段）
            </div>
            <div v-else :ref="(el) => setSparkRef(s.id, el)" class="card-spark"></div>
            <div class="card-foot">
              <span>最大回撤 {{ s.stats.maxDrawdown.toFixed(0) }} 元（{{ s.stats.maxDrawdownPct.toFixed(1) }}%）</span>
              <span class="card-more">查看详情 ›</span>
            </div>
          </template>
          <div v-else class="card-error">回测失败：{{ s.error || '未知错误' }}</div>
        </div>

        <div v-if="!strategies.length && !loading && !errorMsg" class="overview-empty">暂无策略</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { getBacktestOverview, getBacktestContracts } from '@/api'
import { chartColors, onThemeChange } from '@/utils/chartTheme'
import { fmtMoney, fmtRatio, pnlClass } from './format'
import { buildDayOptions, clampDays } from './range'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const errorMsg = ref('')
const strategies = ref([])
// 回测对象是「数据库管理」里已导入的具体合约（如 fu2611），下拉框选择，默认库里的第一个合约
const contracts = ref([])
const contractsLoaded = ref(false)
const params = reactive({
  symbol: String(route.query.symbol || ''),
  days: Number(route.query.days) || 30,
  lots: 5
})
const symbolName = computed(() => contracts.value.find((c) => c.symbol === params.symbol)?.label || params.symbol || '未选择合约')
// 所有策略里最多能拿到的数据天数（0 = 还没请求过）。时间范围选项据此收敛，超出的档位不提供
const availableDays = ref(0)
const requestedDays = ref(0) // 最近一次请求时用户选的天数（收敛到「全部」之前）
const dayOptions = computed(() => buildDayOptions(availableDays.value))
// 每个策略用自己的周期，可得数据不同；只要有策略实际用的天数少于所选天数，就提示一下
const noticeClosed = ref(false) // 数据范围提示被手动关闭；每次重新加载数据时复位
const coverageNotice = computed(() => {
  const short = strategies.value.filter((s) => s.coverage && s.coverage.truncated)
  if (!short.length) return ''
  const detail = short.map((s) => `「${s.name}」(${s.period}分钟线) 实际只有 ${s.coverage.availableDays} 天`).join('；')
  return `所选 ${requestedDays.value} 天超出了本地行情库的数据范围，已使用全部可得数据：${detail}。需要更长区间请到「数据库管理」导入更多交易日的 tick 数据。`
})

// 读取本地行情库里已导入的合约；URL 里带了已不存在的合约时回退到库里的第一个
async function loadContracts() {
  try {
    const res = await getBacktestContracts()
    if (res.success) {
      contracts.value = res.data
      if (!contracts.value.some((c) => c.symbol === params.symbol)) params.symbol = res.default || ''
    }
  } catch (e) {
    console.warn('获取本地合约列表失败', e)
  } finally {
    contractsLoaded.value = true
  }
}

// ---------- 数据 ----------
// 防止快速切换时间范围时，旧请求的结果覆盖新请求
let seq = 0

async function load() {
  const my = ++seq
  errorMsg.value = ''
  noticeClosed.value = false
  // 本地库没有任何合约（或没选合约）时不请求回测，由页面上的导入引导提示用户
  if (!params.symbol) {
    strategies.value = []
    loading.value = false
    return
  }
  loading.value = true
  // 合约和时间范围同步到 URL：刷新页面、从详情页返回时保持选择
  router.replace({ query: { symbol: params.symbol, days: params.days } })
  try {
    const res = await getBacktestOverview({ symbol: params.symbol, days: params.days, lots: params.lots })
    if (my !== seq) return
    if (!res.success) {
      errorMsg.value = res.message || '回测失败'
      strategies.value = []
    } else {
      strategies.value = res.data
      availableDays.value = res.availableDays || 0
      // 所选天数超出可得数据（如 URL 里是 90 而数据只有 21 天）：选中项落到「全部」，结果本来就相同，不必重新请求。
      // 同时记下用户原本想看多少天，用于提示「所选 90 天，实际只有 21 天」
      requestedDays.value = params.days
      params.days = clampDays(params.days, availableDays.value)
      router.replace({ query: { symbol: params.symbol, days: params.days } })
    }
  } catch (e) {
    if (my !== seq) return
    errorMsg.value = e?.response?.data?.message || e?.message || '加载失败，请检查后端是否启动'
    strategies.value = []
  } finally {
    if (my === seq) loading.value = false
  }
  if (my === seq) {
    await nextTick()
    renderSparks()
  }
}

// 红涨绿跌：胜率 >= 50% 红，否则绿；没有交易时不着色
function winRateClass(st) {
  if (!st.tradeCount) return 'neutral'
  return st.winRate >= 50 ? 'positive' : 'negative'
}
// 盈亏比 >= 1 红（平均盈利不小于平均亏损）；无亏损单时无法计算，用中性色
function ratioClass(st) {
  if (st.plRatio === null || st.plRatio === undefined) return 'neutral'
  return st.plRatio >= 1 ? 'positive' : 'negative'
}

function openDetail(s) {
  if (!s.stats) return
  router.push({ path: `/backtest/${s.id}`, query: { symbol: params.symbol, days: params.days, lots: params.lots } })
}

// ---------- 迷你净值曲线 ----------
const sparkEls = {}
const sparkCharts = {}

function setSparkRef(id, el) {
  if (el) sparkEls[id] = el
  else delete sparkEls[id]
}

function renderSparks() {
  const c = chartColors()
  // 清掉已经不存在的图表
  for (const id of Object.keys(sparkCharts)) {
    if (!sparkEls[id] || sparkCharts[id].getDom() !== sparkEls[id]) {
      sparkCharts[id].dispose()
      delete sparkCharts[id]
    }
  }
  for (const s of strategies.value) {
    const el = sparkEls[s.id]
    if (!el || !s.stats) continue
    const chart = sparkCharts[s.id] || (sparkCharts[s.id] = echarts.init(el))
    const first = s.equity[0]?.equity ?? 0
    const last = s.equity[s.equity.length - 1]?.equity ?? 0
    // 红涨绿跌：整体盈利红、亏损绿、持平灰
    const color = last > first ? '#ef4444' : last < first ? '#22c55e' : c.muted
    chart.setOption(
      {
        animation: false,
        grid: { left: 4, right: 4, top: 6, bottom: 4 },
        tooltip: {
          trigger: 'axis',
          backgroundColor: c.tooltipBg,
          textStyle: { color: c.tooltipText, fontSize: 12 },
          borderColor: c.accent,
          formatter: (p) => `${p[0].axisValue}<br/>净值 ${Number(p[0].value).toFixed(2)}`
        },
        xAxis: { type: 'category', show: false, data: s.equity.map((p) => p.time), boundaryGap: false },
        yAxis: { type: 'value', show: false, scale: true },
        series: [
          {
            type: 'line',
            data: s.equity.map((p) => p.equity),
            step: 'end',
            showSymbol: false,
            lineStyle: { width: 1.5, color },
            areaStyle: { color, opacity: 0.12 },
            markLine: {
              silent: true,
              symbol: 'none',
              label: { show: false },
              lineStyle: { color: c.muted, type: 'dashed', width: 1 },
              data: [{ yAxis: first }]
            }
          }
        ]
      },
      true
    )
    chart.resize()
  }
}

function handleResize() {
  Object.values(sparkCharts).forEach((ch) => ch.resize())
}

onThemeChange(() => renderSparks())

// 弹性布局下卡片列数和宽度随窗口变化：监听卡片网格本身的尺寸变化来重画迷你曲线，
// 比只监听 window.resize 更可靠（滚动条出现 / 消失、列数变化都会改变卡片宽度）。
// 网格是 v-if / v-else 渲染的，出现或重建时重新挂上观察者
const gridRef = ref(null)
let resizeObserver = null
watch(gridRef, (el) => {
  resizeObserver?.disconnect()
  if (el && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(el)
  }
})

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  await loadContracts()   // 先确定合约，再回测
  load()
})

onUnmounted(() => {
  seq++
  resizeObserver?.disconnect()
  window.removeEventListener('resize', handleResize)
  Object.values(sparkCharts).forEach((ch) => ch.dispose())
})
</script>

<style scoped>
@import '@/styles/Backtest.css';
</style>
