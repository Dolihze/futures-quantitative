<template>
  <div class="depth-container">
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
      <!-- 左侧：已导入的合约，点击切换 -->
      <aside class="sidebar">
        <div class="control-panel">
          <div class="panel-head">
            <h3>📈 合约</h3>
            <a class="saved-files-refresh" :class="{ disabled: contractsLoading }" @click="loadContracts">刷新</a>
          </div>

          <div v-if="!contracts.length" class="contract-empty">
            <template v-if="contractsLoading">加载中...</template>
            <template v-else>
              还没有历史数据。
              <router-link to="/database" class="empty-link">去「数据库管理」导入 tick 数据 →</router-link>
            </template>
          </div>

          <ul v-else class="contract-list">
            <li
              v-for="c in contracts"
              :key="c.symbol"
              class="contract-item"
              :class="{ active: c.symbol === currentSymbol, disabled: loading }"
              :title="`${c.symbol}  ${c.fileCount} 个文件`"
              @click="openContract(c.symbol)"
            >
              <div class="contract-main">
                <span class="contract-symbol">{{ c.symbol }}</span>
                <span v-if="c.name" class="contract-name">{{ c.name }}</span>
              </div>
              <div class="contract-meta">
                {{ rangeText(c) }} · {{ c.dayCount }} 个交易日 · {{ compactNum(c.tickCount) }} 笔
              </div>
            </li>
          </ul>

          <router-link v-if="contracts.length" to="/database" class="manage-link">管理 / 导入数据 →</router-link>

          <div v-if="errorMsg" class="depth-error"><span>{{ errorMsg }}</span></div>
          <div v-for="(w, i) in warnings" :key="i" class="depth-warning">⚠ {{ w }}</div>
        </div>

        <!-- 当前 K 线统计 -->
        <div v-if="bars.length" class="stat-panel">
          <h4>📊 当前视图</h4>
          <div class="stat-grid">
            <div class="stat-item"><div class="stat-label">K 线根数</div><div class="stat-value">{{ bars.length }}</div></div>
            <div class="stat-item"><div class="stat-label">tick 笔数</div><div class="stat-value">{{ totalTicksInView.toLocaleString() }}</div></div>
            <div class="stat-item"><div class="stat-label">最高</div><div class="stat-value up">{{ viewHigh }}</div></div>
            <div class="stat-item"><div class="stat-label">最低</div><div class="stat-value down">{{ viewLow }}</div></div>
            <div class="stat-item wide"><div class="stat-label">总成交量</div><div class="stat-value">{{ totalVolume.toLocaleString() }}</div></div>
          </div>
        </div>
      </aside>

      <!-- 右侧：工具栏 + K 线 + 盘口 -->
      <div class="chart-container">
        <div class="chart-header">
          <div class="toolbar-title">深度行情<span v-if="fileInfo" class="toolbar-symbol">{{ fileInfo.symbol }}</span></div>
          <div v-if="fileInfo" class="toolbar">
            <div class="info-item">
              <el-radio-group v-model="viewMode" size="small" @change="onViewModeChange">
                <el-radio-button value="kline">K 线</el-radio-button>
                <el-radio-button value="footprint">足迹图</el-radio-button>
              </el-radio-group>
            </div>
            <div class="info-item">
              <span class="info-label">周期:</span>
              <el-radio-group v-model="period" size="small" @change="loadKline">
                <el-radio-button v-for="p in PERIOD_OPTIONS" :key="p.value" :value="p.value">{{ p.label }}</el-radio-button>
              </el-radio-group>
            </div>
            <div class="info-item">
              <span class="info-label">交易日:</span>
              <el-select v-model="day" size="small" class="day-select" :disabled="period === 1440" @change="loadKline">
                <el-option label="全部" value="" />
                <el-option v-for="d in fileInfo.days" :key="d" :label="d" :value="d" />
              </el-select>
            </div>
            <el-popover placement="bottom-end" :width="280" trigger="click" popper-class="depth-settings">
              <template #reference>
                <el-button size="small" class="settings-btn">⚙ 设置</el-button>
              </template>
              <div class="settings-panel">
                <div class="settings-title">足迹图设置</div>
                <div class="settings-row">
                  <span class="settings-label">大单阈值（手）</span>
                  <el-input-number
                    v-model="bigOrder"
                    :min="1"
                    :max="100000"
                    :step="10"
                    size="small"
                    controls-position="right"
                  />
                </div>
                <div class="settings-tip">单笔 tick 成交量 ≥ 阈值，在足迹图上用圆圈标出。默认 {{ DEFAULT_BIG_ORDER }} 手，修改后自动保存。</div>
                <el-button size="small" @click="bigOrder = DEFAULT_BIG_ORDER">恢复默认</el-button>
              </div>
            </el-popover>
          </div>
        </div>

        <div class="depth-body">
          <div class="depth-main">
            <DepthKline
              v-if="viewMode === 'kline'"
              :bars="bars"
              :loading="klineLoading"
              :selected-index="selectedBar"
              :empty-title="fileInfo ? '这个范围没有 K 线' : emptyTitle"
              :empty-desc="fileInfo ? '换一个周期或交易日试试' : emptyDesc"
              @hover="onHover"
              @select="onSelect"
            />
            <DepthFootprint
              v-else
              :bars="bars"
              :big-orders="bigOrders"
              :big-order="bigOrder"
              :tick-size="tickSize"
              :loading="klineLoading"
              :selected-index="selectedBar"
              :empty-title="footprintError ? '无法生成足迹图' : fileInfo ? '这个范围没有数据' : emptyTitle"
              :empty-desc="footprintError || (fileInfo ? '换一个周期或交易日试试' : emptyDesc)"
              @hover="onHover"
              @select="onSelect"
            />

            <!-- 回放控制条 -->
            <div v-if="fileInfo" class="replay-bar">
              <el-button size="small" :disabled="!canStep" @click="step(-1)">◀ 上一笔</el-button>
              <el-button size="small" type="primary" :disabled="!canStep" @click="togglePlay">
                {{ playing ? '⏸ 暂停' : '▶ 回放' }}
              </el-button>
              <el-button size="small" :disabled="!canStep" @click="step(1)">下一笔 ▶</el-button>
              <div class="replay-speed">
                <span class="info-label">速度:</span>
                <el-select v-model="speed" size="small" class="speed-select">
                  <el-option v-for="s in SPEEDS" :key="s.value" :label="s.label" :value="s.value" />
                </el-select>
              </div>
              <span class="replay-pos">
                {{ cursor >= 0 ? `第 ${(cursor + 1).toLocaleString()} / ${fileInfo.tickCount.toLocaleString()} 笔` : '点击 K 线选择起点' }}
              </span>
              <span v-if="fileInfo.levels === 0" class="replay-note">无盘口列</span>
            </div>
          </div>

          <div class="depth-side">
            <DepthBook :book="shownBook" :prev-price="prevPrice" :loading="bookLoading" :live="playing" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  getDepthContracts, openDepthContract,
  getDepthKline, getDepthFootprint, getDepthTicks
} from '@/api'
import DepthKline from './DepthKline.vue'
import DepthFootprint from './DepthFootprint.vue'
import DepthBook from './DepthBook.vue'

const PERIOD_OPTIONS = [
  { value: 1, label: '1分' }, { value: 5, label: '5分' }, { value: 15, label: '15分' },
  { value: 30, label: '30分' }, { value: 60, label: '60分' }, { value: 1440, label: '日线' }
]
// 回放速度 = 每秒推进的 tick 笔数
const SPEEDS = [
  { value: 2, label: '2 笔/秒' }, { value: 5, label: '5 笔/秒' }, { value: 10, label: '10 笔/秒' },
  { value: 30, label: '30 笔/秒' }, { value: 100, label: '100 笔/秒' }
]
const CHUNK = 200   // 回放预取块大小（笔）

// ---------- 状态 ----------
const route = useRoute()
const loading = ref(false)
const errorMsg = ref('')
const warnings = ref([])
const fileInfo = ref(null)        // { depthId, filename, symbol, name, tickCount, levels, days, start, end }
const period = ref(1)
const day = ref('')
const bars = ref([])
const klineLoading = ref(false)

// 视图：K 线 / 足迹图。两个视图共用周期、交易日、游标、盘口、回放；足迹图的数据里自带 K 线，bars 直接取它
const viewMode = ref('kline')
const bigOrders = ref([])          // 足迹图接口返回的大单（按请求时的阈值过滤过；前端再按当前阈值过滤）
const tickSize = ref(1)
const footprintError = ref('')

// 大单阈值（手）：默认 100，修改后持久化到 localStorage，下次打开保持
const DEFAULT_BIG_ORDER = 100
const BIG_ORDER_KEY = 'depth.bigOrder'
function loadBigOrder() {
  const n = Number(localStorage.getItem(BIG_ORDER_KEY))
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : DEFAULT_BIG_ORDER
}
const bigOrder = ref(loadBigOrder())

// 没有打开任何合约时图区的提示：加载中 / 没有数据（引导去数据库管理）/ 有数据但还没选
const emptyTitle = computed(() => {
  if (loading.value || contractsLoading.value) return '正在加载...'
  return contracts.value.length ? '请选择合约' : '还没有历史数据'
})
const emptyDesc = computed(() => {
  if (loading.value || contractsLoading.value) return ''
  return contracts.value.length ? '从左侧点击一个合约查看行情' : '请先到「数据库管理」导入历史 tick 数据，导入后会出现在左侧合约列表里'
})

// ---------- 统计 ----------
const totalTicksInView = computed(() => bars.value.reduce((s, b) => s + (b.ticks || 0), 0))
const totalVolume = computed(() => bars.value.reduce((s, b) => s + (b.volume || 0), 0))
const viewHigh = computed(() => (bars.value.length ? Math.max(...bars.value.map((b) => b.high)) : '--'))
const viewLow = computed(() => (bars.value.length ? Math.min(...bars.value.map((b) => b.low)) : '--'))

// 从 axios 错误里取后端给的可读提示（silent 请求不会弹全局提示）
function errorText(error, fallback) {
  const data = error?.response?.data
  if (data?.message) return data.message
  if (error?.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (error?.request && !error?.response) return '无法连接后端服务，请确认应用已正常启动'
  const status = error?.response?.status
  if (status === 404 || status === 405) return `${fallback}：后端不支持这个操作（HTTP ${status}），可能是后端版本过旧，请重启后端`
  if (status === 502 || status === 503 || status === 504) return `${fallback}：后端没有响应（HTTP ${status}），请确认后端已启动`
  if (status) return `${fallback}（HTTP ${status}）`
  return error?.message ? `${fallback}：${error.message}` : fallback
}

// ---------- 合约列表 ----------
// 数据的导入和删除在「数据库管理」模块；这里只负责选合约、看图。
// 一个合约可能对应多个文件（比如每个交易日一个），后端会按合约合并成一条时间线。
const contracts = ref([])
const contractsLoading = ref(false)
const currentSymbol = computed(() => fileInfo.value?.symbol || '')
const LAST_SYMBOL_KEY = 'depth.lastSymbol'   // 记住上次看的合约，下次进来自动打开

async function loadContracts() {
  contractsLoading.value = true
  try {
    const res = await getDepthContracts()
    contracts.value = res.contracts || []
    return contracts.value
  } catch (error) {
    contracts.value = []
    errorMsg.value = errorText(error, '读取合约列表失败')
    return []
  } finally {
    contractsLoading.value = false
  }
}

// 解析结果设为当前数据：重置回放状态，默认看最后一个交易日的 1 分钟线
async function applyResult(res) {
  stopPlay()
  resetCursor()
  fileInfo.value = res
  warnings.value = res.warnings || []
  period.value = 1
  day.value = res.days?.length ? res.days[res.days.length - 1] : ''
  // 足迹图要 BS 列：当前合约没有时自动退回 K 线视图，避免一进来就是报错空白页
  if (viewMode.value === 'footprint' && res.hasBs === false) viewMode.value = 'kline'
  await loadKline()
}

let openSeq = 0
async function openContract(symbol) {
  if (loading.value || (symbol === currentSymbol.value && fileInfo.value)) return
  const seq = ++openSeq
  errorMsg.value = ''
  warnings.value = []
  loading.value = true
  try {
    const res = await openDepthContract(symbol)
    if (seq !== openSeq) return
    await applyResult(res)
    localStorage.setItem(LAST_SYMBOL_KEY, symbol)
  } catch (error) {
    if (seq !== openSeq) return
    errorMsg.value = errorText(error, '打开合约失败')
    // 合约已被删除 / 文件消失：刷新列表，别让用户对着一个点不开的条目
    if (error?.response?.data?.fileMissing) loadContracts()
  } finally {
    if (seq === openSeq) loading.value = false
  }
}

// 进入页面：优先 URL 里的 ?symbol=（从数据库管理点「查看」过来），其次上次看的合约，最后是最近导入的那个
async function autoOpen() {
  const list = await loadContracts()
  if (!list.length) return
  const want = [route.query.symbol, localStorage.getItem(LAST_SYMBOL_KEY)]
    .find((sym) => sym && list.some((c) => c.symbol === sym))
  await openContract(want || list[0].symbol)
}

// 从数据库管理跳回来时 query 可能变化（同一个组件实例复用），跟着切换
watch(() => route.query.symbol, (sym) => {
  if (sym && contracts.value.some((c) => c.symbol === sym)) openContract(String(sym))
})

const compactNum = (n) => (n >= 10000 ? `${(n / 10000).toFixed(n >= 100000 ? 0 : 1)} 万` : String(n))
// 时间范围：同一年内省略年份，跨度大时才显示年
const rangeText = (c) => {
  const a = c.start.slice(0, 10)
  const b = c.end.slice(0, 10)
  const short = (d) => d.slice(5)
  if (a.slice(0, 4) !== b.slice(0, 4)) return `${a} ~ ${b}`
  return a === b ? short(a) : `${short(a)} ~ ${short(b)}`
}

onMounted(autoOpen)

// ---------- K 线 / 足迹图 ----------
// 足迹图接口一次返回 K 线 + 价位成交量 + 大单，切到足迹图时 bars 就是它的结果（字段是 K 线的超集）。
// 大单接口按「当前阈值与 100 取小」请求：前端调高阈值时本地过滤即可，调低阈值时才需要重新请求（见 watch bigOrder）
let klineSeq = 0
let reopening = false   // 防止「失效 -> 重开 -> 又失效」死循环
let fetchedBigOrder = DEFAULT_BIG_ORDER   // 当前 bigOrders 是按多大的阈值取回来的
async function loadKline() {
  if (!fileInfo.value) return
  const seq = ++klineSeq
  stopPlay()
  resetCursor()
  klineLoading.value = true
  footprintError.value = ''
  try {
    const params = {
      depthId: fileInfo.value.depthId,
      period: period.value,
      day: period.value === 1440 ? '' : day.value
    }
    if (viewMode.value === 'footprint') {
      fetchedBigOrder = bigOrder.value
      const res = await getDepthFootprint({ ...params, bigOrder: fetchedBigOrder })
      if (seq !== klineSeq) return
      bars.value = res.bars || []
      bigOrders.value = res.bigOrders || []
      tickSize.value = res.tickSize || 1
    } else {
      const res = await getDepthKline(params)
      if (seq !== klineSeq) return
      bars.value = res.bars || []
    }
    errorMsg.value = ''
  } catch (error) {
    if (seq !== klineSeq) return
    bars.value = []
    bigOrders.value = []
    if (error?.response?.data?.expired) {
      // 后端重启 / 缓存被淘汰：数据本身还在磁盘上，自动按合约重新打开，用户无感
      const sym = fileInfo.value?.symbol
      fileInfo.value = null
      if (sym && !reopening) {
        reopening = true
        try { await openContract(sym) } finally { reopening = false }
      } else {
        errorMsg.value = error.response.data.message
      }
    } else if (viewMode.value === 'footprint') {
      // 足迹图失败（比如文件没有 BS 列）放在图区里说明，不占用左侧错误栏
      footprintError.value = errorText(error, '生成足迹图失败')
    } else {
      errorMsg.value = errorText(error, '生成 K 线失败')
    }
  } finally {
    if (seq === klineSeq) klineLoading.value = false
  }
}

function onViewModeChange() {
  loadKline()
}

// 阈值变化：保存；足迹图下，调低阈值（比已取回数据用的阈值更小）需要重新请求才能拿到更多大单，
// 调高则前端本地过滤。请求做 400ms 防抖，避免连续点步进按钮时频繁请求
let bigTimer = null
watch(bigOrder, (v) => {
  const n = Math.max(1, Math.floor(Number(v) || DEFAULT_BIG_ORDER))
  localStorage.setItem(BIG_ORDER_KEY, String(n))
  if (viewMode.value !== 'footprint' || !fileInfo.value) return
  if (n < fetchedBigOrder) {
    clearTimeout(bigTimer)
    bigTimer = setTimeout(async () => {
      try {
        const res = await getDepthFootprint({
          depthId: fileInfo.value.depthId,
          period: period.value,
          day: period.value === 1440 ? '' : day.value,
          bigOrder: n
        })
        bigOrders.value = res.bigOrders || []
        fetchedBigOrder = n
      } catch {
        // 取不到就沿用已有的大单，不打扰用户
      }
    }, 400)
  }
})

// ---------- 历史盘口 ----------
// 盘口来源三种：悬停（预览，不改变游标）、点击/步进/回放（游标，定格）。
// 悬停时显示该 K 线最后一笔 tick 的盘口；鼠标移开恢复显示游标的盘口。
const cursor = ref(-1)              // 当前定格 / 回放所在的 tick 序号，-1 = 未选择
const selectedBar = ref(-1)         // 游标所在的 K 线序号（图上高亮）
const cursorBook = ref(null)
const hoverBook = ref(null)
const bookLoading = ref(false)
const prevPrice = ref(null)
const shownBook = computed(() => hoverBook.value || cursorBook.value)

// tick 缓存：序号 -> book，回放时按块预取，避免逐笔请求
const tickCache = new Map()
const TICK_CACHE_MAX = 5000

function cachePut(list) {
  for (const t of list) tickCache.set(t.index, t)
  // 简单的容量控制：超出时删掉最早插入的一批
  if (tickCache.size > TICK_CACHE_MAX) {
    const drop = tickCache.size - TICK_CACHE_MAX
    let i = 0
    for (const k of tickCache.keys()) {
      if (i++ >= drop) break
      tickCache.delete(k)
    }
  }
}

function resetCursor() {
  cursor.value = -1
  selectedBar.value = -1
  cursorBook.value = null
  hoverBook.value = null
  prevPrice.value = null
  tickCache.clear()
}

// 取第 index 笔的盘口：先查缓存，没有则拉一块（以 index 开头，往后 CHUNK 笔）
async function fetchTick(index, prefetchBack = false) {
  if (tickCache.has(index)) return tickCache.get(index)
  const start = prefetchBack ? Math.max(index - CHUNK + 1, 0) : index
  const res = await getDepthTicks({ depthId: fileInfo.value.depthId, start, count: CHUNK })
  cachePut(res.ticks || [])
  return tickCache.get(index) || null
}

// 悬停预览：节流到下一帧，避免鼠标快速滑动时发出大量请求
let hoverTimer = null
let hoverSeq = 0
function onHover(i) {
  clearTimeout(hoverTimer)
  if (i < 0) {
    hoverSeq++
    hoverBook.value = null
    return
  }
  const bar = bars.value[i]
  if (!bar) return
  hoverTimer = setTimeout(async () => {
    const seq = ++hoverSeq
    try {
      const t = await fetchTick(bar.ti1, true)
      if (seq === hoverSeq) hoverBook.value = t
    } catch {
      // 预览失败不打扰用户
    }
  }, 40)
}

// 点击 K 线：游标定位到这根 K 线的第一笔 tick，作为回放起点
async function onSelect(i) {
  const bar = bars.value[i]
  if (!bar) return
  stopPlay()
  selectedBar.value = i
  await moveTo(bar.ti0)
}

async function moveTo(index) {
  const total = fileInfo.value?.tickCount || 0
  if (index < 0 || index >= total) return false
  bookLoading.value = true
  try {
    const t = await fetchTick(index)
    if (!t) return false
    const prev = index > 0 ? tickCache.get(index - 1) : null
    prevPrice.value = prev ? prev.price : null
    cursor.value = index
    cursorBook.value = t
    hoverBook.value = null
    syncSelectedBar(index)
    return true
  } catch (error) {
    errorMsg.value = errorText(error, '获取盘口失败')
    return false
  } finally {
    bookLoading.value = false
  }
}

// 游标所在 tick 属于哪根 K 线（二分查找；K 线按 ti0 升序）
function syncSelectedBar(index) {
  const arr = bars.value
  let lo = 0
  let hi = arr.length - 1
  let ans = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (arr[mid].ti0 <= index) { ans = mid; lo = mid + 1 } else { hi = mid - 1 }
  }
  selectedBar.value = ans >= 0 && index <= arr[ans].ti1 ? ans : -1
}

// ---------- 步进 / 回放 ----------
const canStep = computed(() => !!fileInfo.value && bars.value.length > 0)
const speed = ref(10)
const playing = ref(false)
let playTimer = null

async function step(delta) {
  stopPlay()
  if (cursor.value < 0) {
    // 还没选起点：从第一根 K 线的第一笔开始
    const first = bars.value[0]
    if (!first) return
    await moveTo(first.ti0)
    return
  }
  await moveTo(cursor.value + delta)
}

function togglePlay() {
  if (playing.value) {
    stopPlay()
    return
  }
  startPlay()
}

async function startPlay() {
  if (cursor.value < 0) {
    const first = bars.value[0]
    if (!first) return
    if (!(await moveTo(first.ti0))) return
  }
  playing.value = true
  scheduleTick()
}

// 用 setTimeout 链而不是 setInterval：每一步等盘口取到再排下一步，网络慢时不会堆积请求
function scheduleTick() {
  clearTimeout(playTimer)
  const interval = Math.max(1000 / speed.value, 16)
  playTimer = setTimeout(async () => {
    if (!playing.value) return
    // 高速时每个定时器推进多笔，保证实际速率接近设定值
    const stepN = Math.max(1, Math.round((speed.value * interval) / 1000))
    const next = cursor.value + stepN
    const total = fileInfo.value?.tickCount || 0
    if (next >= total) {
      await moveTo(total - 1)
      stopPlay()
      return
    }
    // 预取：缓存里没有下一块就提前拉
    if (!tickCache.has(next)) {
      try { await fetchTick(next) } catch { stopPlay(); return }
    }
    if (!playing.value) return
    await moveTo(next)
    // 回放越出当前 K 线范围（比如选了单日）时就停
    if (playing.value) scheduleTick()
  }, interval)
}

function stopPlay() {
  playing.value = false
  clearTimeout(playTimer)
}

// 回放中改速度：立刻按新速度重排下一步
watch(speed, () => {
  if (playing.value) scheduleTick()
})

onUnmounted(() => {
  stopPlay()
  clearTimeout(hoverTimer)
  clearTimeout(bigTimer)
})
</script>

<style scoped>
@import '@/styles/DepthMarket.css';
</style>

<!-- el-popover 的内容渲染在 body 下，不在本组件 DOM 内，scoped 样式命中不了，所以设置面板的样式单独用非 scoped 写，类名带 depth- 前缀避免冲突 -->
<style>
.depth-settings .settings-title {
  margin-bottom: 12px;
  color: var(--accent2);
  font-size: 14px;
  font-weight: 600;
}

.depth-settings .settings-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.depth-settings .settings-row .el-input-number {
  width: 110px;
}

.depth-settings .settings-label {
  color: var(--text-muted2);
  font-size: 13px;
}

.depth-settings .settings-tip {
  margin-bottom: 12px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}
</style>
