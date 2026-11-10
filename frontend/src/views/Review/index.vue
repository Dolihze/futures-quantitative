<template>
  <div class="review-container">
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
        <div class="user-info">
          <div class="user-avatar">{{ userStore.username[0]?.toUpperCase() || 'U' }}</div>
          <span class="username">{{ userStore.username || '未登录' }}</span>
        </div>
        <el-button type="danger" size="small" plain @click="handleLogout">退出登录</el-button>
      </div>
    </nav>

    <div class="main-container">
      <!-- 左侧：导入与筛选 -->
      <aside class="sidebar">
        <div class="control-panel">
          <h3>📂 导入交易记录</h3>
          <el-upload
            ref="uploadRef"
            drag
            :auto-upload="false"
            :show-file-list="false"
            accept=".xlsx,.xls,.csv"
            :on-change="handleFileChange"
            class="review-upload"
          >
            <div class="upload-text">
              <div class="upload-main">拖拽文件到此处，或 <em>点击选择</em></div>
              <div class="upload-tip">支持 .xlsx / .xls / .csv，20MB 以内</div>
            </div>
          </el-upload>

          <div v-if="fileInfo" class="file-info">
            <div class="file-name" :title="fileInfo.filename">📄 {{ fileInfo.filename }}</div>
            <div class="file-meta">
              {{ fileInfo.tradeCount }} 笔成交 · {{ fileInfo.products.length }} 个品种
            </div>
            <div class="file-meta">交易日 {{ fileInfo.start.slice(0, 10) }} ~ {{ fileInfo.end.slice(0, 10) }}</div>
          </div>

          <div v-if="errorMsg" class="review-error">
            <span>{{ errorMsg }}</span>
          </div>
          <div v-for="(w, i) in warnings" :key="i" class="review-warning">⚠ {{ w }}</div>
        </div>

        <div v-if="fileInfo" class="control-panel">
          <h3>🔎 筛选条件</h3>
          <el-form label-position="top" size="default">
            <el-form-item label="时间范围">
              <el-date-picker
                v-model="range"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DD"
                :disabled-date="disabledDate"
                :clearable="false"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="交易品种">
              <el-select
                v-model="selectedProducts"
                multiple
                collapse-tags
                collapse-tags-tooltip
                placeholder="全部品种"
                style="width: 100%"
              >
                <el-option v-for="p in fileInfo.products" :key="p" :label="p" :value="p" />
              </el-select>
              <div class="filter-actions">
                <a @click="selectedProducts = [...fileInfo.products]">全选</a>
                <a @click="selectedProducts = []">清空（= 全部）</a>
              </div>
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="includeFee" :disabled="!fileInfo.hasFee">扣除手续费</el-checkbox>
              <div v-if="!fileInfo.hasFee" class="fee-hint">该文件没有手续费数据，曲线为未扣手续费的平仓盈亏</div>
            </el-form-item>
            <el-button style="width: 100%" @click="resetFilters">重置筛选</el-button>
          </el-form>
        </div>

        <!-- 统计 -->
        <div v-if="curve && curve.trades > 0" class="backtest-result">
          <h4>📊 统计（当前筛选）</h4>
          <div class="result-grid">
            <div class="result-item wide">
              <div class="result-label">累计盈亏{{ feeApplied ? '（已扣手续费）' : '' }}</div>
              <div class="result-value" :class="pnlClass(stats.totalPnl)">{{ money(stats.totalPnl) }}</div>
            </div>
            <div class="result-item">
              <div class="result-label">平仓笔数</div>
              <div class="result-value neutral">{{ stats.closeCount }}</div>
            </div>
            <div class="result-item">
              <div class="result-label">胜率</div>
              <div class="result-value" :class="stats.winRate >= 50 ? 'positive' : 'negative'">
                {{ stats.winRate.toFixed(2) }}%
              </div>
            </div>
            <div class="result-item">
              <div class="result-label">最大回撤</div>
              <div class="result-value negative">{{ plain(stats.maxDrawdown) }}</div>
            </div>
            <div v-if="fileInfo.hasFee" class="result-item">
              <div class="result-label">手续费合计</div>
              <div class="result-value neutral">{{ plain(stats.totalFee) }}</div>
            </div>
            <div class="result-item">
              <div class="result-label">单笔最大盈利</div>
              <div class="result-value positive">{{ money(stats.maxProfit) }}</div>
            </div>
            <div class="result-item">
              <div class="result-label">单笔最大亏损</div>
              <div class="result-value negative">{{ money(stats.maxLoss) }}</div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 右侧：盈亏曲线 / 当天 K 线 -->
      <div class="chart-container">
        <div class="chart-header">
          <div class="view-switch">
            <h2>{{ viewMode === 'curve' ? '账户盈亏曲线' : '当天交易回放' }}</h2>
            <el-radio-group v-model="viewMode" size="small">
              <el-radio-button value="curve">资金曲线</el-radio-button>
              <el-radio-button value="kline">当天K线</el-radio-button>
            </el-radio-group>
          </div>
          <div class="data-info" v-if="fileInfo">
            <div class="info-item">
              <span class="info-label">品种:</span>
              <span class="info-value">{{ productLabel }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">成交:</span>
              <span class="info-value">{{ curve ? curve.trades : 0 }} 笔</span>
            </div>
          </div>
        </div>

        <!-- 当天 K 线：用 v-if 而不是 v-show，ECharts 容器在隐藏时宽度为 0，初始化出来的图是空的 -->
        <ReviewKline
          v-if="viewMode === 'kline'"
          :review-id="fileInfo?.reviewId || ''"
          :products="selectedProducts"
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
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { uploadReviewFile, getReviewCurve, logout } from '@/api'
import { useUserStore } from '@/stores/user'
import ReviewKline from './ReviewKline.vue'
import ReviewFunding from './ReviewFunding.vue'

const router = useRouter()
const userStore = useUserStore()

// ---------- 状态 ----------
const uploadRef = ref(null)
const loading = ref(false)
const loadingText = ref('')
const errorMsg = ref('')
const warnings = ref([])
const fileInfo = ref(null)         // { reviewId, filename, products, start, end, tradeCount }
const range = ref(null)            // ['YYYY-MM-DD', 'YYYY-MM-DD']
const selectedProducts = ref([])   // 空 = 全部
const includeFee = ref(true)
const curve = ref(null)            // { points, stats, trades }

// 右侧视图：资金曲线 / 当天 K 线
const viewMode = ref('curve')
// 当天 K 线能选的交易日 = 文件里有成交的交易日，且在左侧“时间范围”之内
const tradingDays = computed(() => {
  const all = fileInfo.value?.days || []
  if (!range.value) return all
  return all.filter((d) => d >= range.value[0] && d <= range.value[1])
})

const stats = computed(() => curve.value?.stats || {})
// 实际是否扣了手续费：用户勾选了，并且文件里确实有手续费数据
const feeApplied = computed(() => includeFee.value && !!fileInfo.value?.hasFee)
const productLabel = computed(() => {
  const all = fileInfo.value?.products || []
  if (!selectedProducts.value.length || selectedProducts.value.length === all.length) return '全部'
  return selectedProducts.value.join('、')
})

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
  return fallback
}

async function handleFileChange(uploadFile) {
  const file = uploadFile.raw
  if (!file) return
  // 文件列表不展示，也不需要保留：每次选择后立刻清掉，否则组件会把第一个文件留在内部列表里，
  // 之后再选文件（比如第一次选错了换一个）不会再触发 on-change，界面像是“没反应”。
  uploadRef.value?.clearFiles()
  // 浏览器对“和上次相同的文件”不会再触发 change，所以改完文件想重新选同一个路径会毫无反应。
  // 把原生 input 的值也清掉，下次选同一个文件才会再次触发。
  const nativeInput = document.querySelector('.review-upload input[type=file]')
  if (nativeInput) nativeInput.value = ''
  errorMsg.value = ''
  warnings.value = []
  loading.value = true
  loadingText.value = '正在解析交易记录...'
  try {
    const res = await uploadReviewFile(file)
    fileInfo.value = res
    warnings.value = res.warnings || []
    // 下面改筛选条件是程序设置的，不是用户操作；这里会马上自己取一次曲线，
    // 所以让 watch 跳过这一轮，否则同一份数据会被请求两次（watch 是异步触发的，clearTimeout 来不及取消）
    skipNextFilterWatch = true
    selectedProducts.value = []
    includeFee.value = true
    range.value = [res.start.slice(0, 10), res.end.slice(0, 10)]
    // watch 在下一个 tick 才触发。如果新值和旧值相同（重复导入同一份文件），watch 根本不会触发，
    // 标志就不会被消费，会误吞用户之后真正的筛选操作——所以这里等一个 tick 后无条件复位。
    await nextTick()
    skipNextFilterWatch = false
    await fetchCurve(true)
    ElMessage.success(`已导入 ${res.tradeCount} 笔成交`)
  } catch (error) {
    // 解析失败时保留上一份已成功导入的数据，只显示错误
    errorMsg.value = errorText(error, '文件解析失败')
  } finally {
    loading.value = false
  }
}

let requestSeq = 0
async function fetchCurve(isFirst = false) {
  if (!fileInfo.value || !range.value) return
  // 防止快速切换筛选条件时，旧请求的结果覆盖新请求
  const seq = ++requestSeq
  loading.value = true
  loadingText.value = '正在生成曲线...'
  try {
    const res = await getReviewCurve({
      reviewId: fileInfo.value.reviewId,
      products: selectedProducts.value.join(','),
      start: range.value[0],
      end: range.value[1],
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
      fileInfo.value = null
      curve.value = null
      errorMsg.value = error.response.data.message
    } else if (!isFirst) {
      errorMsg.value = errorText(error, '获取盈亏曲线失败')
    } else {
      throw error
    }
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

// 筛选条件变化后自动刷新（防抖，避免连续点选时频繁请求）
let filterTimer = null
let skipNextFilterWatch = false
watch([range, selectedProducts, includeFee], () => {
  if (skipNextFilterWatch) {
    skipNextFilterWatch = false
    return
  }
  if (!fileInfo.value) return
  clearTimeout(filterTimer)
  filterTimer = setTimeout(() => fetchCurve(), 250)
})

function disabledDate(date) {
  if (!fileInfo.value) return false
  const d = date.getTime()
  const min = new Date(fileInfo.value.start.slice(0, 10) + 'T00:00:00').getTime()
  const max = new Date(fileInfo.value.end.slice(0, 10) + 'T23:59:59').getTime()
  return d < min || d > max
}

function resetFilters() {
  if (!fileInfo.value) return
  range.value = [fileInfo.value.start.slice(0, 10), fileInfo.value.end.slice(0, 10)]
  selectedProducts.value = []
  includeFee.value = true
}

// 退出登录（与其它页面一致）
const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await logout()
    userStore.logout()
    ElMessage.success('已退出登录')
    router.push('/login')
  } catch (error) {
    // 用户取消操作
  }
}

onUnmounted(() => {
  clearTimeout(filterTimer)
})
</script>

<style scoped>
@import '@/styles/Review.css';
</style>
