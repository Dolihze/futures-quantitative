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
        <UserMenu />
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
            <!-- 第一块：左侧 3 个下拉框（合约 / 限价 / 手数），右侧 5 项信息（最新 / 买一 / 卖一 / 可开仓 / 占用保证金） -->
            <div class="order-form">
              <div class="order-fields">
                <!-- 合约 -->
                <div class="input-group contract-group">
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

                <!-- 价格：数字框，左减右加，步长为合约最小变动价位。
                     点击数字框弹出“最新价 / 对手价 / 市价”三个选项：选中后数字框显示这个文字（下单时再按方向换算成具体价格），
                     手动输入数字或点 −/+ 则回到“指定价格”。 -->
                <div class="input-group">
                  <el-popover
                    :visible="pricePopoverVisible"
                    placement="bottom"
                    :width="'auto'"
                    :show-arrow="true"
                    :offset="5"
                    :teleported="true"
                    popper-class="price-mode-popper"
                  >
                    <template #reference>
                      <div
                        class="price-field"
                        :class="{ 'is-mode': priceMode !== 'fixed' }"
                        v-click-outside="closePricePopover"
                        @click="onPriceFieldClick"
                      >
                        <el-input-number
                          v-model="priceInput"
                          :step="priceTick"
                          :min="0"
                          :precision="pricePrecision"
                          :value-on-clear="null"
                          placeholder="请输入价格"
                          class="trade-number"
                          @change="onPriceChange"
                        />
                        <!-- 非“指定价格”模式：盖在输入区上显示模式名称，不挡住两侧的 −/+ -->
                        <div v-if="priceMode !== 'fixed'" class="price-mode-label">{{ PRICE_MODE_TEXT[priceMode] }}</div>
                      </div>
                    </template>
                    <div class="price-mode-options" ref="priceOptionsRef">
                      <button
                        v-for="m in PRICE_MODES"
                        :key="m.value"
                        type="button"
                        class="price-mode-btn"
                        :class="{ active: priceMode === m.value }"
                        @click="pickPriceMode(m.value)"
                      >{{ m.label }}</button>
                    </div>
                  </el-popover>
                </div>
                <!-- 手数：数字框，左减右加，正整数 -->
                <div class="input-group">
                  <el-input-number
                    v-model="volumeInput"
                    :min="1"
                    :step="1"
                    :precision="0"
                    step-strictly
                    :value-on-clear="1"
                    class="trade-number"
                    @change="onVolumeChange"
                  />
                </div>
              </div>

              <!-- 右侧信息区：5 项固定结构，没有数据时显示 “--”，布局不跳动 -->
              <div class="order-info">
                <div class="info-row">
                  <span class="info-label">最新</span>
                  <b class="info-val" :class="quote ? quoteTrend : ''">{{ fmtPrice(quote?.last_price) }}</b>
                </div>
                <div class="info-row">
                  <span class="info-label">买一</span>
                  <b class="info-val up-text">{{ fmtPrice(quote?.bid_price) }}</b>
                </div>
                <div class="info-row">
                  <span class="info-label">卖一</span>
                  <b class="info-val down-text">{{ fmtPrice(quote?.ask_price) }}</b>
                </div>
                <div class="info-row">
                  <span class="info-label">可开仓</span>
                  <b class="info-val">{{ maxOpenVolume === null ? '--' : maxOpenVolume + ' 手' }}</b>
                </div>
                <div class="info-row">
                  <span class="info-label">占用保证金</span>
                  <b class="info-val">{{ marginUsed === null ? '--' : fmtMoney(marginUsed) + ' 元' }}</b>
                </div>
              </div>
            </div>

            <!-- 第三行：交易操作（均为限价单；按钮里小字是这个操作最多能做几手） -->
            <div class="trading-row">
              <button class="trading-btn long" :disabled="ordering" @click="submitOrder('open_long')">
                <span class="btn-text">买多</span>
                <span class="btn-limit">{{ fmtLimit(maxOpenVolume) }}</span>
              </button>
              <button class="trading-btn short" :disabled="ordering" @click="submitOrder('open_short')">
                <span class="btn-text">卖空</span>
                <span class="btn-limit">{{ fmtLimit(maxOpenVolume) }}</span>
              </button>
              <button class="trading-btn close" :disabled="ordering" @click="submitOrder('close_long')">
                <span class="btn-text">平多</span>
                <span class="btn-limit">{{ fmtLimit(maxCloseLong) }}</span>
              </button>
              <button class="trading-btn close" :disabled="ordering" @click="submitOrder('close_short')">
                <span class="btn-text">平空</span>
                <span class="btn-limit">{{ fmtLimit(maxCloseShort) }}</span>
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
                    <th class="num">持仓市值</th>
                    <th class="num">开仓均价</th>
                    <th class="num">盈利价差</th>
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
                    <td class="num">{{ fmtPositionValue(p) }}</td>
                    <td class="num">{{ fmtPrice(p.price ? Number(p.price.toFixed(2)) : null) }}</td>
                    <td class="num" :class="priceDiffClass(p)">{{ fmtPriceDiff(p) }}</td>
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
import { ElMessage, ElMessageBox, ClickOutside as vClickOutside } from 'element-plus'
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
    syncPriceInput()
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
  priceInput.value = null
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

// 限价 / 手数（都是可输入的下拉框：下拉里给常用选项，也可以直接键入任意值）
const priceInput = ref(null)
const volumeInput = ref(1)
const ordering = ref(false)

// 限价价格的小数位：由合约最小变动价位推出（0.02 → 2 位，0.2 → 1 位，1 → 0 位），保证 +/- 步进不出浮点误差
const pricePrecision = computed(() => {
  const s = String(priceTick.value)
  const dot = s.indexOf('.')
  return dot < 0 ? 0 : Math.min(6, s.length - dot - 1)
})

// ---- 价格模式 ----
// fixed = 指定价格（数字框里的数字）；last = 最新价；counter = 对手价；market = 市价。
// 后端只收限价单，所以后三种都在下单那一刻按行情换算成具体价格，再作为限价发出：
//   最新价：最新成交价
//   对手价：买入（买多 / 平空）用卖一，卖出（卖空 / 平多）用买一，挂在对手盘上，更容易成交
//   市价：期货交易所（尤其是上期所 / 能源中心）的限价单不支持真正的市价单，
//         这里用涨停价（买入）/ 跌停价（卖出）的限价单模拟，价格穿过对手盘，等同市价成交
// 选了后三种之一，数字框显示模式名称；手动输入数字或点 −/+ 就回到指定价格。
const PRICE_MODES = [
  { value: 'last', label: '最新价' },
  { value: 'counter', label: '对手价' },
  { value: 'market', label: '市价' }
]
const PRICE_MODE_TEXT = { last: '最新价', counter: '对手价', market: '市价' }
const priceMode = ref('fixed')
const pricePopoverVisible = ref(false)
const priceOptionsRef = ref(null)

// 让数字框背后的数字跟着最新价走：
//   最新价 / 对手价 / 市价三种模式：数字框显示的是模式名，背后的 priceInput 持续同步为最新价，
//     这样点 −/+ 时是在“此刻的最新价”上加减一个最小变动价位，而不是在很久以前的旧价格上加减。
//   指定价格模式：数字是用户自己定的，不动；只在还是空的时候（刚选了合约）用最新价预填一次。
// 注意：priceInput 在非指定价格模式下【只是 −/+ 的起点，不参与下单】。
// 下单价格由 resolvePrice 按模式取：对手价取买一 / 卖一，市价取涨 / 跌停价，最新价取最新价，
// 绝不会用 priceInput（最新价）去顶替对手价 / 市价，避免本该挂在对手盘上的单子因为价格不够激进而不成交。
// 程序给 v-model 赋值不会触发 el-input-number 的 change（只有用户输入 / 点 −、+ 才会），所以这里不会误把模式切回指定价格。
const syncPriceInput = () => {
  const last = quote.value?.last_price
  if (!last) return
  if (priceMode.value === 'fixed') {
    if (priceInput.value === null) priceInput.value = last
  } else {
    priceInput.value = last
  }
}

const pickPriceMode = (mode) => {
  priceMode.value = mode
  pricePopoverVisible.value = false
  syncPriceInput() // 切换的瞬间就对齐到最新价，不用等下一次行情刷新
}

// 只有点在中间输入区（不是左右的 −/+ 按钮）才弹出选项
const onPriceFieldClick = (e) => {
  if (e.target.closest('.el-input-number__decrease, .el-input-number__increase')) {
    pricePopoverVisible.value = false
    return
  }
  pricePopoverVisible.value = true
}

// 点在价格框和弹层之外：关闭弹层。弹层 teleport 到 body 里，要把它也算作“里面”
const closePricePopover = (e) => {
  if (priceOptionsRef.value && priceOptionsRef.value.contains(e.target)) return
  pricePopoverVisible.value = false
}

// 买入方向：买多、平空；其余是卖出方向
const isBuyAction = (action) => action === 'open_long' || action === 'close_short'

// 按价格模式 + 操作方向算出这一单要发的限价；行情缺失时返回 null
const resolvePrice = (action) => {
  const q = quote.value
  if (priceMode.value === 'fixed') {
    const n = Number(priceInput.value)
    return Number.isFinite(n) && n > 0 ? n : null
  }
  if (!q) return null
  const buy = isBuyAction(action)
  let price = null
  if (priceMode.value === 'last') price = q.last_price
  else if (priceMode.value === 'counter') price = buy ? q.ask_price : q.bid_price
  else if (priceMode.value === 'market') price = buy ? q.limit_up : q.limit_down
  return price || null
}

// 手动改数字（输入 / 点 −、+）：回到指定价格。
// 非指定价格模式下 priceInput 一直跟着最新价（见 syncPriceInput），所以点 −/+ 就是“最新价 ± 一个最小变动价位”。
// 选择模式、行情刷新给 priceInput 赋值都不会触发 change，所以不会误触发。
const onPriceChange = (val) => {
  if (val === undefined) priceInput.value = null
  if (priceMode.value !== 'fixed') {
    priceMode.value = 'fixed'
    // 兜底：万一此刻 priceInput 为空（还没有行情），用最新价起步
    if (!priceInput.value && quote.value?.last_price) priceInput.value = quote.value.last_price
  }
}

const onVolumeChange = (val) => {
  if (!Number.isInteger(val) || val < 1) volumeInput.value = 1
}
// ---- 可开仓手数 / 占用保证金（前端估算）----
// 后端目前没有提供合约保证金率，这里统一按 10% 估算（调试模式的假数据也是这个比例）。
// 以后后端返回真实保证金率后，只需要把这里换成合约自带的值。
const MARGIN_RATE = 0.1

// 每手保证金 = 价格 × 合约乘数 × 保证金率；价格优先用输入的限价，没有就用最新价
const marginPerLot = computed(() => {
  const c = selectedContract.value
  const price = (priceMode.value === 'fixed' ? Number(priceInput.value) : 0) || quote.value?.last_price
  if (!c || !price || !c.size) return null
  return price * c.size * MARGIN_RATE
})

const availableFunds = computed(() => Number(String(accountInfo.available).replace(/,/g, '')) || 0)

// 可开仓手数 = 可用资金 ÷ 每手保证金，向下取整
const maxOpenVolume = computed(() => {
  if (marginPerLot.value === null) return null
  return Math.max(0, Math.floor(availableFunds.value / marginPerLot.value))
})

// 占用保证金 = 每手保证金 × 手数
const marginUsed = computed(() => {
  const vol = Number(volumeInput.value)
  if (marginPerLot.value === null || !Number.isFinite(vol) || vol < 1) return null
  return marginPerLot.value * vol
})

// 持仓行的持仓市值 = 最新价 × 合约乘数 × 持仓手数：这笔仓位按现价值多少钱，不带方向（空头也是正数，方向看“方向”列）。
// 最新价每秒跟着行情变，所以和浮动盈亏同步波动（持仓市值 − 开仓成本 = 浮动盈亏）。
// 合约乘数来自合约列表；持仓的合约不在列表里（例如已下市）、或拿不到最新价（行情还没推送）时算不出来，返回 null，表格显示 --。
// 不拿开仓均价顶替最新价：那样会显示一个看起来像实时、其实是过期的数字。
const positionValue = (p) => {
  const c = contracts.value.find((x) => x.vt_symbol === p.vt_symbol)
  if (!c || !c.size || !p.last_price || !p.volume) return null
  return p.last_price * c.size * p.volume
}
const fmtPositionValue = (p) => {
  const v = positionValue(p)
  return v === null ? '--' : fmtMoney(v)
}
// 持仓行的盈利价差 = 每手赚（亏）了多少个价格点：多头 = 最新价 − 开仓均价，空头 = 开仓均价 − 最新价。
// 盈利为正、亏损为负，和浮动盈亏同号（浮动盈亏 = 盈利价差 × 合约乘数 × 持仓手数）。
// 拿不到最新价或开仓均价时返回 null，表格显示 --。
const priceDiff = (p) => {
  if (!p.last_price || !p.price) return null
  return p.direction === '多' ? p.last_price - p.price : p.price - p.last_price
}
// 带正负号显示：盈利前面加 +，亏损自带 −；fmtPrice 负责吞掉浮点误差（如 760.5600000000001）
const fmtPriceDiff = (p) => {
  const d = priceDiff(p)
  if (d === null) return '--'
  const s = fmtPrice(d)
  return d > 0 ? '+' + s : s
}
// 颜色和浮动盈亏一致：盈利红、亏损绿、持平不变色
const priceDiffClass = (p) => {
  const d = priceDiff(p)
  return d > 0 ? 'up-text' : d < 0 ? 'down-text' : ''
}

// 当前合约的多头 / 空头可平手数（持仓里的 available：已扣掉被挂单冻结的部分）
const closableOf = (direction) => {
  const sym = selectedSymbol.value
  if (!sym) return null
  const p = positions.value.find((x) => x.vt_symbol === sym && x.direction === direction)
  return p ? Number(p.available) || 0 : 0
}
const maxCloseLong = computed(() => closableOf('多'))
const maxCloseShort = computed(() => closableOf('空'))

// 按钮里的小字 ≤n；还没选合约（或开仓手数算不出来）时显示 ≤--
const fmtLimit = (n) => `≤${n === null || n === undefined ? '--' : n}`

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
  const price = resolvePrice(action)
  const volume = Number(volumeInput.value)
  if (price === null) {
    ElMessage.warning(priceMode.value === 'fixed' ? '请输入有效的价格' : `暂时没有该合约的行情，无法按${PRICE_MODE_TEXT[priceMode.value]}下单`)
    return
  }
  if (!Number.isInteger(volume) || volume < 1) {
    ElMessage.warning('手数必须是正整数')
    return
  }

  try {
    await ElMessageBox.confirm(
      `${ACTION_TEXT[action]}　${contractLabel(contract.name, contract.symbol)}\n${priceMode.value === 'fixed' ? '限价' : PRICE_MODE_TEXT[priceMode.value] + '（限价单）'} ${price}　${volume} 手`,
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
  priceMode.value = 'fixed' // 平仓入口会填入对手价这个具体数字，用指定价格显示
  if (!filteredContracts.value.find((c) => c.vt_symbol === p.vt_symbol)) filterContracts(p.symbol)
  onContractChange()
  volumeInput.value = Math.max(1, Math.floor(p.available || p.volume))
  await refreshQuote()
  const q = quote.value
  const price = p.direction === '多' ? q?.bid_price : q?.ask_price
  priceInput.value = price || q?.last_price || null
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
