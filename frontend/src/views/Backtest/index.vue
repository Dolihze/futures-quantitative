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
        <span class="nav-title">量化回测</span>
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
            v-model="params.product"
            class="toolbar-select"
            filterable
            placeholder="选择品种"
            :disabled="loading"
            @change="load"
          >
            <el-option-group v-for="g in productGroups" :key="g.exchange" :label="g.exchange">
              <el-option v-for="p in g.items" :key="p.code" :label="`${p.name} ${p.code}`" :value="p.code" />
            </el-option-group>
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

      <!-- 数据范围说明：新浪每个周期只给最近约 1023 根 K 线，数据不够所选天数时必须明说 -->
      <el-alert
        v-if="coverageNotice"
        class="overview-alert"
        type="info"
        :title="coverageNotice"
        show-icon
        :closable="false"
      />

      <!-- 汇总 -->
      <div v-if="summary" class="summary-bar">
        <div class="summary-item">
          <div class="summary-label">策略数</div>
          <div class="summary-value">{{ summary.count }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">合计交易笔数</div>
          <div class="summary-value">{{ summary.trades }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">合计模拟盈亏</div>
          <div class="summary-value" :class="pnlClass(summary.profit)">{{ fmtMoney(summary.profit) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">盈利策略</div>
          <div class="summary-value">{{ summary.winning }} / {{ summary.count }}</div>
        </div>
      </div>

      <!-- 策略卡片 -->
      <div v-if="loading && !strategies.length" class="overview-loading">
        <div class="loading-spinner"></div>
        <div class="loading-text">正在回测所有策略...</div>
      </div>

      <div v-else class="strategy-grid">
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
import { ref, reactive, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { getBacktestOverview, getBacktestProducts } from '@/api'
import { chartColors, onThemeChange } from '@/utils/chartTheme'
import { fmtMoney, fmtRatio, pnlClass } from './format'
import { buildDayOptions, clampDays } from './range'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const errorMsg = ref('')
const strategies = ref([])
// 回测对象是各常见品种的主连，下拉框选择，默认燃料油主连（FU）
const DEFAULT_PRODUCT = 'FU'
const products = ref([])
const params = reactive({
  product: String(route.query.product || DEFAULT_PRODUCT),
  days: Number(route.query.days) || 30,
  lots: 5
})
const symbolName = computed(() => products.value.find((p) => p.code === params.product)?.name || '燃料油主连')
// 所有策略里最多能拿到的数据天数（0 = 还没请求过）。时间范围选项据此收敛，超出的档位不提供
const availableDays = ref(0)
const requestedDays = ref(0) // 最近一次请求时用户选的天数（收敛到「全部」之前）
const dayOptions = computed(() => buildDayOptions(availableDays.value))
// 每个策略用自己的周期，可得数据不同；只要有策略实际用的天数少于所选天数，就提示一下
const coverageNotice = computed(() => {
  const short = strategies.value.filter((s) => s.coverage && s.coverage.truncated)
  if (!short.length) return ''
  const detail = short.map((s) => `「${s.name}」(${s.period}分钟线) 实际只有 ${s.coverage.availableDays} 天`).join('；')
  return `所选 ${requestedDays.value} 天超出了可获取的数据范围，已使用全部可得数据：${detail}。新浪每个周期只提供最近约 1000 根 K 线。`
})
// 按交易所分组，保持后端给出的顺序
const productGroups = computed(() => {
  const groups = []
  for (const p of products.value) {
    let g = groups.find((x) => x.exchange === p.exchange)
    if (!g) groups.push((g = { exchange: p.exchange, items: [] }))
    g.items.push(p)
  }
  return groups
})

async function loadProducts() {
  try {
    const res = await getBacktestProducts()
    if (res.success) {
      products.value = res.data
      // URL 里带了已不存在的品种时回退到默认
      if (!products.value.some((p) => p.code === params.product)) params.product = res.default || DEFAULT_PRODUCT
    }
  } catch (e) {
    // 品种列表取不到时下拉框为空，当前（默认）品种仍可回测，错误由 load() 展示
    console.warn('获取品种列表失败', e)
  }
}

// ---------- 数据 ----------
// 防止快速切换时间范围时，旧请求的结果覆盖新请求
let seq = 0

async function load() {
  const my = ++seq
  loading.value = true
  errorMsg.value = ''
  // 品种和时间范围同步到 URL：刷新页面、从详情页返回时保持选择
  router.replace({ query: { product: params.product, days: params.days } })
  try {
    const res = await getBacktestOverview({ product: params.product, days: params.days, lots: params.lots })
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
      router.replace({ query: { product: params.product, days: params.days } })
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

const summary = computed(() => {
  const ok = strategies.value.filter((s) => s.stats)
  if (!ok.length) return null
  return {
    count: ok.length,
    trades: ok.reduce((n, s) => n + s.stats.tradeCount, 0),
    profit: ok.reduce((n, s) => n + s.stats.totalProfit, 0),
    winning: ok.filter((s) => s.stats.totalProfit > 0).length
  }
})

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
  router.push({ path: `/backtest/${s.id}`, query: { product: params.product, days: params.days, lots: params.lots } })
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

onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadProducts()
  load()
})

onUnmounted(() => {
  seq++
  window.removeEventListener('resize', handleResize)
  Object.values(sparkCharts).forEach((ch) => ch.dispose())
})
</script>

<style scoped>
@import '@/styles/Backtest.css';
</style>
