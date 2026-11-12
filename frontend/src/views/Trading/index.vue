<template>
  <div class="trading-container">
    <!-- 顶部导航 -->
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
        <ThemeSwitcher />
        <div class="user-info">
          <div class="user-avatar">{{ userStore.username[0]?.toUpperCase() || 'U' }}</div>
          <span>{{ userStore.username || '未登录' }}</span>
        </div>
        <el-button type="danger" size="small" plain @click="handleLogout">退出登录</el-button>
      </div>
    </nav>

    <!-- 主内容 -->
    <div class="main-content">
      <!-- 数据统计 -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">账户权益</div>
          <div class="stat-value">¥ {{ accountInfo.balance }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">可用资金</div>
          <div class="stat-value">¥ {{ accountInfo.available }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">使用率</div>
          <div class="stat-value">{{ accountInfo.usageRate }}%</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">今日盈亏</div>
          <div class="stat-value" :class="accountInfo.profitClass">¥ {{ accountInfo.profit }}</div>
        </div>
      </div>

      <!-- 下单交易（左）与当前委托（右）并排，各占一半宽度 -->
      <div class="trade-row">
        <div class="trade-col">
          <!-- 下单交易模块标题 -->
          <div class="section-header">
            <h2 class="section-title">下单交易</h2>
          </div>

          <!-- 下单交易面板 -->
          <div class="trading-panel">
            <!-- 第一行：合约选择 + 最新行情 -->
            <div class="trading-row">
              <div class="input-group contract-group">
                <div class="input-label">合约</div>
                <el-select
                  v-model="selectedSymbol"
                  filterable
                  :filter-method="filterContracts"
                  :loading="contractsLoading"
                  :placeholder="contractsLoading ? '合约加载中…' : '选择或搜索合约，如 ag2612'"
                  no-data-text="没有匹配的合约"
                  class="contract-select"
                  popper-class="contract-select-popper"
                  @change="onContractPicked"
                  @visible-change="onContractDropdown"
                >
                  <!-- 分组：“常用”（最近选择过的 3 个合约，本地存储）固定在顶部，下面是“全部合约”。
                       没有常用合约时只有一个不带标题的组，外观和以前一样。
                       “全部合约”里不包含已在“常用”里的合约：同一个 value 出现两次会让选中高亮错乱。 -->
                  <template v-for="group in contractGroups" :key="group.key">
                    <!-- 带标题的分组（有常用合约时）：标题用 el-option-group 渲染 -->
                    <el-option-group v-if="group.label" :label="group.label">
                      <el-option
                        v-for="item in group.items"
                        :key="group.key + item.vt_symbol"
                        :label="contractLabel(item.name, item.symbol)"
                        :value="item.vt_symbol"
                      >
                        <div class="contract-option">
                          <span class="contract-option-name">{{ contractLabel(item.name, item.symbol) }}</span>
                          <span class="contract-option-code">{{ item.exchange }}</span>
                        </div>
                      </el-option>
                    </el-option-group>
                    <!-- 没有标题（没有常用合约时）：直接平铺，不渲染分组标题行，外观和以前一样 -->
                    <template v-else>
                      <el-option
                        v-for="item in group.items"
                        :key="group.key + item.vt_symbol"
                        :label="contractLabel(item.name, item.symbol)"
                        :value="item.vt_symbol"
                      >
                        <div class="contract-option">
                          <span class="contract-option-name">{{ contractLabel(item.name, item.symbol) }}</span>
                          <span class="contract-option-code">{{ item.exchange }}</span>
                        </div>
                      </el-option>
                    </template>
                  </template>
                </el-select>
              </div>

              <!-- 行情区：现价 / 买一 / 卖一 三项同一行。不论有没有行情都是同一套结构，没有数据的字段显示 “--”，布局不跳动。
                   每项的数字区是固定宽度的等宽数字，“--” 和真实价格占位一致，标签位置不会跳 -->
              <div class="quote-box">
                <div class="quote-detail">
                  <span class="q-item">现价<b class="q-val" :class="quote ? quoteTrend : ''">{{ fmtPrice(quote?.last_price) }}</b></span>
                  <span class="q-item">买一<b class="q-val up-text">{{ fmtPrice(quote?.bid_price) }}</b></span>
                  <span class="q-item">卖一<b class="q-val down-text">{{ fmtPrice(quote?.ask_price) }}</b></span>
                </div>
              </div>
            </div>

            <!-- 第二行：限价和手数 -->
            <div class="trading-row">
              <!-- 限价输入 -->
              <div class="input-group">
                <div class="input-label">
                  限价
                  <a v-if="quote?.last_price" class="fill-last" @click="fillLastPrice">最新价</a>
                </div>
                <div class="input-wrapper">
                  <input
                    type="number"
                    v-model.number="priceInput"
                    :step="priceTick"
                    placeholder="请输入限价"
                  >
                  <div class="input-btn-group">
                    <button class="input-btn" @click="adjustPrice(1)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="18 15 12 9 6 15"/>
                      </svg>
                    </button>
                    <button class="input-btn" @click="adjustPrice(-1)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="6 9 12 15 18 9"/>
                      </svg>
                    </button>
                  </div>
                </div>
              </div>

              <!-- 手数输入 -->
              <div class="input-group">
                <div class="input-label">手数</div>
                <div class="input-wrapper">
                  <input
                    type="number"
                    v-model.number="volumeInput"
                    min="1"
                    step="1"
                  >
                  <div class="input-btn-group">
                    <button class="input-btn" @click="adjustVolume(1)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="18 15 12 9 6 15"/>
                      </svg>
                    </button>
                    <button class="input-btn" @click="adjustVolume(-1)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="6 9 12 15 18 9"/>
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 第三行：交易操作（均为限价单） -->
            <div class="trading-row">
              <button class="trading-btn long" :disabled="ordering" @click="submitOrder('open_long')">
                买多
              </button>
              <button class="trading-btn short" :disabled="ordering" @click="submitOrder('open_short')">
                卖空
              </button>
              <button class="trading-btn close" :disabled="ordering" @click="submitOrder('close_long')">
                平多
              </button>
              <button class="trading-btn close" :disabled="ordering" @click="submitOrder('close_short')">
                平空
              </button>
            </div>
          </div>
        </div>

        <div class="trade-col orders-col">
          <!-- 委托列表：高度跟随左侧下单面板，内容多时在面板内部滚动 -->
          <div class="section-header orders-header">
            <h2 class="section-title">当前委托</h2>
          </div>
          <div class="orders-panel paged-panel">
            <!-- 表格区：占满面板剩余高度，分页条固定在面板底部（右下角），不随表格滚动 -->
            <div class="paged-body">
              <table class="orders-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>合约</th>
                    <th>方向</th>
                    <th>开平</th>
                    <th class="num">委托价</th>
                    <th class="num">已成 / 委托</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!orders.length">
                    <td colspan="8" class="orders-empty">暂无委托</td>
                  </tr>
                  <tr v-for="o in pagedOrders" :key="o.vt_orderid">
                    <td>{{ o.time }}</td>
                    <td>{{ o.symbol }}</td>
                    <td :class="o.direction === '多' ? 'up-text' : 'down-text'">{{ o.direction }}</td>
                    <td>{{ o.offset }}</td>
                    <td class="num">{{ fmtPrice(o.price) }}</td>
                    <td class="num">{{ o.traded }} / {{ o.volume }}</td>
                    <td><span class="order-status" :class="orderStatusClass(o)">{{ o.status }}</span></td>
                    <td>
                      <a v-if="o.active" class="cancel-link" @click="cancelOne(o)">撤单</a>
                      <span v-else class="muted">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- 分页条始终占位（没有委托时也在，只是禁用），位置不跳动 -->
            <div class="paged-footer">
              <!-- 总数文案用默认插槽自己渲染成“共 N 条”（数字两侧各一个空格）：
                   Element Plus 自带的 total 在没配语言包时是英文 “Total N”，而引入整套中文语言包会带来别的组件文案变化 -->
              <el-pagination
                v-model:current-page="orderPage"
                :page-size="PAGE_SIZE"
                :total="orders.length"
                layout="slot, prev, pager, next"
                size="small"
                background
                :pager-count="5"
              >
                <span class="pager-total">共 {{ orders.length }} 条</span>
              </el-pagination>
            </div>
          </div>
        </div>
      </div>

      <!-- 当前持仓（左）与成交明细（右）并排，各占一半宽度，各自每页 5 条 -->
      <div class="trade-row">
        <div class="trade-col paged-col positions-col">
          <div class="section-header orders-header">
            <h2 class="section-title">当前持仓</h2>
          </div>
          <div class="orders-panel paged-panel">
            <div class="paged-body">
              <table class="orders-table">
                <thead>
                  <tr>
                    <th>合约</th>
                    <th>方向</th>
                    <th class="num">持仓</th>
                    <th class="num">可平</th>
                    <th class="num">开仓均价</th>
                    <th class="num">最新价</th>
                    <th class="num">浮动盈亏</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!positions.length">
                    <td colspan="8" class="orders-empty">暂无持仓</td>
                  </tr>
                  <tr v-for="p in pagedPositions" :key="p.vt_symbol + p.direction">
                    <!-- 合约列只显示代码（如 IF2612）：代码里已含品种和月份，足以区分合约；中文名放进悬停提示，不占列宽 -->
                    <td :title="p.name && p.name !== p.symbol ? p.name : null">{{ p.symbol }}</td>
                    <td :class="p.direction === '多' ? 'up-text' : 'down-text'">{{ p.direction }}</td>
                    <td class="num">{{ p.volume }}</td>
                    <td class="num">{{ p.available }}</td>
                    <td class="num">{{ fmtPrice(p.price ? Number(p.price.toFixed(2)) : null) }}</td>
                    <td class="num">{{ fmtPrice(p.last_price) }}</td>
                    <td class="num" :class="p.pnl > 0 ? 'up-text' : p.pnl < 0 ? 'down-text' : ''">{{ fmtMoney(p.pnl) }}</td>
                    <td>
                      <a class="cancel-link" @click="useForClose(p)">平仓</a>
                      <a class="cancel-link reverse-link" @click="submitReverse(p)">反手</a>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="paged-footer">
              <el-pagination
                v-model:current-page="positionPage"
                :page-size="PAGE_SIZE"
                :total="positions.length"
                layout="slot, prev, pager, next"
                size="small"
                background
                :pager-count="5"
              >
                <span class="pager-total">共 {{ positions.length }} 条</span>
              </el-pagination>
            </div>
          </div>
        </div>

        <div class="trade-col paged-col">
          <div class="section-header orders-header">
            <h2 class="section-title">成交明细</h2>
          </div>
          <div class="orders-panel paged-panel">
            <div class="paged-body">
              <table class="orders-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>合约</th>
                    <th>方向</th>
                    <th>开平</th>
                    <th class="num">成交价</th>
                    <th class="num">成交手数</th>
                    <th>成交编号</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!trades.length">
                    <td colspan="7" class="orders-empty">暂无成交</td>
                  </tr>
                  <tr v-for="t in pagedTrades" :key="t.vt_tradeid">
                    <td>{{ t.time }}</td>
                    <td>{{ t.symbol }}</td>
                    <td :class="t.direction === '多' ? 'up-text' : 'down-text'">{{ t.direction }}</td>
                    <td>{{ t.offset }}</td>
                    <td class="num">{{ fmtPrice(t.price) }}</td>
                    <td class="num">{{ t.volume }}</td>
                    <td class="muted">{{ t.vt_tradeid.split('.').pop() }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="paged-footer">
              <el-pagination
                v-model:current-page="tradePage"
                :page-size="PAGE_SIZE"
                :total="trades.length"
                layout="slot, prev, pager, next"
                size="small"
                background
                :pager-count="5"
              >
                <span class="pager-total">共 {{ trades.length }} 条</span>
              </el-pagination>
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- 自定义弹窗 -->
    <div class="modal-overlay" :class="{ active: showModal }" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
        </div>
        <div class="modal-title">{{ modalTitle }}</div>
        <div class="modal-message">{{ modalMessage }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { logout } from '@/api'
// 交易相关接口走入口层：真实账号请求后端 CTP；调试模式（跳过登录进入）用前端假数据，见 api/trading.js
import {
  getAccount,
  getContracts,
  getQuote,
  placeOrder,
  getOrders,
  cancelOrder,
  getPositions,
  getTrades,
  startReverse
} from '@/api/trading'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

// 量化账号会话是否可用（后端有登录会话）。页面不再展示这个状态，只用来驱动数据加载 / 掉线处理：
// 会话可用时才加载合约、委托、持仓；掉线时清空数据并提示一次；之后自动重连
const isQuantConnected = ref(false)

// 账户信息
const accountInfo = reactive({
  balance: '0.00',
  available: '0.00',
  usageRate: '0.00',
  profit: '0.00',
  profitClass: 'zero'
})

const fmtMoney = (n) =>
  Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// 清空账户展示
const resetAccountInfo = () => {
  Object.assign(accountInfo, {
    balance: '0.00',
    available: '0.00',
    usageRate: '0.00',
    profit: '0.00',
    profitClass: 'zero'
  })
}

// 用后端 CTP 会话的快照刷新账户展示
const applyAccountSnapshot = (snap) => {
  const acc = snap?.account
  if (!acc) return // 首次资金回报还没到，保持原样，下一次轮询再刷新

  const balance = Number(acc.balance) || 0
  const available = Number(acc.available) || 0
  const profit = Number(snap.position_profit) || 0
  const used = balance > 0 ? Math.max(balance - available, 0) : 0

  accountInfo.balance = fmtMoney(balance)
  accountInfo.available = fmtMoney(available)
  accountInfo.usageRate = balance > 0 ? ((used / balance) * 100).toFixed(2) : '0.00'
  accountInfo.profit = fmtMoney(profit)
  accountInfo.profitClass = profit > 0 ? 'positive' : profit < 0 ? 'negative' : 'zero'
}

// 保持连接：进入页面立即请求一次，之后每 3 秒请求一次账户快照，直到离开页面。
//   - 成功：刷新资金；如果之前没连上（刚进页面 / 掉线后恢复），顺便启动委托 / 持仓 / 成交轮询并加载合约
//   - 失败且之前是连上的（网络 / 前置掉线）：清空数据并提示一次；之后静默重试，恢复后自动接上
//   - 失败且之前就没连上（后端启动稍慢、没有登录会话）：静默，等下一次
//   - 请求异常（后端暂时不可达）：不改变状态，下次再试
let accountTimer = null
let disposed = false // 页面已离开：在途请求回来后不再改状态 / 启动轮询
const stopAccountPolling = () => {
  if (accountTimer) {
    clearInterval(accountTimer)
    accountTimer = null
  }
}

const syncAccount = async () => {
  try {
    const res = await getAccount()
    if (disposed) return
    if (res.success) {
      applyAccountSnapshot(res.data)
      if (!isQuantConnected.value) {
        isQuantConnected.value = true
        startTradingPolling() // 加载合约列表、委托、持仓、成交
      }
    } else if (isQuantConnected.value) {
      isQuantConnected.value = false
      stopTradingPolling()
      resetAccountInfo()
      ElMessage.warning('量化账号连接已断开')
    }
  } catch (error) {
    // 后端暂时不可达，下次轮询再试
  }
}

const startAccountPolling = () => {
  stopAccountPolling()
  syncAccount() // 立即请求一次，首屏不用等 3 秒
  accountTimer = setInterval(syncAccount, 3000)
}

// ---------------------------------------------------------------------------
// 合约选择 / 行情 / 限价下单 / 委托
// ---------------------------------------------------------------------------

// 合约列表（登录后由 CTP 异步查询，刚进入页面时可能还没就绪，就绪前自动重试）
const contracts = ref([])
const filteredContracts = ref([])
const contractsLoading = ref(false)
const selectedSymbol = ref('')
let contractRetryTimer = null

const MAX_OPTIONS = 80 // 下拉里最多渲染的合约数，全部期货合约有几百个，输入关键字再缩小范围

// 合约的显示名：有独立中文名时显示“名称（代码）”，名称缺失或和代码相同时只显示代码。
// SimNow 返回的合约名称就是代码本身（852 个合约全部如此），直接拼会得到 “fu2701（fu2701）”；
// 换成会返回中文名的期货公司后，这里自动恢复成 “燃料油2701（fu2701）”。
const contractLabel = (name, symbol) => {
  const n = String(name ?? '').trim()
  const s = String(symbol ?? '').trim()
  if (!n || n.toLowerCase() === s.toLowerCase()) return s
  return `${n}（${s}）`
}

// ---- 常用合约：最近选择过的 N 个，存在 localStorage，下拉顶部的“常用”分组 ----
// 存的是 vt_symbol（如 ag2612.SHFE），最近的在前、去重。
// 各账号 / 调试模式共用一份：合约代码是公共的，换账号后不存在的合约会在显示时被过滤掉。
const RECENT_KEY = 'trading.recentContracts'
const RECENT_MAX = 3

const loadRecent = () => {
  try {
    const list = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
    return Array.isArray(list) ? list.filter((s) => typeof s === 'string').slice(0, RECENT_MAX) : []
  } catch (error) {
    return [] // 存储被清理 / 内容损坏：当作没有
  }
}

const recentSymbols = ref(loadRecent())

// 记录一次选择：放到最前面，去重，最多保留 RECENT_MAX 个
const recordRecent = (vtSymbol) => {
  if (!vtSymbol) return
  recentSymbols.value = [vtSymbol, ...recentSymbols.value.filter((s) => s !== vtSymbol)].slice(0, RECENT_MAX)
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(recentSymbols.value))
  } catch (error) {
    // 存储不可用（隐私模式 / 配额满）：本次会话内仍然有效，只是不会持久化
  }
}

// 下拉搜索关键字（空表示没有搜索）
const searchKeyword = ref('')

const matchKeyword = (c, kw) => !kw || c.symbol.toLowerCase().includes(kw) || c.name.toLowerCase().includes(kw)

// “常用”分组：只显示当前合约列表里还存在的，并且符合搜索关键字
const recentOptions = computed(() => {
  const kw = searchKeyword.value
  return recentSymbols.value
    .map((vt) => contracts.value.find((c) => c.vt_symbol === vt))
    .filter((c) => c && matchKeyword(c, kw))
})

// 下拉里实际渲染的分组。有常用时：常用 + 全部合约（去掉已在常用里的）；没有常用时只有一个不带标题的组
const contractGroups = computed(() => {
  const recentIds = new Set(recentOptions.value.map((c) => c.vt_symbol))
  const others = filteredContracts.value.filter((c) => !recentIds.has(c.vt_symbol))
  // 当前选中的合约必须在渲染列表里，否则输入框显示不出名称（会退化成 ag2612.SHFE 这样的原始值）：
  // 它可能被只显示前 80 条截掉、或被搜索关键字过滤掉（默认选中持仓第一条 / 点“平仓”都会遇到）
  // 搜索中不追加：用户搜 IF 就只该看到匹配项（追加会混进无关的合约，还会让“没有匹配的合约”提示出不来）；
  // 此时输入框上的名称由 el-select 缓存的已选项提供，不受影响
  const sel = selectedSymbol.value
  if (!searchKeyword.value && sel && !recentIds.has(sel) && !others.some((c) => c.vt_symbol === sel)) {
    const c = contracts.value.find((x) => x.vt_symbol === sel)
    if (c) others.unshift(c)
  }
  const groups = []
  if (recentOptions.value.length) groups.push({ key: 'recent-', label: '常用', items: recentOptions.value })
  if (others.length) {
    groups.push({ key: 'all-', label: recentOptions.value.length ? '全部合约' : '', items: others })
  }
  return groups
})

const filterContracts = (keyword = '') => {
  const kw = String(keyword).trim().toLowerCase()
  searchKeyword.value = kw
  const list = kw ? contracts.value.filter((c) => matchKeyword(c, kw)) : contracts.value
  filteredContracts.value = list.slice(0, MAX_OPTIONS)
}

const onContractDropdown = (visible) => {
  if (visible) filterContracts('')
}

const loadContracts = async () => {
  contractsLoading.value = true
  try {
    const res = await getContracts()
    if (res.success) {
      contracts.value = res.data
      filterContracts('')
      contractsLoading.value = false
      return
    }
  } catch (error) {
    // 后端暂时不可达，走下面的重试
  }
  // 合约信息正在加载（或暂时失败）：2 秒后重试，直到取到为止
  if (isQuantConnected.value) {
    contractRetryTimer = setTimeout(loadContracts, 2000)
  } else {
    contractsLoading.value = false
  }
}

// 当前选中合约的行情
const quote = ref(null)
const lastQuotePrice = ref(null)
const quoteTrend = ref('')
let quoteTimer = null

// 价格显示：最多保留 6 位小数并去掉末尾的 0，吞掉 7187.400000000001 这类浮点误差
const fmtPrice = (v) =>
  v === null || v === undefined || v === '' ? '--' : String(Number(Number(v).toFixed(6)))

const selectedContract = computed(() => contracts.value.find((c) => c.vt_symbol === selectedSymbol.value))
const priceTick = computed(() => selectedContract.value?.pricetick || 1)

const refreshQuote = async () => {
  if (!selectedSymbol.value) return
  const symbol = selectedSymbol.value
  try {
    const res = await getQuote(symbol)
    if (symbol !== selectedSymbol.value) return // 请求期间已切换合约，丢弃过期结果
    if (!res.success) return
    const q = res.data
    const prev = lastQuotePrice.value
    if (q.last_price !== null && prev !== null) {
      quoteTrend.value = q.last_price > prev ? 'up' : q.last_price < prev ? 'down' : quoteTrend.value
    }
    if (q.last_price !== null) lastQuotePrice.value = q.last_price
    quote.value = q
  } catch (error) {
    // 下次轮询再试
  }
}

const stopQuotePolling = () => {
  if (quoteTimer) {
    clearInterval(quoteTimer)
    quoteTimer = null
  }
}

const onContractChange = () => {
  stopQuotePolling()
  quote.value = null
  lastQuotePrice.value = null
  quoteTrend.value = ''
  priceInput.value = ''
  if (!selectedSymbol.value) return
  refreshQuote()
  quoteTimer = setInterval(refreshQuote, 1000)
}

// 用户在下拉里主动选了合约：记入“常用”，再走统一的切换逻辑。
// 点持仓“平仓”和默认选中也会切换合约，但不是用户在挑品种，所以不记入常用（它们直接调用 onContractChange）
const onContractPicked = () => {
  recordRecent(selectedSymbol.value)
  onContractChange()
}

// 默认选中的合约：持仓列表第一条 → 没有持仓用最近选择的 → 都没有就留空。
// 只在合约列表和持仓都加载完成后执行一次，并且用户已经自己选了就不动，
// 否则每 3 秒一次的持仓刷新会把用户的选择覆盖掉。断开重连后（数据被清空）会重新走一遍。
const defaultPicked = ref(false)
const positionsLoaded = ref(false)

const applyDefaultContract = () => {
  if (defaultPicked.value || selectedSymbol.value) return
  if (!contracts.value.length || !positionsLoaded.value) return // 数据还没齐，等下一次触发
  defaultPicked.value = true

  const exists = (vt) => contracts.value.some((c) => c.vt_symbol === vt)
  // 持仓里的合约不一定在合约列表里（例如已下市），找第一个存在的
  const fromPosition = positions.value.map((p) => p.vt_symbol).find(exists)
  const pick = fromPosition || recentSymbols.value.find(exists)
  if (!pick) return // 没有持仓也没有最近选择过：保持为空

  selectedSymbol.value = pick
  onContractChange()
}

// 限价 / 手数
const priceInput = ref('')
const volumeInput = ref(1)
const ordering = ref(false)

const fillLastPrice = () => {
  if (quote.value?.last_price) priceInput.value = quote.value.last_price
}

// 按合约最小变动价位调整价格；用四舍五入消除浮点误差（如 0.1 + 0.2）
const adjustPrice = (direction) => {
  const tick = priceTick.value
  let base = Number(priceInput.value)
  if (!Number.isFinite(base) || base <= 0) base = quote.value?.last_price || 0
  if (!base) return
  const next = Math.round((base + direction * tick) / tick) * tick
  if (next > 0) priceInput.value = Number(next.toFixed(6))
}

const adjustVolume = (direction) => {
  const next = (Number(volumeInput.value) || 0) + direction
  if (next >= 1) volumeInput.value = Math.floor(next)
}

const ACTION_TEXT = {
  open_long: '买多',
  open_short: '卖空',
  close_long: '平多',
  close_short: '平空'
}

// 限价下单：先在前端挡掉明显的错误，真正的校验以后端为准；下单前必须二次确认
const submitOrder = async (action) => {
  const contract = selectedContract.value
  if (!contract) {
    ElMessage.warning('请先选择合约')
    return
  }
  const price = Number(priceInput.value)
  const volume = Number(volumeInput.value)
  if (!Number.isFinite(price) || price <= 0) {
    ElMessage.warning('请输入有效的限价')
    return
  }
  if (!Number.isInteger(volume) || volume < 1) {
    ElMessage.warning('手数必须是正整数')
    return
  }

  try {
    await ElMessageBox.confirm(
      `${ACTION_TEXT[action]}　${contractLabel(contract.name, contract.symbol)}\n限价 ${price}　${volume} 手`,
      '确认下单',
      { confirmButtonText: '确认下单', cancelButtonText: '取消', type: 'warning', customStyle: { whiteSpace: 'pre-line' } }
    )
  } catch (error) {
    return // 用户取消
  }

  ordering.value = true
  try {
    const res = await placeOrder({ symbol: contract.vt_symbol, action, price, volume })
    if (res.success) {
      ElMessage.success(res.message || '委托已提交')
    } else {
      ElMessage.error(res.message || '下单失败')
    }
    refreshAll()
  } catch (error) {
    console.error('下单错误:', error)
    ElMessage.error('下单请求失败，请检查后端连接')
  } finally {
    ordering.value = false
  }
}

// 前端分页（后端每 3 秒返回全量，一天的委托 / 持仓 / 成交量级不大，不需要改接口）。
// 每页 5 条：面板高度由 Trading.css 的 --trade-panel-height 统一决定，刚好放得下表头 + 5 行 + 分页条。
// 当前委托、当前持仓、成交明细三个列表共用这一套逻辑，保证行为一致。
const PAGE_SIZE = 5

const usePaged = (list) => {
  const page = ref(1)
  const pageCount = computed(() => Math.max(1, Math.ceil(list.value.length / PAGE_SIZE)))
  const paged = computed(() => list.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

  // 每 3 秒轮询刷新会整体替换列表：停留在第几页就保持第几页，不要被强制跳回第一页；
  // 只有当前页超出了范围（比如列表缩短 / 被清空 / 断开重连）才退回到最后一页。
  watch(pageCount, (count) => {
    if (page.value > count) page.value = count
  })
  return { page, paged }
}

// 委托列表
const orders = ref([])
let ordersTimer = null
const { page: orderPage, paged: pagedOrders } = usePaged(orders)

const refreshOrders = async () => {
  try {
    const res = await getOrders()
    if (res.success) orders.value = res.data
  } catch (error) {
    // 下次轮询再试
  }
}

const orderStatusClass = (o) => {
  if (o.status === '全部成交') return 'done'
  if (o.status === '已拒绝') return 'rejected'
  if (o.status === '已撤销') return 'cancelled'
  return 'active'
}

const cancelOne = async (o) => {
  try {
    const res = await cancelOrder(o.vt_orderid)
    if (res.success) {
      ElMessage.success(res.message || '撤单成功')
    } else {
      ElMessage.error(res.message || '撤单失败')
    }
  } catch (error) {
    ElMessage.error('撤单请求失败，请检查后端连接')
  }
  refreshAll()
}

// 持仓 / 成交
const positions = ref([])
const trades = ref([])
const { page: positionPage, paged: pagedPositions } = usePaged(positions)
const { page: tradePage, paged: pagedTrades } = usePaged(trades)

const refreshPositions = async () => {
  try {
    const res = await getPositions()
    if (res.success) {
      positions.value = res.data
      positionsLoaded.value = true // 持仓第一次返回（哪怕是空列表）后，才能决定默认合约
    }
  } catch (error) {
    // 下次轮询再试
  }
}

// 合约列表和持仓都到齐后，决定默认选中的合约（只执行一次，见 applyDefaultContract）
watch([contracts, positionsLoaded], applyDefaultContract)

const refreshTrades = async () => {
  try {
    const res = await getTrades()
    if (res.success) trades.value = res.data
  } catch (error) {
    // 下次轮询再试
  }
}

// 一次刷新委托 / 持仓 / 成交（下单、撤单、反手后立刻调用，不用等 3 秒）
const refreshAll = () => {
  refreshOrders()
  refreshPositions()
  refreshTrades()
}

// 持仓行上的“平仓”：选中该合约，填入可平手数和对手价，由用户确认价格后再点上方的“平多 / 平空”。
// 对手价：平多是卖出，用买一价；平空是买入，用卖一价，更容易成交。
const useForClose = async (p) => {
  selectedSymbol.value = p.vt_symbol
  if (!filteredContracts.value.find((c) => c.vt_symbol === p.vt_symbol)) filterContracts(p.symbol)
  onContractChange()
  volumeInput.value = Math.max(1, Math.floor(p.available || p.volume))
  await refreshQuote()
  const q = quote.value
  const price = p.direction === '多' ? q?.bid_price : q?.ask_price
  priceInput.value = price || q?.last_price || ''
  ElMessage.info(
    `已选中 ${contractLabel(p.name, p.symbol)}，限价 ${priceInput.value || '待填'}、${volumeInput.value} 手；确认后点上方的「${p.direction === '多' ? '平多' : '平空'}」`
  )
}

// 反手：先平掉该持仓，平仓【全部成交】后才反向开同样手数。
// 平仓价取对手价（更容易成交），开仓价取反向的对手价；价格拿不到时不允许发起，避免盲目下单。
const submitReverse = async (p) => {
  if (!p.available || p.available < p.volume) {
    ElMessage.warning(`${contractLabel(p.name, p.symbol)} 有 ${p.volume - p.available} 手被挂单占用，请先撤销相关委托再反手`)
    return
  }
  // 反手要用最新盘口，先确保订阅并取到这个合约的行情
  let q = null
  try {
    const res = await getQuote(p.vt_symbol)
    if (res.success) q = res.data
  } catch (error) {
    // 走下面的“拿不到行情”提示
  }
  if (!q || !q.bid_price || !q.ask_price) {
    ElMessage.warning('暂时没有该合约的盘口行情，无法反手，请稍后再试（非交易时段没有行情）')
    return
  }
  // 多单反手：卖出平仓（用买一价）→ 卖出开空（用买一价）；空单反手：买入平仓（用卖一价）→ 买入开多（用卖一价）
  const price = p.direction === '多' ? q.bid_price : q.ask_price
  const toSide = p.direction === '多' ? '空' : '多'

  try {
    await ElMessageBox.confirm(
      `反手　${contractLabel(p.name, p.symbol)}\n` +
        `第 1 步：平 ${p.direction} ${p.volume} 手，限价 ${price}\n` +
        `第 2 步：开 ${toSide} ${p.volume} 手，限价 ${price}\n\n` +
        `注意：只有第 1 步【全部成交】后才会自动执行第 2 步。\n` +
        `如果第 1 步没有成交或被撤销，不会开反向仓。`,
      '确认反手',
      { confirmButtonText: '确认反手', cancelButtonText: '取消', type: 'warning', customStyle: { whiteSpace: 'pre-line' } }
    )
  } catch (error) {
    return // 用户取消
  }

  ordering.value = true
  try {
    const res = await startReverse({
      symbol: p.vt_symbol,
      fromSide: p.direction,
      closePrice: price,
      openPrice: price,
      volume: p.volume
    })
    if (res.success) {
      ElMessage.success(res.message || '反手已发起')
    } else {
      ElMessage.error(res.message || '反手失败')
    }
    refreshAll()
  } catch (error) {
    console.error('反手错误:', error)
    ElMessage.error('反手请求失败，请检查后端连接')
  } finally {
    ordering.value = false
  }
}

const startTradingPolling = () => {
  refreshAll()
  if (!ordersTimer) ordersTimer = setInterval(refreshAll, 3000)
  if (!contracts.value.length) loadContracts()
}

const stopTradingPolling = () => {
  stopQuotePolling()
  if (ordersTimer) {
    clearInterval(ordersTimer)
    ordersTimer = null
  }
  if (contractRetryTimer) {
    clearTimeout(contractRetryTimer)
    contractRetryTimer = null
  }
  // 断开后清掉上一个会话的数据，避免重新连接时看到旧的合约 / 委托 / 行情
  contracts.value = []
  filteredContracts.value = []
  contractsLoading.value = false
  selectedSymbol.value = ''
  defaultPicked.value = false // 重新连接后重新决定默认合约
  positionsLoaded.value = false
  quote.value = null
  orders.value = []
  orderPage.value = 1
  positions.value = []
  positionPage.value = 1
  trades.value = []
  tradePage.value = 1
}

// 弹窗
const showModal = ref(false)
const modalTitle = ref('')
const modalMessage = ref('')

// 退出登录
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

// 关闭弹窗
const closeModal = () => {
  showModal.value = false
}

// 生命周期
// 进入页面就开始保持连接：后端已有登录会话（登录页已用期货账号登录成功 / 调试模式的假数据）时自动拉取资金、
// 合约、委托、持仓；暂时没有会话（后端启动稍慢等）时静默重试，等会话就绪后自动接上
onMounted(() => {
  startAccountPolling()
})

onUnmounted(() => {
  disposed = true
  stopAccountPolling()
  stopTradingPolling()
})
</script>

<style scoped>
@import '@/styles/Trading.css';
</style>

<!-- 下拉面板通过 teleport 挂到 body 下，scoped / :deep 命中不了，需以非 scoped 方式引入 -->
<style>
@import '@/styles/TradingPopper.css';
</style>
