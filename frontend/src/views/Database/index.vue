<template>
  <div class="db-container">
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

    <div class="db-body">
      <!-- 标题 + 导入 -->
      <div class="db-head">
        <div>
          <h2>数据库管理</h2>
          <p v-if="tab === 'market'" class="db-sub">
            管理深度行情用的历史 tick 数据。文件保存在项目根目录的 <code>{{ dir }}</code> 文件夹，
            导入时会读取文件内的交易日并自动改名为「合约名_YYYYMMDD」，重名时提示是否覆盖；
            同一合约的多个文件（如每个交易日一个）会自动合并成一条时间线。
          </p>
          <p v-else class="db-sub">
            管理交易复盘用的历史交易记录（成交明细 Excel / CSV）。文件保存在项目根目录的 <code>{{ reviewDir }}</code> 文件夹，
            保持原文件名，重名时提示是否覆盖。在「交易复盘」页左侧可直接点击切换这里的文件。
          </p>
        </div>
        <router-link v-if="tab === 'market'" to="/depth" class="db-goto">去深度行情看图 →</router-link>
        <router-link v-else to="/review" class="db-goto">去交易复盘 →</router-link>
      </div>

      <div class="db-tabs" role="tablist">
        <button type="button" role="tab" class="db-tab" :class="{ active: tab === 'trades' }"
                :aria-selected="tab === 'trades'" @click="tab = 'trades'">历史交易记录管理</button>
        <button type="button" role="tab" class="db-tab" :class="{ active: tab === 'market' }"
                :aria-selected="tab === 'market'" @click="tab = 'market'">历史行情数据管理</button>
      </div>

      <!-- ============ 历史交易记录管理 ============ -->
      <template v-if="tab === 'trades'">
        <el-upload
          ref="reviewUploadRef"
          drag
          multiple
          :auto-upload="false"
          :show-file-list="false"
          accept=".xlsx,.xls,.csv"
          :on-change="handleReviewFileChange"
          class="db-upload review-db-upload"
        >
          <div class="db-upload-text">
            <div class="db-upload-main">拖拽交易记录到此处，或 <em>点击选择</em>（可一次选多个）</div>
            <div class="db-upload-tip">支持 .xlsx / .xls / .csv，单个 20MB 以内。</div>
          </div>
        </el-upload>

        <div v-if="reviewTasks.length" class="db-tasks">
          <div v-for="t in reviewTasks" :key="t.id" class="db-task" :class="t.status">
            <span class="task-icon">{{ t.status === 'ok' ? '✓' : t.status === 'error' ? '✕' : t.status === 'skip' ? '–' : '…' }}</span>
            <span class="task-name" :title="t.name">{{ t.name }}</span>
            <span class="task-msg">{{ t.message }}</span>
          </div>
        </div>

        <div class="db-panel">
          <div class="db-panel-head">
            <span>已导入的交易记录（{{ reviewFiles.length }}）</span>
            <span class="db-total" v-if="reviewFiles.length">
              共 {{ reviewTradeTotal.toLocaleString() }} 手成交 · {{ formatSize(reviewSizeTotal) }}
            </span>
            <a class="db-link" :class="{ disabled: reviewLoading }" @click="loadReviewFiles">刷新</a>
          </div>

          <div v-if="!reviewFiles.length" class="db-empty">
            {{ reviewLoading ? '加载中...' : `还没有数据。导入交易记录后会出现在这里；也可以直接把 Excel 放进 ${reviewDir} 文件夹后点“刷新”。` }}
          </div>

          <div v-else class="db-table">
            <div class="db-row db-row-head review-row">
              <span class="c-symbol">文件</span>
              <span class="c-days">交易日</span>
              <span class="c-products">品种</span>
              <span class="c-num">成交手数</span>
              <span class="c-num">大小</span>
              <span class="c-op">操作</span>
            </div>
            <div v-for="f in reviewFiles" :key="f.name" class="db-row db-row-item review-row">
              <span class="c-symbol"><b :title="f.name">📄 {{ f.name }}</b></span>
              <template v-if="!f.error">
                <span class="c-days">{{ dayRange(f.days) }}</span>
                <span class="c-products" :title="f.products.join('、')">{{ f.products.join('、') }}</span>
                <span class="c-num">{{ f.tradeCount.toLocaleString() }}</span>
              </template>
              <span v-else class="c-err" :title="f.error">⚠ {{ f.error }}</span>
              <span class="c-num">{{ formatSize(f.size) }}</span>
              <span class="c-op">
                <router-link v-if="!f.error" :to="{ path: '/review', query: { file: f.name } }" class="op-link">查看</router-link>
                <a class="op-link danger" @click.stop="removeReviewFile(f.name)">删除</a>
              </span>
            </div>
          </div>
        </div>
      </template>

      <!-- ============ 历史行情数据管理 ============ -->
      <template v-else>
      <el-upload
        ref="uploadRef"
        drag
        multiple
        :auto-upload="false"
        :show-file-list="false"
        accept=".csv"
        :on-change="handleFileChange"
        class="db-upload"
      >
        <div class="db-upload-text">
          <div class="db-upload-main">拖拽 tick CSV 到此处，或 <em>点击选择</em>（可一次选多个）</div>
          <div class="db-upload-tip">
            支持 .csv（UTF-8 / GBK），单个 500MB 以内。必需列：时间、最新价；
            建议带成交量、持仓量、买卖盘口，足迹图还需要 BS（成交性质）列。
          </div>
        </div>
      </el-upload>

      <!-- 导入进度 / 结果 -->
      <div v-if="tasks.length" class="db-tasks">
        <div v-for="t in tasks" :key="t.id" class="db-task" :class="t.status">
          <span class="task-icon">{{ t.status === 'ok' ? '✓' : t.status === 'error' ? '✕' : t.status === 'skip' ? '–' : '…' }}</span>
          <span class="task-name" :title="t.name">{{ t.name }}</span>
          <span class="task-msg">{{ t.message }}</span>
        </div>
      </div>

      <!-- 合约表 -->
      <div class="db-panel">
        <div class="db-panel-head">
          <span>已导入的合约（{{ contracts.length }}）</span>
          <span class="db-total" v-if="contracts.length">
            共 {{ totalFiles }} 个文件 · {{ totalTicks.toLocaleString() }} 笔 tick · {{ formatSize(totalSize) }}
          </span>
          <a class="db-link" :class="{ disabled: loading }" @click="loadContracts">刷新</a>
        </div>

        <div v-if="!contracts.length" class="db-empty">
          {{ loading ? '加载中...' : `还没有数据。导入 tick CSV 后会出现在这里；也可以直接把 CSV 放进 ${dir} 文件夹后点“刷新”。` }}
        </div>

        <div v-else class="db-table">
          <div class="db-row db-row-head">
            <span class="c-symbol">合约</span>
            <span class="c-num">文件</span>
            <span class="c-num">交易日</span>
            <span class="c-num">tick 数</span>
            <span class="c-range">时间范围</span>
            <span class="c-flag">BS</span>
            <span class="c-op">操作</span>
          </div>

          <template v-for="c in contracts" :key="c.symbol">
            <div class="db-row db-row-item" :class="{ open: expanded === c.symbol }" @click="toggle(c.symbol)">
              <span class="c-symbol">
                <i class="arrow">{{ expanded === c.symbol ? '▾' : '▸' }}</i>
                <b>{{ c.symbol }}</b>
                <small v-if="c.name">{{ c.name }}</small>
              </span>
              <span class="c-num">{{ c.fileCount }}</span>
              <span class="c-num">{{ c.dayCount }}</span>
              <span class="c-num">{{ c.tickCount.toLocaleString() }}</span>
              <span class="c-range">{{ c.start.slice(0, 16) }} ~ {{ c.end.slice(0, 16) }}</span>
              <span class="c-flag" :class="c.hasBs ? 'yes' : 'no'" :title="c.hasBs ? '有成交性质，支持足迹图' : '没有 BS 列，不支持足迹图'">
                {{ c.hasBs ? '✓' : '—' }}
              </span>
              <span class="c-op">
                <router-link :to="{ path: '/depth', query: { symbol: c.symbol } }" class="op-link" @click.stop>查看</router-link>
                <a class="op-link danger" @click.stop="removeContract(c)">删除</a>
              </span>
            </div>

            <!-- 展开：该合约名下的文件 -->
            <div v-if="expanded === c.symbol" class="db-files">
              <div v-for="f in c.files" :key="f.name" class="db-file">
                <span class="f-name" :title="f.name">📄 {{ f.name }}</span>
                <span class="f-days">{{ dayRange(f.days) }}</span>
                <span class="f-num">{{ f.tickCount.toLocaleString() }} 笔</span>
                <span class="f-num">{{ formatSize(f.size) }}</span>
                <span class="f-time">{{ formatMtime(f.mtime) }}</span>
                <a class="op-link danger" @click.stop="removeFile(f.name)">删除</a>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 无法识别的文件 -->
      <div v-if="unrecognized.length" class="db-panel warn">
        <div class="db-panel-head"><span>⚠ 无法识别的文件（{{ unrecognized.length }}）</span></div>
        <div class="db-files flat">
          <div v-for="f in unrecognized" :key="f.name" class="db-file">
            <span class="f-name" :title="f.name">📄 {{ f.name }}</span>
            <span class="f-err">{{ f.error }}</span>
            <span class="f-num">{{ formatSize(f.size) }}</span>
            <a class="op-link danger" @click.stop="removeFile(f.name)">删除</a>
          </div>
        </div>
      </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import {
  uploadDepthFile, getDepthContracts, deleteDepthContract, deleteDepthFile,
  uploadReviewFile, getReviewFilesDetail, deleteReviewFile
} from '@/api'

const route = useRoute()
// 当前 Tab：trades = 历史交易记录管理，market = 历史行情数据管理（可用 ?tab=market 直达）
const tab = ref(route.query.tab === 'market' ? 'market' : 'trades')
const uploadRef = ref(null)
const loading = ref(false)
const dir = ref('depth_files')
const contracts = ref([])
const unrecognized = ref([])
const expanded = ref('')
const tasks = ref([])

const totalFiles = computed(() => contracts.value.reduce((s, c) => s + c.fileCount, 0))
const totalTicks = computed(() => contracts.value.reduce((s, c) => s + c.tickCount, 0))
const totalSize = computed(() => contracts.value.reduce((s, c) => s + c.size, 0))

const formatSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)
const formatMtime = (s) => {
  const d = new Date(s * 1000)
  const p = (v) => String(v).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
const dayRange = (days) => (!days.length ? '' : days.length === 1 ? days[0] : `${days[0]} ~ ${days[days.length - 1]}（${days.length} 天）`)

// 后端给的可读提示（silent 请求不会弹全局提示）
function errorText(error, fallback) {
  const data = error?.response?.data
  if (data?.message) return data.message
  if (error?.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (error?.request && !error?.response) return '无法连接后端服务，请确认应用已正常启动'
  const status = error?.response?.status
  if (status === 404 || status === 405) return `${fallback}：后端不支持这个操作（HTTP ${status}），可能是后端版本过旧，请重启后端`
  if (status) return `${fallback}（HTTP ${status}）`
  return error?.message ? `${fallback}：${error.message}` : fallback
}

async function loadContracts() {
  loading.value = true
  try {
    const res = await getDepthContracts()
    contracts.value = res.contracts || []
    unrecognized.value = res.unrecognized || []
    dir.value = res.dir || dir.value
    if (expanded.value && !contracts.value.some((c) => c.symbol === expanded.value)) expanded.value = ''
  } catch (error) {
    contracts.value = []
    unrecognized.value = []
    ElMessage.error(errorText(error, '读取合约列表失败'))
  } finally {
    loading.value = false
  }
}

const toggle = (symbol) => {
  expanded.value = expanded.value === symbol ? '' : symbol
}

// ---------- 导入（可多选，逐个处理；同名文件逐个询问是否覆盖） ----------
// el-upload 多选时每个文件触发一次 on-change；用一条串行队列保证覆盖确认框一次只弹一个
let queue = Promise.resolve()
let taskSeq = 0

function handleFileChange(uploadFile) {
  const file = uploadFile.raw
  if (!file) return
  // 同复盘：清掉组件内部列表和原生 input，否则再选同一个文件不会触发 change
  uploadRef.value?.clearFiles()
  const nativeInput = /** @type {HTMLInputElement | null} */ (document.querySelector('.db-upload input[type=file]'))
  if (nativeInput) nativeInput.value = ''

  const task = { id: ++taskSeq, name: file.name, status: 'wait', message: '等待导入...' }
  tasks.value = [task, ...tasks.value].slice(0, 12)
  queue = queue.then(() => importOne(file, task)).catch(() => {})
}

async function importOne(file, task) {
  const upd = (status, message) => { task.status = status; task.message = message }
  upd('wait', '正在解析并保存...')
  try {
    let res
    try {
      res = await uploadDepthFile(file)
    } catch (error) {
      if (error?.response?.status !== 409 || !error.response.data?.exists) throw error
      const name = error.response.data.name || file.name
      task.name = name
      try {
        await ElMessageBox.confirm(`文件重复：文件夹中已存在「${name}」（导入文件「${file.name}」），是否覆盖？`, '文件重复', {
          confirmButtonText: '覆盖', cancelButtonText: '跳过', type: 'warning'
        })
      } catch {
        upd('skip', '已存在，已跳过')
        return
      }
      upd('wait', '正在覆盖...')
      res = await uploadDepthFile(file, true)
    }
    const extra = res.warnings?.length ? `（${res.warnings[0]}）` : ''
    if (res.savedName) task.name = res.savedName
    upd('ok', `${res.symbol} · ${res.tickCount.toLocaleString()} 笔 · ${res.days.length} 个交易日${res.hasBs ? '' : ' · 无 BS 列'}${extra}`)
    await loadContracts()
  } catch (error) {
    upd('error', errorText(error, '导入失败'))
  }
}

// ---------- 删除 ----------
async function removeContract(c) {
  try {
    await ElMessageBox.confirm(
      `确定要删除合约「${c.symbol}」吗？将删除它名下的 ${c.fileCount} 个文件（${c.tickCount.toLocaleString()} 笔 tick），此操作不可恢复。`,
      '删除合约',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await deleteDepthContract(c.symbol)
    ElMessage.success(`已删除 ${c.symbol}`)
  } catch (error) {
    if (!error?.response?.data?.fileMissing) ElMessage.error(errorText(error, '删除失败'))
  }
  loadContracts()
}

async function removeFile(name) {
  try {
    await ElMessageBox.confirm(`确定要删除文件「${name}」吗？`, '删除文件', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    })
  } catch {
    return
  }
  try {
    await deleteDepthFile(name)
    ElMessage.success(`已删除 ${name}`)
  } catch (error) {
    if (!error?.response?.data?.fileMissing) ElMessage.error(errorText(error, '删除失败'))
  }
  loadContracts()
}

// ==================== 历史交易记录管理（交易复盘的文件） ====================
const reviewUploadRef = ref(null)
const reviewLoading = ref(false)
const reviewDir = ref('review_files')
const reviewFiles = ref([])
const reviewTasks = ref([])

const reviewTradeTotal = computed(() => reviewFiles.value.reduce((s, f) => s + (f.tradeCount || 0), 0))
const reviewSizeTotal = computed(() => reviewFiles.value.reduce((s, f) => s + f.size, 0))

async function loadReviewFiles() {
  reviewLoading.value = true
  try {
    const res = await getReviewFilesDetail()
    reviewFiles.value = res.files || []
    reviewDir.value = res.dir || reviewDir.value
  } catch (error) {
    reviewFiles.value = []
    ElMessage.error(errorText(error, '读取交易记录列表失败'))
  } finally {
    reviewLoading.value = false
  }
}

let reviewQueue = Promise.resolve()
let reviewTaskSeq = 0

function handleReviewFileChange(uploadFile) {
  const file = uploadFile.raw
  if (!file) return
  reviewUploadRef.value?.clearFiles()
  const nativeInput = /** @type {HTMLInputElement | null} */ (document.querySelector('.review-db-upload input[type=file]'))
  if (nativeInput) nativeInput.value = ''

  const task = { id: ++reviewTaskSeq, name: file.name, status: 'wait', message: '等待导入...' }
  reviewTasks.value = [task, ...reviewTasks.value].slice(0, 12)
  reviewQueue = reviewQueue.then(() => importReviewOne(file, task)).catch(() => {})
}

async function importReviewOne(file, task) {
  const upd = (status, message) => { task.status = status; task.message = message }
  upd('wait', '正在解析并保存...')
  try {
    let res
    try {
      res = await uploadReviewFile(file)
    } catch (error) {
      if (error?.response?.status !== 409 || !error.response.data?.exists) throw error
      const name = error.response.data.name || file.name
      try {
        await ElMessageBox.confirm(`文件重复：文件夹中已存在「${name}」，是否覆盖？`, '文件重复', {
          confirmButtonText: '覆盖', cancelButtonText: '跳过', type: 'warning'
        })
      } catch {
        upd('skip', '已存在，已跳过')
        return
      }
      upd('wait', '正在覆盖...')
      res = await uploadReviewFile(file, true)
    }
    const extra = res.warnings?.length ? `（${res.warnings[0]}）` : ''
    upd('ok', `${res.tradeCount} 手成交 · ${res.days.length} 个交易日 · ${res.products.length} 个品种${extra}`)
    await loadReviewFiles()
  } catch (error) {
    upd('error', errorText(error, '导入失败'))
  }
}

async function removeReviewFile(name) {
  try {
    await ElMessageBox.confirm(`确定要删除交易记录文件「${name}」吗？此操作不可恢复。`, '删除文件', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    })
  } catch {
    return
  }
  try {
    await deleteReviewFile(name)
    ElMessage.success(`已删除 ${name}`)
  } catch (error) {
    if (!error?.response?.data?.fileMissing) ElMessage.error(errorText(error, '删除失败'))
  }
  loadReviewFiles()
}

onMounted(() => {
  loadReviewFiles()
  loadContracts()
})
</script>

<style scoped>
@import '@/styles/Database.css';
</style>
