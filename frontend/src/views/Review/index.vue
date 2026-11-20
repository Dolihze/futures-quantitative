<template>
  <div class="review-container">
    <!-- 顶部导航栏 -->
    <nav class="navbar">
      <div class="nav-left">
        <router-link to="/review" class="back-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          返回账户总览
        </router-link>
        <div class="day-switch">
          <button type="button" class="day-btn" :disabled="!prevDay" @click="gotoDay(prevDay)">‹ 上一日</button>
          <span class="day-title">{{ day }}</span>
          <button type="button" class="day-btn" :disabled="!nextDay" @click="gotoDay(nextDay)">下一日 ›</button>
        </div>
      </div>
      <div class="nav-right">
        <UserMenu />
      </div>
    </nav>

    <div class="main-container">
      <!-- 左侧：导入与统计 -->
      <aside class="sidebar">
        <div class="control-panel">
          <h3>📅 {{ day }} 交易复盘</h3>
          <div v-if="fileInfo" class="file-info">
            <div class="file-meta">{{ dayTradeCount }} 手成交</div>
            <div class="file-meta">数据来自已导入的全部交易记录（{{ fileInfo.fileCount }} 个文件）</div>
          </div>
          <div v-if="errorMsg" class="review-error">
            <span>{{ errorMsg }}</span>
          </div>
          <div v-for="(w, i) in warnings" :key="i" class="review-warning">⚠ {{ w }}</div>
        </div>

        <!-- 统计 -->
        <div v-if="curve && curve.trades > 0" class="backtest-result">
          <h4>📊 统计</h4>
          <!-- 三行：累计盈亏 / 交易日期 + 手续费合计 / 交易笔数 + 胜率。
               没有手续费数据时第二行只有交易日期，让它占满整行，避免半行留空 -->
          <div class="result-grid">
            <div class="result-item wide">
              <div class="result-label">累计盈亏{{ feeApplied ? '（已扣手续费）' : '' }}</div>
              <div class="result-value" :class="pnlClass(stats.totalPnl)">{{ money(stats.totalPnl) }}</div>
            </div>
            <div class="result-item" :class="{ wide: !fileInfo.hasFee }">
              <div class="result-label">交易日期</div>
              <div class="result-value neutral">
                <span class="result-date-part">{{ day.replaceAll('-', '/') }}</span>
              </div>
            </div>
            <div v-if="fileInfo.hasFee" class="result-item">
              <div class="result-label">手续费合计</div>
              <div class="result-value neutral">{{ plain(stats.totalFee) }}</div>
            </div>
            <div class="result-item">
              <div class="result-label">交易笔数</div>
              <div class="result-value neutral">{{ stats.closeCount }}</div>
            </div>
            <div class="result-item">
              <div class="result-label">胜率</div>
              <div class="result-value" :class="stats.winRate >= 50 ? 'positive' : 'negative'">
                {{ stats.winRate.toFixed(2) }}%
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 右侧：盈亏曲线 / 当天 K 线 -->
      <div v-if="noDayData" class="chart-container day-empty">
        <div class="empty-icon">🔍</div>
        <div class="empty-title">{{ day }} 没有成交记录</div>
        <div class="empty-desc">这一天不在已导入的交易记录里</div>
        <router-link to="/review" class="day-empty-btn">返回账户总览</router-link>
      </div>
      <div v-else class="chart-container">
        <div class="chart-header">
          <div class="view-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              class="view-tab"
              :class="{ active: viewMode === 'curve' }"
              :aria-selected="viewMode === 'curve'"
              @click="viewMode = 'curve'"
            >
              账户盈亏曲线
            </button>
            <button
              type="button"
              role="tab"
              class="view-tab"
              :class="{ active: viewMode === 'kline' }"
              :aria-selected="viewMode === 'kline'"
              @click="viewMode = 'kline'"
            >
              当天交易回放
            </button>
          </div>
          <div class="data-info" v-if="fileInfo">
            <div class="info-item">
              <span class="info-label">品种:</span>
              <!-- 曲线 Tab：只有「全部」一个选项（不可改）；回放 Tab：选项是导入文件里包含的品种 -->
              <el-select
                v-if="viewMode === 'kline'"
                v-model="klineProduct"
                size="small"
                class="product-select"
                :disabled="!fileInfo.products.length"
              >
                <el-option v-for="p in fileInfo.products" :key="p" :label="p" :value="p" />
              </el-select>
              <el-select v-else model-value="" size="small" class="product-select" disabled placeholder="全部">
                <el-option label="全部" value="" />
              </el-select>
            </div>
          </div>
        </div>

        <!-- 当天交易回放：第一次打开 Tab 时才挂载（此时才请求接口），之后用 v-show 保留组件和数据，
             切回来不再重复请求。不能一开始就挂载：ECharts 容器在隐藏时宽度为 0，初始化出来的图是空的；
             而一旦挂载过，隐藏再显示时组件内的 ResizeObserver 会自动重新量尺寸 -->
        <ReviewKline
          v-if="klineVisited"
          v-show="viewMode === 'kline'"
          :active="viewMode === 'kline'"
          :review-id="fileInfo?.reviewId || ''"
          :products="klineProducts"
          :days="tradingDays"
        />

        <!-- 账户盈亏曲线：用 v-show 保留 DOM（图表只初始化一次，切回来时调 resize 重新量尺寸）。数据由本页取，组件只负责画 -->
        <ReviewFunding
          v-show="viewMode === 'curve'"
          ref="fundingRef"
          :curve="curve"
          :file-info="fileInfo"
          :loading="loading"
          :loading-text="loadingText"
          @error="errorMsg = $event"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getReviewOverview, getReviewCurve } from '@/api'
import ReviewKline from './ReviewKline.vue'
import ReviewFunding from './ReviewFunding.vue'

// ---------- 状态 ----------
const route = useRoute()
const router = useRouter()
// 当前交易日（来自路由 /review/day/:day）
const day = computed(() => String(route.params.day || ''))
const loading = ref(false)
const loadingText = ref('')
const errorMsg = ref('')
const warnings = ref([])
const fileInfo = ref(null)         // { reviewId, filename, products, start, end, tradeCount }
const curve = ref(null)            // { points, stats, trades }

// 右侧视图：资金曲线 / 当天 K 线
const viewMode = ref('curve')
// 当天交易回放是否打开过：打开过就一直保留组件（缓存），不再卸载重载
const klineVisited = ref(false)
watch(viewMode, (mode) => {
  if (mode === 'kline') klineVisited.value = true
})
// 当天交易回放选中的品种（右上角下拉框）：选项是导入文件里包含的品种，导入新文件时默认选第一个
const klineProduct = ref('')
// 传给回放组件的品种数组用 computed 缓存：模板里直接写 [klineProduct] 每次渲染都会生成新数组
const klineProducts = computed(() => (klineProduct.value ? [klineProduct.value] : []))
watch(
  () => fileInfo.value?.products,
  (list) => {
    if (!list?.length) klineProduct.value = ''
    else if (!list.includes(klineProduct.value)) klineProduct.value = list[0]
  },
  { immediate: true }
)
// 当天交易回放：固定看路由里的这一天
const tradingDays = computed(() => (day.value ? [day.value] : []))

const stats = computed(() => curve.value?.stats || {})
// 是否扣手续费：文件里有手续费数据就扣（没有就是未扣手续费的平仓盈亏）。不再提供开关
const feeApplied = computed(() => !!fileInfo.value?.hasFee)

// ---------- 格式化（红涨绿跌，与项目其它页面一致）----------
const plain = (v) => Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const money = (v) => (v > 0 ? '+' : '') + plain(v)
const pnlClass = (v) => (v > 0 ? 'positive' : v < 0 ? 'negative' : 'neutral')

// ---------- 图表 ----------
// 账户盈亏曲线在 ReviewFunding.vue 里，这里只拿它的引用：从别的标签切回来时让它重新量一次尺寸
const fundingRef = ref(null)
// 从 K 线视图切回资金曲线：图表容器之前被 display:none 隐藏过，尺寸要重新量一次
watch(viewMode, async (mode) => {
  if (mode !== 'curve') return
  await nextTick()
  fundingRef.value?.resize()
})

// ---------- 数据流程 ----------
// 从 axios 错误里取出后端给的可读提示（silent 请求不会弹全局提示，需要页面自己展示）
function errorText(error, fallback) {
  const data = error?.response?.data
  if (data?.message) return data.message
  if (error?.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (error?.request && !error?.response) return '无法连接后端服务，请确认应用已正常启动'
  // 有响应但不是后端约定的 JSON（比如代理报错页、旧版后端的 HTML 错误页）：按状态码说明原因，
  // 不能只给一句笼统的“xx失败”，用户没法判断该怎么办
  const status = error?.response?.status
  if (status === 404 || status === 405) return `${fallback}：后端不支持这个操作（HTTP ${status}），可能是后端版本过旧，请重启后端`
  if (status === 502 || status === 503 || status === 504) return `${fallback}：后端没有响应（HTTP ${status}），请确认后端已启动`
  if (status) return `${fallback}（HTTP ${status}）`
  return error?.message ? `${fallback}：${error.message}` : fallback
}

// ---------- 数据：合并后的全部交易记录（reviewId）+ 当天 ----------
let retried = false                // reviewId 失效时只自动重取一次，避免死循环
const allDays = ref([])            // 有成交的全部交易日（升序），上一日 / 下一日用
const dayTradeCount = ref(0)       // 当天成交手数
const noDayData = ref(false)         // 路由里的这一天没有成交（手输地址 / 文件被删）

const dayIndex = computed(() => allDays.value.indexOf(day.value))
const prevDay = computed(() => (dayIndex.value > 0 ? allDays.value[dayIndex.value - 1] : ''))
const nextDay = computed(() => (dayIndex.value >= 0 && dayIndex.value < allDays.value.length - 1 ? allDays.value[dayIndex.value + 1] : ''))
const gotoDay = (d) => d && router.push({ name: 'ReviewDay', params: { day: d } })

// 拉取总览，得到合并后的 reviewId；再按当天取曲线。reviewId 在后端缓存里，重启 / 文件变化后会换新
async function loadAll() {
  errorMsg.value = ''
  warnings.value = []
  loading.value = true
  loadingText.value = '正在加载交易记录...'
  try {
    const res = await getReviewOverview({ fee: 1 })
    allDays.value = (res.days || []).map((d) => d.day)
    const today = (res.days || []).find((d) => d.day === day.value)
    dayTradeCount.value = today?.volume || 0
    noDayData.value = !today
    // 当天可选品种：总览里的品种列表。回放页默认选成交额最大的品种
    fileInfo.value = {
      reviewId: res.reviewId,
      filename: day.value,
      products: (res.products || []).map((p) => p.product),
      hasFee: !!res.hasFee,
      fileCount: res.fileCount || 0,
      days: [day.value]
    }
    warnings.value = res.warnings || []
    if (!today) {
      curve.value = null
      return
    }
    await fetchCurve(true)
  } catch (error) {
    errorMsg.value = errorText(error, '加载交易记录失败')
  } finally {
    loading.value = false
  }
}

// 换日（上一日 / 下一日）：组件复用，路由参数变了就重新取当天的曲线
watch(day, () => {
  retried = false
  if (fileInfo.value) loadAll()   // 回放组件的 days 随 day 变化，自己会刷新
})

loadAll()
let requestSeq = 0
async function fetchCurve(isFirst = false) {
  if (!fileInfo.value) return
  // 防止快速切换文件时，旧请求的结果覆盖新请求
  const seq = ++requestSeq
  loading.value = true
  loadingText.value = '正在生成曲线...'
  try {
    // 不再有筛选条件：全部品种、整个文件的时间范围（不传 products / start / end），有手续费数据就扣
    const res = await getReviewCurve({
      reviewId: fileInfo.value.reviewId,
      start: day.value,
      end: day.value,
      fee: feeApplied.value ? 1 : 0
    })
    if (seq !== requestSeq) return
    curve.value = res
    errorMsg.value = ''
    // 新版后端一定会返回 openMarks（没有开仓时是空数组）；字段缺失说明运行的是旧版后端，画不出开仓点。
    // 打包版的后端（src-tauri/sidecar）需要重新构建（npm run backend:build）才会更新。
    const staleMsg = '后端版本过旧，没有返回开仓数据，图上不会显示开仓点；请重启后端（打包版需重新执行 npm run backend:build）'
    warnings.value = warnings.value.filter((w) => w !== staleMsg)
    if (!Array.isArray(res.openMarks)) warnings.value.push(staleMsg)
    // 图表由 ReviewFunding 组件监听 curve 自己重画；绘图出错它会通过 error 事件通知这里（见模板）
  } catch (error) {
    if (seq !== requestSeq) return
    if (error?.response?.data?.expired) {
      // 后端缓存里的合并记录失效了（后端重启 / 被挤出缓存）：重新取一次总览换新的 reviewId，只重试一次
      fileInfo.value = null
      curve.value = null
      if (isFirst && !retried) {
        retried = true
        loading.value = false
        await loadAll()
        return
      }
      errorMsg.value = '交易记录已失效，请返回账户总览后重新进入'
    } else if (!isFirst) {
      errorMsg.value = errorText(error, '获取盈亏曲线失败')
    } else {
      throw error
    }
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

</script>

<style scoped>
@import '@/styles/Review.css';
</style>
