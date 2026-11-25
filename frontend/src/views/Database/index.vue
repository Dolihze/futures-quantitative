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
      <!-- 导入方式：固定高度的卡片，切换方式时高度不变 -->
      <div class="db-import">
        <div class="db-import-head">
          <span class="db-import-title">导入方式</span>
          <el-select v-model="importMode" size="default" style="width: 150px" :disabled="imp.busy">
            <el-option value="bulk" label="批量导入" />
            <el-option value="single" label="单个导入" />
          </el-select>
          <span class="db-import-hint">
            {{ importMode === 'bulk' ? '上传全量压缩包，按品种自动挑出所有合约' : '直接导入单个或多个 tick CSV 文件' }}
          </span>
        </div>

        <!-- 批量导入：选品种 + 上传全量压缩包 -->
        <div v-if="importMode === 'bulk'" class="db-import-body db-bulk">
          <p class="db-bulk-desc">
            压缩包结构：<code>YYYYMM/YYYYMMDD/合约.zip</code>（如 <code>202611/20261102/fu2611.zip</code>）。
            挑出所选品种的所有合约，解压后读取文件内的交易日，改名为「合约名_YYYYMMDD」保存，规则与单个 CSV 导入一致。
          </p>
          <div class="db-bulk-form">
            <span class="db-bulk-label">品种</span>
            <el-select v-model="imp.products" multiple collapse-tags collapse-tags-tooltip :max-collapse-tags="2"
                       filterable allow-create default-first-option clearable
                       placeholder="可多选，也可输入品种代码，如 fu" style="width: 320px" :disabled="imp.busy"
                       popper-class="db-product-popper">
              <el-option v-for="p in FUTURES_PRODUCTS" :key="p.value" :value="p.value" :label="`${p.label}（${p.value}）`">
                <!-- 点击由 el-option 处理，checkbox 只负责显示勾选状态 -->
                <el-checkbox :model-value="imp.products.includes(p.value)" tabindex="-1" class="db-product-check">
                  {{ p.label }}（{{ p.value }}）
                </el-checkbox>
              </el-option>
            </el-select>
            <el-checkbox v-model="imp.overwrite" :disabled="imp.busy">已存在的同名文件直接覆盖（默认跳过）</el-checkbox>
            <el-upload
              ref="bulkUploadRef"
              :auto-upload="false"
              :show-file-list="false"
              accept=".zip"
              :disabled="imp.busy || !bulkProducts.length"
              :on-change="handleBulkFileChange"
              class="db-bulk-upload"
            >
              <el-button type="primary" :disabled="imp.busy || !bulkProducts.length" :loading="imp.busy">
                {{ imp.busy ? '导入中...' : '选择压缩包并导入' }}
              </el-button>
            </el-upload>
            <span v-if="!bulkProducts.length && !imp.busy" class="db-bulk-label">请先选择品种</span>
          </div>

          <!-- 固定高度的进度 / 结果区，内容多时内部滚动 -->
          <div class="db-bulk-status">
            <template v-if="imp.busy">
              <el-progress :percentage="imp.percent" :stroke-width="14" text-inside
                           :status="undefined" :format="() => `${imp.percent}%`" />
              <div class="db-bulk-progress-text">{{ imp.stageText }}</div>
            </template>
            <template v-else-if="imp.result">
              <div class="db-bulk-summary">
                「{{ imp.result.originalName }}」· 品种
                <b v-for="p in imp.result.products" :key="p" :class="{ bad: !imp.result.perProduct[p] }"
                   :title="imp.result.perProduct[p] ? '' : '压缩包里没有这个品种的数据'">{{ p }}（{{ imp.result.perProduct[p] || 0 }}）</b>：
                命中 <b>{{ imp.result.matched }}</b> 份，
                新增 <b class="ok">{{ imp.result.imported }}</b>，
                覆盖 <b class="ok">{{ imp.result.overwritten }}</b>，
                跳过 <b>{{ imp.result.skipped }}</b>，
                失败 <b :class="{ bad: imp.result.failed }">{{ imp.result.failed }}</b>；
                涉及 {{ imp.result.contracts.length }} 个合约
                <template v-if="imp.result.contracts.length">（{{ imp.result.contracts.join('、') }}）</template>
              </div>
              <div v-for="(it, i) in bulkFails" :key="i" class="db-bulk-fail">
                <span :title="it.label">{{ it.label }}</span>
                <span>{{ it.message }}</span>
              </div>
            </template>
            <div v-else-if="imp.error" class="db-bulk-fail"><span>导入失败</span><span>{{ imp.error }}</span></div>
            <div v-else class="db-bulk-idle">选择品种并上传压缩包后，这里显示导入进度和结果</div>
          </div>
        </div>

        <!-- 单个导入：原来的 CSV 上传 -->
        <div v-else class="db-import-body db-single">
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
        </div>
      </div>

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
          <span>已导入的品种（{{ productGroups.length }}）· 合约（{{ contracts.length }}）</span>
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
            <span class="c-symbol">品种 / 合约</span>
            <span class="c-num">文件</span>
            <span class="c-num">交易日</span>
            <span class="c-num">tick 数</span>
            <span class="c-range">时间范围</span>
            <span class="c-flag">BS</span>
            <span class="c-op">操作</span>
          </div>

          <template v-for="g in productGroups" :key="g.code">
            <!-- 一级：品种 -->
            <div class="db-row db-row-item db-row-product" :class="{ open: expandedProducts.includes(g.code) }" @click="toggleProduct(g.code)">
              <span class="c-symbol">
                <i class="arrow">{{ expandedProducts.includes(g.code) ? '▾' : '▸' }}</i>
                <b>{{ g.code }}</b>
                <small v-if="g.label">{{ g.label }}</small>
                <em class="product-count">{{ g.contracts.length }} 个合约</em>
              </span>
              <span class="c-num">{{ g.fileCount }}</span>
              <span class="c-num">{{ g.dayCount }}</span>
              <span class="c-num">{{ g.tickCount.toLocaleString() }}</span>
              <span class="c-range">{{ g.start.slice(0, 16) }} ~ {{ g.end.slice(0, 16) }}</span>
              <span class="c-flag" :class="g.hasBs ? 'yes' : 'no'" :title="g.hasBs ? '全部合约都有成交性质' : '部分合约没有 BS 列，不支持足迹图'">
                {{ g.hasBs ? '✓' : '—' }}
              </span>
              <span class="c-op">
                <a class="op-link danger" @click.stop="removeProduct(g)">删除</a>
              </span>
            </div>

            <!-- 二级：该品种名下的合约 -->
            <template v-if="expandedProducts.includes(g.code)">
              <template v-for="c in g.contracts" :key="c.symbol">
                <div class="db-row db-row-item db-row-contract" :class="{ open: expanded === c.symbol }" @click="toggle(c.symbol)">
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

                <!-- 三级：该合约名下的文件 -->
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
            </template>
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
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import {
  uploadDepthFile, getDepthContracts, deleteDepthContract, deleteDepthFile,
  uploadReviewFile, getReviewFilesDetail, deleteReviewFile
} from '@/api'
import { FUTURES_PRODUCTS } from '@/constants/futuresProducts'
import { useDepthImportStore } from '@/stores/depthImport'

const route = useRoute()
// 当前 Tab：trades = 历史交易记录管理，market = 历史行情数据管理（可用 ?tab=market 直达）
const tab = ref(route.query.tab === 'market' ? 'market' : 'trades')
const uploadRef = ref(null)
const loading = ref(false)
const dir = ref('depth_files')
const contracts = ref([])
const unrecognized = ref([])
const expanded = ref('')          // 展开的合约（显示它名下的文件）
const expandedProducts = ref([])  // 展开的品种（显示它名下的合约），可同时展开多个
const tasks = ref([])

const totalFiles = computed(() => contracts.value.reduce((s, c) => s + c.fileCount, 0))
const totalTicks = computed(() => contracts.value.reduce((s, c) => s + c.tickCount, 0))
const totalSize = computed(() => contracts.value.reduce((s, c) => s + c.size, 0))

// ---------- 按品种分组（一级：品种，二级：合约，三级：文件） ----------
const PRODUCT_NAMES = Object.fromEntries(FUTURES_PRODUCTS.map((p) => [p.value, p.label]))

// 合约代码 -> 品种代码（大写）：带交易所前缀（SHFE.fu2611）或后缀（A2607.XDCE）都取合约本体开头的字母
function productOf(symbol) {
  const s = String(symbol || '').trim()
  const parts = s.split('.')
  // 取含数字的那一段当合约本体（SHFE.fu2611 -> fu2611；A2607.XDCE -> A2607）；都没有数字就取第一段
  const body = parts.find((p) => /\d/.test(p)) || parts[0]
  const m = body.match(/^[A-Za-z]+/)
  return m ? m[0].toUpperCase() : '其他'
}

const productGroups = computed(() => {
  const map = new Map()
  for (const c of contracts.value) {
    const code = productOf(c.symbol)
    let g = map.get(code)
    if (!g) {
      g = { code, label: PRODUCT_NAMES[code.toLowerCase()] || '', contracts: [], fileCount: 0, tickCount: 0, size: 0, days: new Set(), start: c.start, end: c.end, hasBs: true }
      map.set(code, g)
    }
    g.contracts.push(c)
    g.fileCount += c.fileCount
    g.tickCount += c.tickCount
    g.size += c.size
    c.days.forEach((d) => g.days.add(d))
    if (c.start < g.start) g.start = c.start
    if (c.end > g.end) g.end = c.end
    g.hasBs = g.hasBs && c.hasBs
  }
  const out = [...map.values()].map((g) => ({
    ...g,
    dayCount: g.days.size,
    // 合约由新到旧：交割月份晚的在前（fu2710 在 fu2611 上面）。代码里的数字是 YYMM，自然排序后倒序即可
    contracts: g.contracts.slice().sort((a, b) => b.symbol.localeCompare(a.symbol, undefined, { numeric: true }))
  }))
  out.sort((a, b) => a.code.localeCompare(b.code))
  return out
})

const toggleProduct = (code) => {
  const i = expandedProducts.value.indexOf(code)
  if (i >= 0) expandedProducts.value.splice(i, 1)
  else expandedProducts.value.push(code)
}

// 删除整个品种：把它名下所有合约依次删掉
async function removeProduct(g) {
  try {
    await ElMessageBox.confirm(
      `确定要删除品种「${g.code}${g.label ? ' ' + g.label : ''}」吗？将删除它名下 ${g.contracts.length} 个合约、${g.fileCount} 个文件（${g.tickCount.toLocaleString()} 笔 tick），此操作不可恢复。`,
      '删除品种',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  let ok = 0
  let failed = 0
  for (const c of g.contracts) {
    try {
      await deleteDepthContract(c.symbol)
      ok++
    } catch (error) {
      if (!error?.response?.data?.fileMissing) failed++
    }
  }
  if (failed) ElMessage.warning(`已删除 ${ok} 个合约，${failed} 个删除失败`)
  else ElMessage.success(`已删除品种 ${g.code}（${ok} 个合约）`)
  loadContracts()
}

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
    expandedProducts.value = expandedProducts.value.filter((code) => contracts.value.some((c) => productOf(c.symbol) === code))
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

// ---------- 导入方式 + 批量导入：全量压缩包 -> 指定品种 ----------
// 批量导入的状态和轮询放在 store（stores/depthImport.js），不随页面销毁：导入中途切到别的页面再回来，进度还在
const importMode = ref('bulk')   // bulk = 批量导入，single = 单个导入
const bulkUploadRef = ref(null)
const imp = useDepthImportStore()

// 已选品种：只留字母并转小写、去重（和后端 normalize_products 一致）；输入框里手敲的非法代码会被过滤掉
const bulkProducts = computed(() => {
  /** @type {string[]} */
  const out = []
  for (const raw of imp.products || []) {
    const p = String(raw || '').trim().toLowerCase()
    if (/^[a-z]{1,4}$/.test(p) && !out.includes(p)) out.push(p)
  }
  return out
})
const bulkFails = computed(() => (imp.result?.items || []).filter((i) => i.status === 'failed'))

async function handleBulkFileChange(uploadFile) {
  const file = uploadFile.raw
  if (!file || imp.busy) return
  bulkUploadRef.value?.clearFiles()
  const nativeInput = /** @type {HTMLInputElement | null} */ (document.querySelector('.db-bulk-upload input[type=file]'))
  if (nativeInput) nativeInput.value = ''

  if (!bulkProducts.value.length) {
    ElMessage.warning('请先选择品种')
    return
  }
  if (!file.name.toLowerCase().endsWith('.zip')) {
    ElMessage.warning('仅支持 .zip 压缩包')
    return
  }
  imp.products = bulkProducts.value   // 提交规范化后的品种列表
  imp.start(file)                     // 不 await：任务在 store 里跑，离开页面也不受影响
}

// 任务成功结束（页面还在时）：提示 + 刷新合约列表。离开页面期间结束的，回来时 onMounted 会重新加载列表
watch(() => imp.finishedSeq, () => {
  const res = imp.result
  if (!res) return
  const ok = res.imported + res.overwritten
  if (res.failed) ElMessage.warning(`导入完成：成功 ${ok} 份，失败 ${res.failed} 份`)
  else ElMessage.success(`导入完成：新增 ${res.imported} 份，覆盖 ${res.overwritten} 份，跳过 ${res.skipped} 份`)
  loadContracts()
})

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
  imp.restore()   // 导入进行中时离开又回来 / 应用被刷新：接管后端正在跑的任务，继续显示进度
})
</script>

<style scoped>
@import '@/styles/Database.css';
</style>

<style>
@import '@/styles/DatabasePopper.css';
</style>
