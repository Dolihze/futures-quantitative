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
        <UserMenu />
      </div>
    </nav>

    <div class="main-container">
      <!-- 左侧：导入与统计 -->
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
              {{ fileInfo.tradeCount }} 手成交 · {{ fileInfo.products.length }} 个品种
            </div>
            <div class="file-meta">交易日 {{ tradeDateText }}</div>
          </div>

          <!-- 已导入的文件：保存在项目的 review_files 文件夹里，点一下就能直接切换分析 -->
          <div class="saved-files">
            <div class="saved-files-head">
              <span>已导入的文件</span>
              <a class="saved-files-refresh" :class="{ disabled: filesLoading }" @click="loadFileList">刷新</a>
            </div>
            <div v-if="!reviewFiles.length" class="saved-files-empty">
              {{ filesLoading ? '加载中...' : `还没有文件。导入的文件会保存到项目根目录的 ${filesDir} 文件夹，也可以直接把 Excel 放进去后点“刷新”` }}
            </div>
            <ul v-else class="saved-files-list">
              <li
                v-for="f in reviewFiles"
                :key="f.name"
                class="saved-file"
                :class="{ active: f.name === currentFileName, disabled: loading }"
                :title="f.name"
                @click="handleOpenFile(f.name)"
              >
                <div class="saved-file-main">
                  <div class="saved-file-name">{{ f.name }}</div>
                  <div class="saved-file-meta">{{ formatMtime(f.mtime) }} · {{ formatSize(f.size) }}</div>
                </div>
                <a class="saved-file-delete" title="删除这个文件" @click.stop="handleDeleteFile(f.name)">删除</a>
              </li>
            </ul>
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
              <!-- 跨多天时 “起 ~ 止” 放不进半行：每个日期保持完整，只允许在两个日期之间换行 -->
              <div class="result-value neutral">
                <span v-for="(d, i) in statDateParts" :key="i" class="result-date-part">{{ d }}</span>
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
      <div class="chart-container">
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { uploadReviewFile, getReviewFiles, openReviewFile, deleteReviewFile, getReviewCurve } from '@/api'
import ReviewKline from './ReviewKline.vue'
import ReviewFunding from './ReviewFunding.vue'

// ---------- 状态 ----------
const uploadRef = ref(null)
const loading = ref(false)
const loadingText = ref('')
const errorMsg = ref('')
const warnings = ref([])
const fileInfo = ref(null)         // { reviewId, filename, products, start, end, tradeCount }
const curve = ref(null)            // { points, stats, trades }

// 交易日文字：导出的 Excel 通常只有一天，只有一天时显示 “2026-10-29”，跨多天（比如夜盘归到下一交易日）才显示范围
const tradeDateText = computed(() => {
  if (!fileInfo.value) return ''
  const start = fileInfo.value.start.slice(0, 10)
  const end = fileInfo.value.end.slice(0, 10)
  return start === end ? start : `${start} ~ ${end}`
})

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
// 统计里的“交易日期”，格式 YYYY/MM/DD；规则同上：一天只写一天，跨多天写“起 ~ 止”。
// 拆成数组渲染：跨多天时两个日期各自成段，窄的格子里只在两个日期之间换行，不会把一个日期从中间截断
const statDateParts = computed(() => {
  if (!fileInfo.value) return []
  const start = fileInfo.value.start.slice(0, 10).replaceAll('-', '/')
  const end = fileInfo.value.end.slice(0, 10).replaceAll('-', '/')
  return start === end ? [start] : [`${start} ~`, end]
})

// 当天交易回放能看的交易日 = 文件里有成交的交易日
const tradingDays = computed(() => fileInfo.value?.days || [])

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
    let res
    try {
      res = await uploadReviewFile(file)
    } catch (error) {
      // 文件夹里已有同名文件：后端没有解析也没有保存，弹窗让用户确认是否覆盖
      if (error?.response?.status !== 409 || !error.response.data?.exists) throw error
      loading.value = false      // 确认框期间不要一直转圈，也不要挡住别的操作
      const name = error.response.data.name || file.name
      try {
        await ElMessageBox.confirm(`文件夹中已存在「${name}」，是否覆盖？`, '文件已存在', {
          confirmButtonText: '覆盖',
          cancelButtonText: '取消',
          type: 'warning'
        })
      } catch {
        return                   // 用户取消：什么都不改，保留当前正在分析的数据
      }
      loading.value = true
      res = await uploadReviewFile(file, true)
    }
    await applyReviewResult(res)
    ElMessage.success(res.overwritten ? `已覆盖并导入 ${res.tradeCount} 手成交` : `已导入 ${res.tradeCount} 手成交`)
    // 上传的文件会保存到 review_files 文件夹，刷新“已导入文件”列表
    loadFileList()
  } catch (error) {
    // 解析失败时保留上一份已成功导入的数据，只显示错误
    errorMsg.value = errorText(error, '文件解析失败')
  } finally {
    loading.value = false
  }
}

// 把一份解析结果（上传或从文件夹选择，返回结构相同）设为当前数据，并取一次曲线
async function applyReviewResult(res) {
  fileInfo.value = res
  warnings.value = res.warnings || []
  await fetchCurve(true)
}

// ---------- 已导入文件（项目 review_files 文件夹）----------
const reviewFiles = ref([])          // [{ name, size, mtime }]，最近修改的在前
const filesLoading = ref(false)
const filesDir = ref('review_files')
const currentFileName = computed(() => fileInfo.value?.filename || '')

async function loadFileList() {
  filesLoading.value = true
  try {
    const res = await getReviewFiles()
    reviewFiles.value = res.files || []
    filesDir.value = res.dir || filesDir.value
  } catch (error) {
    // 列表只是辅助功能，取不到时不打断主流程，也不弹错误
    reviewFiles.value = []
  } finally {
    filesLoading.value = false
  }
}

// 点击列表里的文件：直接分析，不用再从外部选文件。点击当前正在分析的文件不重复加载
let openSeq = 0
async function handleOpenFile(name) {
  if (loading.value || name === currentFileName.value) return
  const seq = ++openSeq
  errorMsg.value = ''
  warnings.value = []
  loading.value = true
  loadingText.value = '正在解析交易记录...'
  try {
    const res = await openReviewFile(name)
    if (seq !== openSeq) return
    await applyReviewResult(res)
    ElMessage.success(`已切换到 ${name}（${res.tradeCount} 手成交）`)
  } catch (error) {
    if (seq !== openSeq) return
    errorMsg.value = errorText(error, '文件解析失败')
    // 文件已经不在文件夹里（被删除或移动）：刷新列表，让它从列表里消失
    if (error?.response?.data?.fileMissing) loadFileList()
  } finally {
    if (seq === openSeq) loading.value = false
  }
}

// 删除列表里的文件：确认后只删磁盘上的文件。已经解析进内存、正在分析的数据不受影响（图表照常），
// 只是之后不能再从列表里选它
async function handleDeleteFile(name) {
  if (loading.value) return
  try {
    await ElMessageBox.confirm(
      name === currentFileName.value
        ? `确定要删除「${name}」吗？这是当前正在分析的文件，删除后当前图表不受影响，但之后无法再从列表中选择它。`
        : `确定要删除「${name}」吗？`,
      '删除文件',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await deleteReviewFile(name)
    ElMessage.success(`已删除 ${name}`)
  } catch (error) {
    // 后端明确说“文件不存在”（fileMissing）：文件已经被别的程序删了，目的达到，不报错，只刷新列表。
    // 不能只看 404 状态码：旧版后端没有这个接口时也会回 404 / 405，那是接口问题，必须报错
    if (!error?.response?.data?.fileMissing) {
      ElMessage.error(errorText(error, '删除失败'))
    }
  }
  loadFileList()
}

const formatSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)
const formatMtime = (s) => {
  const d = new Date(s * 1000)
  const p = (v) => String(v).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

loadFileList()

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

</script>

<style scoped>
@import '@/styles/Review.css';
</style>
