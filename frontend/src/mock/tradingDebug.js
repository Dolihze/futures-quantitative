/**
 * 调试模式（登录页「调试模式（跳过登录）」，broker === 'debug'）下交易页使用的假数据。
 *
 * 为什么放在前端：调试模式没有后端 CTP 会话，真实接口全部会失败；假数据只服务于前端界面调试，
 * 不应该混进 ctp_service.py 这类真实交易代码。只有 broker === 'debug' 时才会走到这里（见 api/trading.js），
 * 真实账号的数据流完全不受影响。
 *
 * 所有函数的返回值和真实接口一致：Promise<{ success, data?, message? }>（axios 拦截器已经解包 response.data），
 * 并且是「有状态」的：下单会新增委托 / 成交并改变持仓、撤单会改变状态、反手会先挂平仓单再自动反向开仓、
 * 行情每次读取会小幅跳动，这样界面上的按钮、分页、状态标签、浮动盈亏都能真实地动起来。
 */

const delay = (ms = 120) => new Promise((resolve) => setTimeout(resolve, ms))
const ok = (data, message) => ({ success: true, ...(data !== undefined ? { data } : {}), ...(message ? { message } : {}) })
const fail = (message) => ({ success: false, message })

// ---------------------------------------------------------------------------
// 合约（价格数据取自常见品种的大致价位）。
// 每个合约都给了和代码不同的中文名，下拉里统一显示成“名称（代码）”。
// 注意：真实 SimNow 返回的合约名称就是代码本身（页面上只显示代码），这里是为了调试“有中文名”时的界面刻意不同。
// ---------------------------------------------------------------------------
const SPECS = [
  ['ag2612', 'SHFE', '白银2612', 15, 1, 8050],
  ['ag2701', 'SHFE', '白银2701', 15, 1, 8090],
  ['au2612', 'SHFE', '黄金2612', 1000, 0.02, 760.5],
  ['cu2612', 'SHFE', '沪铜2612', 5, 10, 78200],
  ['al2612', 'SHFE', '沪铝2612', 5, 5, 20650],
  ['rb2701', 'SHFE', '螺纹钢2701', 10, 1, 3210],
  ['hc2701', 'SHFE', '热卷2701', 10, 1, 3340],
  ['fu2701', 'SHFE', '燃料油2701', 10, 1, 4013],
  ['sc2612', 'INE', '原油2612', 1000, 0.1, 512.3],
  ['i2701', 'DCE', '铁矿石2701', 100, 0.5, 812.5],
  ['m2701', 'DCE', '豆粕2701', 10, 1, 2980],
  ['p2701', 'DCE', '棕榈油2701', 10, 2, 8620],
  ['TA2701', 'CZCE', 'PTA2701', 5, 2, 5480],
  ['MA2701', 'CZCE', '甲醇2701', 10, 1, 2465],
  ['SR2701', 'CZCE', '白糖2701', 10, 1, 5890],
  ['IF2612', 'CFFEX', '沪深300股指2612', 300, 0.2, 4100.0],
  ['IC2612', 'CFFEX', '中证500股指2612', 200, 0.2, 6180.4],
  ['lc2701', 'GFEX', '碳酸锂2701', 1, 50, 120000]
].map(([symbol, exchange, name, size, pricetick, base]) => ({
  vt_symbol: `${symbol}.${exchange}`,
  symbol,
  exchange,
  name,
  size,
  pricetick,
  min_volume: 1,
  max_volume: 500,
  base
}))

const specOf = (vtSymbol) => SPECS.find((s) => s.vt_symbol === vtSymbol)

// ---------------------------------------------------------------------------
// 行情：在基准价上随机游走，同一合约的价格在多次读取之间连续变化
// ---------------------------------------------------------------------------
const lastPrice = {}
// 价格只在基准价上下 WANDER_TICKS 个最小变动价位内波动：既能看到涨跌色变化，
// 又不会漂远——调试时把限价设在“基准价 ± 几个 tick”，成交 / 挂单的结果是可预期的
const WANDER_TICKS = 5
const priceOf = (spec) => {
  const prev = lastPrice[spec.vt_symbol] ?? spec.base
  const step = [-1, 0, 0, 1][Math.floor(Math.random() * 4)] * spec.pricetick
  const lo = spec.base - WANDER_TICKS * spec.pricetick
  const hi = spec.base + WANDER_TICKS * spec.pricetick
  lastPrice[spec.vt_symbol] = Number(Math.min(hi, Math.max(lo, prev + step)).toFixed(6))
  return lastPrice[spec.vt_symbol]
}

const quoteOf = (spec) => {
  const last = priceOf(spec)
  const tick = spec.pricetick
  return {
    vt_symbol: spec.vt_symbol,
    symbol: spec.symbol,
    last_price: last,
    bid_price: Number((last - tick).toFixed(6)),
    ask_price: Number((last + tick).toFixed(6)),
    limit_up: Number((spec.base * 1.05).toFixed(2)),
    limit_down: Number((spec.base * 0.95).toFixed(2))
  }
}

// ---------------------------------------------------------------------------
// 时间 / 编号工具
// ---------------------------------------------------------------------------
const pad = (n) => String(n).padStart(2, '0')
const hms = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
const minutesAgo = (m) => hms(new Date(Date.now() - m * 60000))

let seq = 100
const nextId = () => ++seq

// ---------------------------------------------------------------------------
// 委托：覆盖所有状态。status 文案和后端 ctp_service._STATUS_TEXT 一致
// ---------------------------------------------------------------------------
const mkOrder = (symbol, direction, offset, price, volume, traded, status, minsAgo) => {
  const spec = SPECS.find((s) => s.symbol === symbol)
  const id = nextId()
  return {
    vt_orderid: `CTP.1_900_${id}`,
    vt_symbol: spec.vt_symbol,
    symbol,
    direction,
    offset,
    price,
    volume,
    traded,
    status,
    active: status === '未成交' || status === '部分成交' || status === '提交中',
    time: minutesAgo(minsAgo)
  }
}

// 最新的在前
let orders = [
  mkOrder('ag2612', '多', '开', 8048, 3, 0, '未成交', 1),
  mkOrder('rb2701', '空', '开', 3225, 5, 2, '部分成交', 3),
  mkOrder('cu2612', '多', '平', 78150, 1, 0, '未成交', 6),
  mkOrder('IF2612', '空', '开', 4102.4, 2, 2, '全部成交', 9),
  mkOrder('au2612', '多', '开', 761.0, 2, 2, '全部成交', 14),
  mkOrder('sc2612', '多', '开', 510.0, 1, 0, '已撤销', 18),
  mkOrder('i2701', '空', '开', 815.5, 4, 0, '已拒绝', 22),
  mkOrder('m2701', '多', '开', 2975, 6, 6, '全部成交', 31),
  mkOrder('TA2701', '空', '平', 5490, 3, 3, '全部成交', 47),
  mkOrder('ag2701', '多', '开', 8085, 2, 2, '全部成交', 58)
]

// ---------------------------------------------------------------------------
// 成交明细（最新的在前），编号形如 CTP.<成交号>，页面取最后一段显示
// ---------------------------------------------------------------------------
const mkTrade = (symbol, direction, offset, price, volume, minsAgo, orderIdx) => {
  const spec = SPECS.find((s) => s.symbol === symbol)
  return {
    vt_tradeid: `CTP.${10000000 + nextId()}`,
    vt_orderid: orders[orderIdx]?.vt_orderid || `CTP.1_900_${nextId()}`,
    vt_symbol: spec.vt_symbol,
    symbol,
    direction,
    offset,
    price,
    volume,
    time: minutesAgo(minsAgo)
  }
}

let trades = [
  mkTrade('rb2701', '空', '开', 3225, 2, 3, 1),
  mkTrade('IF2612', '空', '开', 4102.4, 2, 9, 3),
  mkTrade('au2612', '多', '开', 761.0, 1, 14, 4),
  mkTrade('au2612', '多', '开', 761.0, 1, 14, 4),
  mkTrade('m2701', '多', '开', 2975, 3, 31, 7),
  mkTrade('m2701', '多', '开', 2974, 3, 31, 7),
  mkTrade('TA2701', '空', '平', 5490, 2, 47, 8),
  mkTrade('TA2701', '空', '平', 5490, 1, 47, 8),
  mkTrade('ag2701', '多', '开', 8085, 1, 58, 9),
  mkTrade('ag2701', '多', '开', 8085, 1, 58, 9),
  mkTrade('ag2612', '多', '开', 8031, 5, 95, -1) // 更早的成交，对应的委托不在当前列表里
]

// ---------------------------------------------------------------------------
// 持仓：价格 / 方向 / 今昨仓 / 被挂单冻结（frozen > 0 时前端会拦截反手）各种情况都有
// ---------------------------------------------------------------------------
// [symbol, 方向, 总手数, 昨仓, 开仓均价, 冻结手数]
const POSITION_SEEDS = [
  ['ag2612', '多', 5, 3, 8031, 0],
  ['ag2612', '空', 2, 0, 8070, 0],
  ['rb2701', '空', 2, 0, 3225, 0],
  ['IF2612', '空', 2, 0, 4102.4, 0],
  ['au2612', '多', 2, 0, 761.0, 0],
  ['cu2612', '多', 3, 3, 78090, 1], // 有 1 手被挂单占用
  ['m2701', '多', 6, 0, 2974.5, 0],
  ['sc2612', '空', 1, 1, 515.8, 0],
  ['lc2701', '多', 4, 2, 119500, 0]
]

let positionBook = POSITION_SEEDS.map(([symbol, direction, volume, yd, price, frozen]) => ({
  symbol,
  direction,
  volume,
  yd_volume: yd,
  price,
  frozen
}))

const positionsView = () =>
  positionBook
    .filter((p) => p.volume > 0)
    .map((p) => {
      const spec = SPECS.find((s) => s.symbol === p.symbol)
      const last = priceOf(spec)
      const sign = p.direction === '多' ? 1 : -1
      const yd = Math.min(p.yd_volume, p.volume)
      return {
        vt_symbol: spec.vt_symbol,
        symbol: p.symbol,
        name: spec.name,
        exchange: spec.exchange,
        direction: p.direction,
        volume: p.volume,
        yd_volume: yd,
        td_volume: p.volume - yd,
        frozen: p.frozen,
        available: Math.max(p.volume - p.frozen, 0),
        price: p.price,
        last_price: last,
        pnl: (last - p.price) * p.volume * spec.size * sign,
        pnl_source: 'live'
      }
    })
    .sort((a, b) => (a.symbol === b.symbol ? a.direction.localeCompare(b.direction) : a.symbol.localeCompare(b.symbol)))

// ---------------------------------------------------------------------------
// 进行中的反手：页面不再展示反手任务，这里只用来拦截“同一持仓重复发起反手”
// （和后端一致：同合约同方向已有反手在等平仓成交时不允许再发）。
// ---------------------------------------------------------------------------
const pendingReverse = new Set()
const reverseKey = (vtSymbol, side) => `${vtSymbol}|${side}`

// ---------------------------------------------------------------------------
// 账户：权益 / 可用 / 持仓盈亏都由当前持仓实时算出，下单后可用资金会变化
// ---------------------------------------------------------------------------
const BALANCE = 1286450.0
let usedMargin = 238600.0

const snapshot = () => {
  const view = positionsView()
  const profit = view.reduce((sum, p) => sum + p.pnl, 0)
  return {
    broker: 'debug',
    username: '管理员',
    account: {
      account: 'DEBUG-000001',
      balance: BALANCE + profit,
      available: BALANCE + profit - usedMargin,
      frozen: 0
    },
    positions: view,
    position_profit: profit
  }
}

// ---------------------------------------------------------------------------
// 对外接口（和 @/api 同名同签名）
// ---------------------------------------------------------------------------
export async function quantLogin() {
  await delay(300)
  return ok(snapshot(), '连接成功')
}

export async function getAccount() {
  await delay()
  return ok(snapshot())
}

export async function getContracts() {
  await delay(400) // 稍微有点延迟，能看到“合约加载中…”
  return ok(
    SPECS.map(({ base, ...c }) => c)
  )
}

export async function getQuote(symbol) {
  await delay(60)
  const spec = specOf(symbol)
  return spec ? ok(quoteOf(spec)) : fail(`合约不存在：${symbol}`)
}

export async function getOrders() {
  await delay()
  return ok(orders.map((o) => ({ ...o })))
}

export async function getPositions() {
  await delay()
  return ok(positionsView())
}

export async function getTrades() {
  await delay()
  return ok(trades.map((t) => ({ ...t })))
}

// 限价下单：价格 >= 涨停价模拟柜台拒单；其余按 “买入价 >= 卖一价 / 卖出价 <= 买一价” 立即成交，否则挂单
export async function placeOrder({ symbol, action, price, volume }) {
  await delay(200)
  const spec = specOf(symbol)
  if (!spec) return fail(`合约不存在：${symbol}`)
  if (!Number.isFinite(price) || price <= 0) return fail('请输入有效的限价')
  if (!Number.isInteger(volume) || volume < 1) return fail('手数必须是正整数')

  // 委托方向：买多（开多）、平空（买入平仓）是“买”→ 多；卖空（开空）、平多（卖出平仓）是“卖”→ 空，和柜台一致
  const direction = action === 'open_long' || action === 'close_short' ? '多' : '空'
  const offset = action.startsWith('open') ? '开' : '平'
  const q = quoteOf(spec)

  if (price > q.limit_up || price < q.limit_down) {
    return fail(`价格超出涨跌停范围（${q.limit_down} ~ ${q.limit_up}）`)
  }

  // 平仓：必须有足够的可平持仓（平多卖出 → 持有多单；平空买入 → 持有空单）
  if (offset === '平') {
    const holdSide = action === 'close_long' ? '多' : '空'
    const pos = positionBook.find((p) => p.symbol === spec.symbol && p.direction === holdSide)
    const available = pos ? pos.volume - pos.frozen : 0
    if (available < volume) return fail(`可平${holdSide}仓不足（可平 ${available} 手，委托 ${volume} 手）`)
  }

  const crosses = direction === '多' ? price >= q.ask_price : price <= q.bid_price
  const order = recordOrder(spec, action, price, volume, crosses)
  return ok({ vt_orderids: [order.vt_orderid] }, crosses ? '委托已成交' : '委托已提交')
}

// 新增一条委托；filled 为真时同时生成成交明细并更新持仓。限价下单和反手共用，保证三张表数据自洽
function recordOrder(spec, action, price, volume, filled) {
  const order = {
    vt_orderid: `CTP.1_900_${nextId()}`,
    vt_symbol: spec.vt_symbol,
    symbol: spec.symbol,
    // 买多（开多）、平空（买入平仓）是“买”→ 多；卖空（开空）、平多（卖出平仓）是“卖”→ 空，和柜台一致
    direction: action === 'open_long' || action === 'close_short' ? '多' : '空',
    offset: action.startsWith('open') ? '开' : '平',
    price,
    volume,
    traded: filled ? volume : 0,
    status: filled ? '全部成交' : '未成交',
    active: !filled,
    time: hms(new Date())
  }
  orders = [order, ...orders]

  if (filled) {
    trades = [
      {
        vt_tradeid: `CTP.${10000000 + nextId()}`,
        vt_orderid: order.vt_orderid,
        vt_symbol: spec.vt_symbol,
        symbol: spec.symbol,
        direction: order.direction,
        offset: order.offset,
        price,
        volume,
        time: order.time
      },
      ...trades
    ]
    applyFill(spec, action, price, volume)
  }
  return order
}

// 成交后更新持仓簿
function applyFill(spec, action, price, volume) {
  if (action.startsWith('open')) {
    const side = action === 'open_long' ? '多' : '空'
    let pos = positionBook.find((p) => p.symbol === spec.symbol && p.direction === side)
    if (!pos) {
      pos = { symbol: spec.symbol, direction: side, volume: 0, yd_volume: 0, price: 0, frozen: 0 }
      positionBook.push(pos)
    }
    pos.price = (pos.price * pos.volume + price * volume) / (pos.volume + volume)
    pos.volume += volume
    usedMargin += price * spec.size * volume * 0.1
  } else {
    const side = action === 'close_long' ? '多' : '空'
    const pos = positionBook.find((p) => p.symbol === spec.symbol && p.direction === side)
    if (pos) {
      pos.volume -= volume
      pos.yd_volume = Math.min(pos.yd_volume, pos.volume)
      usedMargin = Math.max(0, usedMargin - price * spec.size * volume * 0.1)
    }
  }
}

export async function cancelOrder(orderId) {
  await delay(150)
  const o = orders.find((x) => x.vt_orderid === orderId)
  if (!o) return fail('委托不存在')
  if (!o.active) return fail(`该委托状态为「${o.status}」，无法撤销`)
  o.status = '已撤销'
  o.active = false
  return ok(undefined, '撤单成功')
}

// 反手：和后端一样，要求可平手数 == 持仓手数，且同一持仓不能重复发起。
// 平仓委托立即发出（挂单），约 4 秒后“平仓成交”，随后自动反向开仓成交；
// 这期间委托 / 成交 / 持仓三张表会依次变化，方便调试界面刷新。
export async function startReverse({ symbol, fromSide, closePrice, openPrice, volume }) {
  await delay(250)
  const spec = specOf(symbol)
  if (!spec) return fail(`合约不存在：${symbol}`)
  const pos = positionBook.find((p) => p.symbol === spec.symbol && p.direction === fromSide)
  if (!pos || pos.volume < volume) return fail('持仓不足，无法反手')
  if (pos.volume - pos.frozen < volume) return fail('有持仓被挂单占用，请先撤销相关委托再反手')
  const key = reverseKey(symbol, fromSide)
  if (pendingReverse.has(key)) return fail('该合约已有一笔反手在等待平仓成交，请先等待成交或取消')

  const closeAction = fromSide === '多' ? 'close_long' : 'close_short'
  const openAction = fromSide === '多' ? 'open_short' : 'open_long'
  const closeOrder = recordOrder(spec, closeAction, closePrice, volume, false) // 先挂出平仓单
  pendingReverse.add(key)

  setTimeout(() => {
    pendingReverse.delete(key)
    if (!closeOrder.active) return // 平仓单期间被用户撤了：不再开反向仓
    // 平仓单成交：补成交明细、更新持仓
    closeOrder.traded = closeOrder.volume
    closeOrder.status = '全部成交'
    closeOrder.active = false
    trades = [
      {
        vt_tradeid: `CTP.${10000000 + nextId()}`,
        vt_orderid: closeOrder.vt_orderid,
        vt_symbol: spec.vt_symbol,
        symbol: spec.symbol,
        direction: closeOrder.direction,
        offset: closeOrder.offset,
        price: closeOrder.price,
        volume,
        time: hms(new Date())
      },
      ...trades
    ]
    applyFill(spec, closeAction, closeOrder.price, volume)
    // 然后反向开仓并成交
    recordOrder(spec, openAction, openPrice, volume, true)
  }, 4000)

  return ok(undefined, '反手已发起：先平仓，全部成交后自动反向开仓')
}
