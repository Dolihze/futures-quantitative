<template>
  <div class="kline-view">
    <!-- 黄色提示（可关闭）；品种由页面右上角的下拉框选择。
         key 绑定提示内容：换了一条新提示时组件重建，之前被关掉的提示不会把新提示一起吞掉 -->
    <el-alert
      v-if="notice"
      :key="notice"
      class="kline-notice"
      type="warning"
      :title="notice"
      show-icon
      @close="notice = ''"
    />

    <div class="kline-body">
      <div ref="chartRef" class="kline-chart"></div>

      <!-- 鼠标所在那根 K 线的信息，固定显示在图表右上角（不跟随鼠标）。
           订单（开仓点、连线、平仓点）的提示框仍然是 ECharts 自带的、跟随鼠标的那种 -->
      <div v-if="hoverBar" class="kline-info">
        <div class="kline-info-time">{{ hoverBar.time }}</div>
        <div>开 {{ hoverBar.open }} · 高 {{ hoverBar.high }} · 低 {{ hoverBar.low }} · 收 {{ hoverBar.close }}</div>
        <div class="kline-info-vol">成交量 {{ hoverBar.volume }}</div>
      </div>

      <div v-if="!days.length" class="chart-empty">
        <div class="empty-icon">🕯️</div>
        <div class="empty-title">还没有数据</div>
        <div class="empty-desc">先在左侧导入交易记录</div>
      </div>
      <div v-else-if="!loading && !symbols.length" class="chart-empty">
        <div class="empty-icon">🔍</div>
        <div class="empty-title">{{ day }} 没有成交记录</div>
        <div class="empty-desc">请调整左侧的时间范围，或在右上角换一个品种</div>
      </div>
      <div v-else-if="!loading && klineUnavailable" class="chart-empty">
        <div class="empty-icon">🕯️</div>
        <div class="empty-title">取不到这一天的 1 分钟 K 线</div>
        <div class="empty-desc">{{ klineUnavailable }}</div>
      </div>
      <div v-if="loading" class="chart-loading">
        <div class="loading-spinner"></div>
        <div class="loading-text">正在加载 K 线和交易...</div>
      </div>
    </div>

    <div v-if="hiddenTrades.length" class="kline-hidden">
      <div class="kline-hidden-title">以下交易有一端不在当天的 K 线上，只标出了当天的那一端：</div>
      <div v-for="(t, i) in hiddenTrades" :key="i" class="kline-hidden-item">{{ t }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { getReviewDayTrades, getReviewDayKline } from '@/api'

const props = defineProps({
  reviewId: { type: String, default: '' },
  products: { type: Array, default: () => [] },   // 页面右上角选中的品种（回放页只看这个品种），空 = 全部
  days: { type: Array, default: () => [] },       // 文件里有成交的全部交易日（升序）
  active: { type: Boolean, default: true }        // 当前 Tab 是否可见；隐藏时筛选变化不立刻请求，等切回来再刷新
})

const chartRef = ref(null)
let chart = null
// 当前画在图上的开仓点 / 平仓点、连线的原始数据（含订单号 info.n）。悬停高亮时据此改 active 维
let orderPoints = []
let orderLinks = []

const day = ref('')
const symbol = ref('')
const symbols = ref([])          // [{ symbol, trades }]
const loading = ref(false)
const notice = ref('')
const klineUnavailable = ref('')
const hiddenTrades = ref([])
const kline = ref([])            // 当前合约当天的 K 线
const hoverIndex = ref(-1)       // 鼠标所在的 K 线序号，-1 表示鼠标不在 K 线区域，右上角的信息面板隐藏
const hoverBar = computed(() => kline.value[hoverIndex.value] || null)
const period = ref(1)            // 实际取到的 K 线周期（分钟）

const currentTrades = computed(() => symbols.value.find((s) => s.symbol === symbol.value)?.trades || [])

// ---------- 数据加载 ----------
// 防止快速切换日期/合约时，旧请求的结果覆盖新请求
let seq = 0

async function loadDay() {
  if (!props.reviewId || !day.value) return
  const my = ++seq
  loading.value = true
  notice.value = ''
  klineUnavailable.value = ''
  try {
    const res = await getReviewDayTrades({ reviewId: props.reviewId, day: day.value, products: props.products.join(',') })
    if (my !== seq) return
    symbols.value = res.symbols || []
    // 合约由右上角选的品种决定：同一品种当天有多个合约时，取成交笔数最多的那个（并列取第一个，按合约代码排序）
    symbol.value = symbols.value.reduce((best, s) => (!best || s.trades.length > best.trades.length ? s : best), null)?.symbol || ''
    if (!symbol.value) {
      kline.value = []
      renderChart()
      return
    }
    await loadKline(my)
  } catch (e) {
    if (my !== seq) return
    notice.value = e?.response?.data?.message || '加载交易失败，请重试'
    symbols.value = []
    kline.value = []
    renderChart()
  } finally {
    if (my === seq) loading.value = false
  }
}

async function loadKline(my) {
  try {
    const res = await getReviewDayKline({ symbol: symbol.value, day: day.value })
    if (my !== seq) return
    if (!res.available) {
      kline.value = []
      klineUnavailable.value = res.message || '没有 K 线数据'
    } else {
      kline.value = res.data
      period.value = res.period || 1
      // 新浪的 K 线接口没有日期参数，每个周期只给最近 1023 根：1 分钟线只有最近约 3 个交易日。
      // 取不到 1 分钟线时后端自动换成更长的周期，这里要告诉用户现在看到的不是 1 分钟线。
      const msgs = []
      if (period.value !== 1) {
        msgs.push(`这一天的 1 分钟 K 线已经取不到（新浪只保留最近约 3 个交易日），当前显示的是 ${period.value} 分钟 K 线，成交点仍按真实成交时间标在所在的那根 K 线上`)
      }
      if (res.partial) msgs.push('这一天的开头部分可能缺失')
      notice.value = msgs.join('；')
    }
  } catch (e) {
    if (my !== seq) return
    kline.value = []
    klineUnavailable.value = e?.response?.data?.message || '获取 K 线失败，请检查网络后重试'
  }
  renderChart()
}

// ---------- 绘图 ----------
// 和 ECharts 蜡烛影线同一条规则：线宽 1px 时，把 x 对齐到“像素中心”（整数 + 0.5）。
// 照抄 zrender 的 subPixelOptimize（它没有从 echarts 公开导出）：
//   doubled = round(x * 2)；doubled + round(线宽) 是偶数就用 doubled / 2，否则往负方向取（doubled - 1）/ 2
const crispX = (x) => {
  const doubled = Math.round(x * 2)
  return (doubled + 1) % 2 === 0 ? doubled / 2 : (doubled - 1) / 2
}

const pad2 = (n) => String(n).padStart(2, '0')
const toMs = (s) => new Date(s.replace(' ', 'T')).getTime()

// 红涨绿跌（和项目其它页面一致）
// 平时的红绿（K 线边框、订单的点和连线）用稍深的一档；悬停时订单（点和连线）换成更鲜艳的一档。
// 悬停色不能靠“提亮”：红色提亮会掉成粉色（试过 #f87171，已经不像红色了），所以改用饱和度高的纯红 / 纯绿，
// 比平时的颜色更亮更艳，但仍然是红和绿
const UP = '#dc2626'
const DOWN = '#16a34a'
const UP_HOVER = '#ff5a5a'
const DOWN_HOVER = '#22e060'
// 平时的颜色 -> 悬停时的颜色。订单的点和连线的颜色只有这几种（做多红、做空绿、盈亏为 0 的灰），
// 绘制时按“当前颜色”查，不用给每个数据项再多存一份悬停色；查不到的（比如灰色）保持原色
const HOVER_COLOR = { [UP]: UP_HOVER, [DOWN]: DOWN_HOVER }

// 开仓三角、平仓圆点的尺寸：下面的最大值就是 K 线足够宽时的尺寸，K 线变窄时按比例缩小
const CANDLE_BAR_RATIO = 0.75   // 蜡烛实体占一格的比例，要和 series 里的 barWidth 保持一致
const TRI_MAX = 12              // 三角形底边（和高）的最大值（px）
const TRI_RATIO = 1 / 2         // 三角形底边不超过 K 线宽度的 1/2
const DOT_MAX = 7               // 圆点直径的最大值（px）
const DOT_RATIO = 1 / 3         // 圆点直径不超过 K 线宽度的 1/3
// 图形不设最小尺寸，改成限制 K 线的缩放下限：K 线实体最窄不低于这个宽度（px），缩到这么窄就不让再缩。
// 这样 K 线宽 6px 时，三角形底边 3px、圆点直径 2px 就是最小的图形，不会小到看不见
const CANDLE_MIN_PX = 6
// 连线用来接收鼠标的透明粗线的宽度（px）。可见的线只有 1px 宽，不放宽的话鼠标要偏离不到 2px 才碰得到。
// 越宽越容易悬停到线，但几条线交叉、相邻的地方越容易抢走别的订单的悬停；10px = 线两侧各 5px，是个折中，按手感调
const LINK_HIT_WIDTH = 10
// 绘图区左右的留白（px），要和下面 grid 的 left / right 一致；同屏最多能放几根 K 线按绘图区宽度算
const GRID_LEFT = 70
const GRID_RIGHT = 40

// dataZoom 窗口的最大跨度 maxValueSpan：一屏最多同时显示多少根 K 线，窗口再拉宽（缩小 K 线图）就会被限制住。
// 一格最窄 = K 线实体最窄 / 实体占一格的比例，绘图区宽度除以它就是最多能放几根。
// 注意 maxValueSpan 是窗口“终点序号 - 起点序号”，N 根 K 线的跨度是 N - 1，所以要减 1，
// 否则最宽时会多放一根，K 线实体比 CANDLE_MIN_PX 略窄（实测 5.95px）。
// 默认视图原来是显示全天（约 345 根），多数窗口宽度下放不下这么多，默认只显示其中一段，拖滑块或滚轮查看其余部分。
function maxVisibleBars() {
  const plotW = Math.max((chartRef.value?.clientWidth || 0) - GRID_LEFT - GRID_RIGHT, 0)
  const bars = Math.floor(plotW / (CANDLE_MIN_PX / CANDLE_BAR_RATIO))
  return Math.max(bars - 1, 1)
}

// 订单图形的绘制：原来的两个系列（交易连线、成交点）和悬停时叠在最上面的“悬停订单”系列共用同一份，
// 只是数据里各维度的下标不同，所以坐标所在的维度下标由 dims 传进来。

// 画一条连线。dims = [开仓序号, 开仓价, 平仓序号, 平仓价] 所在的维度下标；
// active：是否画成高亮样式；withHitArea：是否带一条透明的粗线专门接收鼠标（悬停层是 silent 的，不需要）
function drawLink(api, dims, active, withHitArea) {
  const p1 = api.coord([api.value(dims[0]), api.value(dims[1])])
  const p2 = api.coord([api.value(dims[2]), api.value(dims[3])])
  const baseColor = api.visual('color')
  // 悬停时换成更鲜艳的红 / 绿（只在高亮样式里用；平时的细线仍是 baseColor）
  const color = active ? HOVER_COLOR[baseColor] || baseColor : baseColor
  const shape = { x1: crispX(p1[0]), y1: p1[1], x2: crispX(p2[0]), y2: p2[1] }
  // 订单被悬停时的整体高亮：连线加粗、不透明、换成更鲜艳的颜色。
  // 不用 ECharts 的 emphasis 状态（实测对订单的三个图形无法联动），而是由数据里的 active 驱动：
  // 悬停订单的开仓点、连线、平仓点同时画成高亮样式（见 setActiveOrder）
  const visible = {
    type: 'line',
    shape,
    silent: true,
    style: active
      ? { stroke: color, lineWidth: 2.5, opacity: 1, fill: 'none' }
      : { stroke: color, lineWidth: 1, opacity: 0.9, fill: 'none' },
    emphasisDisabled: true
  }
  if (!withHitArea) return visible
  // 一条连线画成两层：
  //  - 下面一条 LINK_HIT_WIDTH 宽的透明粗线，专门接收鼠标：可见的线只有 1px，鼠标要偏离不到 2px 才算碰到
  //    （实测 3px 外就是空白），几乎对不准；透明粗线把能碰到的范围放宽。
  //  - 上面一条可见的线，silent 不接收鼠标，只负责画。
  // 两层共用同一个数据项，所以悬停透明粗线 = 悬停这个订单的连线，提示框、整体高亮都照常
  return {
    type: 'group',
    emphasisDisabled: true,   // 不让 ECharts 自己的悬停状态再叠一层，高亮完全由 active 控制
    children: [
      { type: 'line', shape, style: { stroke: 'rgba(0,0,0,0)', lineWidth: LINK_HIT_WIDTH, fill: 'none' }, emphasisDisabled: true },
      visible
    ]
  }
}

// 画一个开仓三角或平仓圆点。dims = [K 线序号, 价格, 形状] 所在的维度下标；
// 形状：1 做多开仓（尖朝上）、-1 做空开仓（尖朝下）、0 平仓（圆点）
function drawPoint(api, dims, active) {
  const kind = api.value(dims[2])
  const [px, py] = api.coord([api.value(dims[0]), api.value(dims[1])])
  const x = crispX(px)
  const baseColor = api.visual('color')
  // 悬停时换成更鲜艳的红 / 绿
  const color = active ? HOVER_COLOR[baseColor] || baseColor : baseColor
  // 图形大小跟着 K 线宽度走：缩小 K 线图（K 线变窄）时，图形不能比 K 线还大。
  // 蜡烛实体宽 = 一格的像素宽 × barWidth（75%）。每次缩放、拖动、改窗口大小都会重新进来，所以是动态的。
  // 现在的尺寸（三角 12px、圆点 7px）是最大值，只会缩小，不会放大。
  const candleW = api.size([1, 0])[0] * CANDLE_BAR_RATIO
  // 这个订单被悬停时，color 上面已经换成了悬停色，点本身没有别的高亮样式；三个图形的 active 同时为真，所以一起变色
  const style = { fill: color }
  if (kind === 0) {
    const d = Math.min(DOT_MAX, candleW * DOT_RATIO)          // 圆点直径：不超过 K 线宽度的 1/3
    return { type: 'circle', shape: { cx: x, cy: py, r: d / 2 }, style, emphasisDisabled: true }
  }
  // 三角形：底边不超过 K 线宽度的 1/2，高度和底边相等（等腰），尖端朝上（kind=1）或朝下（kind=-1）。
  // 三角形的视觉重心在底边往尖端 1/3 处，比外框中心偏离“边长的 1/6”（边长 12px 时就是 2px），
  // 整体往尖端方向挪这么多，让重心对准成交价
  const side = Math.min(TRI_MAX, candleW * TRI_RATIO)
  const h = side / 2
  const shift = -kind * (side / 6)
  const tip = py - kind * h + shift
  const base = py + kind * h + shift
  return {
    type: 'polygon',
    shape: { points: [[x, tip], [x + h, base], [x - h, base]] },
    style,
    emphasisDisabled: true
  }
}

// 两个订单系列（交易连线、成交点）的数据。active 是当前被鼠标悬停的订单序号（-1 = 没有），
// 属于这个订单的开仓点、平仓点、连线的最后一维置 1，renderItem 据此画成高亮样式。
// 初始渲染和悬停时的更新都用这个函数，不会出现两套数据格式。
function linkSeriesData(active) {
  return orderLinks.map((l) => ({
    // [开仓序号, 开仓价, 平仓序号, 平仓价, 是否高亮]
    value: [l.coords[0][0], l.coords[0][1], l.coords[1][0], l.coords[1][1], l.info.n === active ? 1 : 0],
    itemStyle: { color: l.lineStyle.color },
    info: l.info
  }))
}
function pointSeriesData(active) {
  return orderPoints.map((p) => ({ ...p, value: [p.value[0], p.value[1], p.value[2], p.info.n === active ? 1 : 0] }))
}
// 悬停订单系列的数据：只有被悬停的那一个订单的开仓点、平仓点、连线，没有悬停时是空的。
// 第 0 维是图形种类（0 点、1 连线），后面是各自的坐标：
//   点  [0, K 线序号, 价格, 形状]
//   连线 [1, 开仓序号, 开仓价, 平仓序号, 平仓价]
function hoverSeriesData(active) {
  if (active < 0) return []
  const data = []
  for (const l of orderLinks) {
    if (l.info.n === active) {
      data.push({ value: [1, l.coords[0][0], l.coords[0][1], l.coords[1][0], l.coords[1][1]], itemStyle: { color: l.lineStyle.color } })
    }
  }
  for (const p of orderPoints) {
    if (p.info.n === active) data.push({ value: [0, p.value[0], p.value[1], p.value[2]], itemStyle: p.itemStyle })
  }
  return data
}

// 绘图出错不能让异常一路冒到 loadDay / loadKline 的 catch 里：那里会把它当成“加载失败”，
// 清空数据后再画一次，第二次又抛出来，就变成没人接的 Uncaught (in promise)，也看不出真正出错的地方。
// 这里自己接住：把真实的错误和调用栈打到控制台，页面上给一句提示。
function renderChart() {
  if (!chart || chart.isDisposed()) return
  // 数据要整个换掉了：旧的悬停状态作废。否则 hoveredOrder 还指着旧数据里的订单号，
  // 新数据里同一个序号是另一笔订单，之后鼠标移开时会去取消高亮一个根本没高亮的订单
  hoveredOrder = -1
  hoverIndex.value = -1
  hideCross()
  try {
    drawChart()
  } catch (e) {
    console.error('[ReviewKline] 绘制 K 线失败', e)
    notice.value = `图表绘制失败：${e?.message || e}（详细调用栈见浏览器控制台）`
  }
}

function drawChart() {
  const bars = kline.value
  if (!bars.length) {
    chart.clear()
    hiddenTrades.value = []
    return
  }
  // 横轴用类目轴（第几根 K 线），夜盘到日盘之间的休市时间不留空白。
  // 新浪 K 线的时间戳是这根 K 线的“结束时间”（1 分钟线第一根是 09:01，5 分钟线第一根是 09:05，区间右闭），
  // 所以成交放在“结束时间不早于成交时间的第一根”里：09:03 的成交在 5 分钟线的 09:05 那根，09:05:00 整也在 09:05 那根。
  // 用精确到秒的时间比较，不能截断到分钟（09:05:30 应该落在 09:10 那根）。
  const ends = bars.map((b) => toMs(b.time))
  const periodMs = Math.max(period.value, 1) * 60000
  const indexOf = (timeStr) => {
    const k = toMs(timeStr)
    let lo = 0
    let hi = ends.length - 1
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (ends[mid] < k) lo = mid + 1
      else hi = mid
    }
    return lo
  }
  // 超出这天 K 线范围（比如开仓在前一个交易日、或在集合竞价时段）的成交不画，列在图下面。
  // 第一根 K 线覆盖的区间是 (end - 周期, end]，之前一个周期以内的成交（集合竞价略早于开盘）仍然贴到第一根上
  const inRange = (timeStr) => {
    const k = toMs(timeStr)
    return k >= ends[0] - 2 * periodMs && k <= ends[ends.length - 1] + periodMs
  }

  const labels = bars.map((b, i) => {
    const t = b.time
    const hm = t.slice(11, 16)
    // 夜盘的第一根（日期和上一根不同）带上日期，方便看出跨日
    const newDay = i === 0 || t.slice(0, 10) !== bars[i - 1].time.slice(0, 10)
    return newDay ? `${t.slice(5, 10)}\n${hm}` : hm
  })

  // 开仓点和平仓点同色，颜色由这笔交易的方向决定：做多红、做空绿
  const sideColor = (side) => (side === '多' ? UP : DOWN)
  const points = []   // 开、平仓标记
  const links = []    // 开仓到平仓的连线
  const hidden = []
  currentTrades.value.forEach((t, n) => {
    const openOk = t.openTime && inRange(t.openTime)
    const closeOk = t.closeTime && inRange(t.closeTime)
    if (t.openTime && !openOk) hidden.push(`${symbol.value} ${t.side}单 ${t.lots} 手：开仓 ${t.openTime} @ ${t.openPrice}（不在当天） → 平仓 ${t.closeTime} @ ${t.closePrice}，盈亏 ${t.pnl}`)
    if (!t.openTime) hidden.push(`${symbol.value} ${t.side}单 ${t.lots} 手：平仓 ${t.closeTime} @ ${t.closePrice}（文件里找不到对应的开仓），盈亏 ${t.pnl}`)
    if (t.closeTime && !closeOk) hidden.push(`${symbol.value} ${t.side}单 ${t.lots} 手：开仓 ${t.openTime} @ ${t.openPrice} → 平仓 ${t.closeTime} @ ${t.closePrice}（不在当天），盈亏 ${t.pnl}`)
    // 连线颜色表示这笔交易的盈亏：盈利红、亏损绿（和项目其它页面一致），盈亏为 0 用灰色
    const winColor = t.pnl > 0 ? UP : t.pnl < 0 ? DOWN : '#94a3b8'
    // info 里只放订单本身：不管鼠标悬停在开仓点、连线还是平仓点上，提示框都按订单展示，格式一样
    const info = { n, t }
    if (openOk) {
      points.push({
        name: 'open',
        // [K 线序号, 价格, 形状, 是否高亮]：形状 1 = 尖朝上的三角（做多开仓），-1 = 尖朝下的三角（做空开仓），0 = 圆点（平仓）；
        // 最后一维是这个订单当前是否被鼠标悬停（0 / 1），悬停时三个图形一起置 1，renderItem 据此画高亮样式
        value: [indexOf(t.openTime), t.openPrice, t.side === '多' ? 1 : -1, 0],
        itemStyle: { color: sideColor(t.side) },
        info
      })
    }
    if (closeOk) {
      points.push({
        name: 'close',
        value: [indexOf(t.closeTime), t.closePrice, 0, 0],
        itemStyle: { color: sideColor(t.side) },
        info
      })
    }
    if (openOk && closeOk) {
      links.push({
        coords: [[indexOf(t.openTime), t.openPrice], [indexOf(t.closeTime), t.closePrice]],
        lineStyle: { color: winColor },
        info
      })
    }
  })
  hiddenTrades.value = hidden
  // 保存下来：悬停高亮时只需要改 active 维重新生成这两个系列的数据，不用重新算整张图
  orderPoints = points
  orderLinks = links

  const lows = bars.map((b) => b.low)
  const highs = bars.map((b) => b.high)
  // y 轴要把所有成交价也包进去（成交价理论上都在 K 线的高低之内，但取整/数据缺口时可能略超出）
  const prices = points.map((p) => p.value[1])
  const yMin = Math.min(...lows, ...prices)
  const yMax = Math.max(...highs, ...prices)
  const pad = (yMax - yMin) * 0.05 || 1

  chart.setOption(
    {
      backgroundColor: '#16213e',
      animation: false,
      grid: { left: GRID_LEFT, right: GRID_RIGHT, top: 30, bottom: 90 },
      tooltip: {
        trigger: 'item',
        // 背景的不透明度 0.8 -> 0.6，更透一点，不会把后面的 K 线完全遮住
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        borderColor: '#00d4ff',
        textStyle: { color: '#fff' },
        // K 线（蜡烛）不响应鼠标，没有提示框，只有订单的开仓点、连线、平仓点有。
        // 三者作为一个整体：不管悬停在哪一个上，提示框都是同一种格式——订单（连线）的格式。
        formatter: (p) => {
          const info = p.data?.info
          if (!info) return ''
          // 悬停在开仓点或平仓点上时，几个订单的开仓（或平仓）可能落在同一根 K 线、同一价位上，点会叠在一起，
          // 把叠在一起的订单都列出来；悬停在连线上只列这一条
          const isPoint = p.seriesName === '成交点'
          const same = isPoint
            ? points.filter((q) => q.value[0] === p.data.value[0] && q.value[1] === p.data.value[1] && q.name === p.data.name)
            : [p.data]
          const block = ({ t }) => {
            const pc = t.pnl > 0 ? UP : t.pnl < 0 ? DOWN : '#fff'
            const pnl = `${t.pnl > 0 ? '+' : ''}${t.pnl.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            // 第一行“做多/做空 手数”；第二行是开仓“买/卖：价格”（做多开仓是买、做空开仓是卖），
            // 第三行平仓不再区分买卖，统一写“平：价格”。不显示时间。
            const openWord = t.side === '多' ? '买' : '卖'
            return `<div style="font-weight:bold;margin-bottom:4px">${t.side === '多' ? '做多' : '做空'} ${t.lots} 手</div>
              <div>${openWord}：${t.openPrice ?? '—'}</div>
              <div>平：${t.closePrice}</div>
              <div>盈亏：<b style="color:${pc}">${pnl}</b></div>`
          }
          return same.map((q) => block(q.info)).join('<div style="height:1px;background:#475569;margin:6px 0"></div>')
        }
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: true,
        axisLine: { lineStyle: { color: '#475569' } },
        axisLabel: { color: '#94a3b8', fontSize: 11, lineHeight: 15, hideOverlap: true },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        scale: true,
        min: Math.floor(yMin - pad),
        max: Math.ceil(yMax + pad),
        axisLine: { show: true, lineStyle: { color: '#475569' } },
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: 'rgba(71, 85, 105, 0.3)' } }
      },
      // maxValueSpan：一屏最多显示的 K 线根数，缩到 K 线实体窄于 CANDLE_MIN_PX 就不让再缩（见 maxVisibleBars）。
      // 窗口大小变化时由 handleResize 更新。一天有 300~500 根 1 分钟线，鼠标滚轮 / 拖滑块可以放大看细节、平移看其他时段
      dataZoom: [
        { type: 'inside', xAxisIndex: 0, filterMode: 'none', maxValueSpan: maxVisibleBars() },
        { type: 'slider', xAxisIndex: 0, filterMode: 'none', maxValueSpan: maxVisibleBars(), height: 24, bottom: 20, borderColor: '#334155', textStyle: { color: '#94a3b8' } }
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          // K 线不响应鼠标：悬停时不高亮（ECharts 默认会把边框加粗）、没有跟随鼠标的提示框，鼠标指针也保持普通箭头
          // （ZRender 里图形的 cursor 默认是 pointer，只要被命中指针就会变小手；silent 的图形不会被命中）。
          // K 线的信息在右上角固定的面板里显示，靠 bindKlineHover 监听整个画布的 mousemove 取得，不需要蜡烛被命中。
          // 只有订单（开仓点、连线、平仓点）才有高亮和跟随鼠标的提示框
          silent: true,
          // 蜡烛宽度占每根 K 线所在格子的比例。默认约 50%（实测蜡烛 9px、间隙 9px），调到 75% 让间隙缩小一半。
          // 不设 barMaxWidth：K 线少（放大后）时每格很宽，蜡烛也跟着变宽，空心框才好看
          barWidth: `${CANDLE_BAR_RATIO * 100}%`,
          // ECharts 的 candlestick 数据顺序是 [开, 收, 低, 高]；红涨绿跌
          data: bars.map((b) => [b.open, b.close, b.low, b.high]),
          // 空心 K 线：涨跌的实体都透明，只靠边框颜色区分——上涨（收 >= 开）红框，下跌绿框。
          // color / borderColor 是上涨的实体填充 / 边框，color0 / borderColor0 是下跌的。
          // 实体边框和上下影线共用 borderWidth，一个值同时控制整根 K 线的线条粗细
          itemStyle: { color: 'transparent', color0: 'transparent', borderColor: UP, borderColor0: DOWN, borderWidth: 1 }
        },
        {
          // 开仓到平仓的连线。用 custom 系列自己画，是为了让两个端点的 x 和 K 线影线严格重合：
          // ECharts 的蜡烛会把 1px 的影线对齐到“像素中心”（整数 + 0.5），比格子中心偏左约 0.7px；
          // 这个对齐在 ECharts 内部写死、不能关闭，而 lines 系列的端点是格子中心，所以两条线会差零点几个像素、看着没重合。
          // renderItem 每次渲染都会拿到当前缩放下的像素坐标，所以缩放、拖动、改变窗口大小后仍然对得上。
          name: '交易连线',
          type: 'custom',
          coordinateSystem: 'cartesian2d',
          z: 5,
          // 悬停高亮时不要让别的图形（K 线、其它订单）变淡
          emphasis: { focus: 'none' },
          // 放大后超出绘图区的部分裁掉，不要画到坐标轴外面
          clip: true,
          renderItem: (params, api) => drawLink(api, [0, 1, 2, 3], api.value(4) === 1, true),
          // data 的每一项是 [开仓序号, 开仓价, 平仓序号, 平仓价, 是否高亮]；颜色和 info 放在 itemStyle / info 里
          data: linkSeriesData(-1)
        },
        {
          // 开仓三角和平仓圆点。同样用 custom 系列自己画：scatter 的图形中心是格子中心，
          // 比 K 线影线（对齐到像素中心）偏右约 0.7px，放大看三角和圆点就像往右偏；
          // 这里 x 用和影线、连线同一个 crispX，三者严格在同一条竖线上。
          name: '成交点',
          type: 'custom',
          coordinateSystem: 'cartesian2d',
          z: 10,
          emphasis: { focus: 'none' },
          clip: true,
          renderItem: (params, api) => drawPoint(api, [0, 1, 2], api.value(3) === 1),
          data: pointSeriesData(-1)
        },
        {
          // 悬停订单：被鼠标悬停的那个订单（连线 + 开仓点 + 平仓点）整体浮到最上面。
          // 层级只能靠系列的 z 排：custom 系列里元素自己的 z 会被系列的 z 覆盖（ECharts 源码里注明 Always erase），
          // 元素只能用 z2，而 z2 只在同一个 z 里比较——被悬停订单的连线在连线系列（z 5）里，永远盖不过成交点系列（z 10）
          // 里别的订单的点。所以单独开一个 z 最高的系列，只放被悬停的订单，在它们上面再画一份；
          // 原来两个系列里的图形一个都没动，悬停结束时这个系列清空，层级顺序自然恢复。
          // silent：不接收鼠标。命中仍落在下面原来的图形上，鼠标事件的流程和以前完全一样，
          // 不会因为上面多出来一层而触发 mouseout → 熄灭 → 再点亮的循环。
          name: '悬停订单',
          type: 'custom',
          coordinateSystem: 'cartesian2d',
          z: 20,
          silent: true,
          clip: true,
          renderItem: (params, api) =>
            api.value(0) === 1
              ? drawLink(api, [1, 2, 3, 4], true, false)   // 连线：强制高亮样式，不要透明粗线
              : drawPoint(api, [1, 2, 3], true),           // 点：强制高亮样式
          data: hoverSeriesData(-1)
        }
      ]
    },
    true
  )
}

// ---------- 订单悬停：开仓点、连线、平仓点作为一个整体 ----------
// 悬停订单的任意一个图形（开仓点、连线、平仓点），这个订单的三个图形一起高亮；离开一起恢复。
// 没有用 ECharts 自带的 highlight / emphasis：它只会高亮鼠标直接碰到的那一个图形，三个图形分属两个系列，没法联动。
// 改成数据驱动：每个数据项最后一维 active 表示“它的订单是否被悬停”，改完 active 重新给这两个系列设数据，
// renderItem 按 active 画高亮样式。只更新这两个系列（合并模式、不带 true），不碰 K 线，也不会重置 dataZoom；
// ECharts 按 dataIndex 复用已有图形、只改属性，鼠标下面的图形不会被销毁重建，所以不会因为重绘触发 mouseout 引起闪烁。
let hoveredOrder = -1

function setActiveOrder(n) {
  if (n === hoveredOrder) return
  hoveredOrder = n
  if (!chart || chart.isDisposed()) return
  // series 里按 name 对应，不依赖它们在数组里的下标
  chart.setOption({
    series: [
      { name: '交易连线', data: linkSeriesData(n) },
      { name: '成交点', data: pointSeriesData(n) },
      { name: '悬停订单', data: hoverSeriesData(n) }
    ]
  })
}

function bindOrderHover() {
  // 只处理订单的两个系列；K 线、坐标轴等其它图形的事件忽略
  const isOrder = (p) => p?.seriesName === '成交点' || p?.seriesName === '交易连线'
  // 注意这里不用 chart.on(事件名, { seriesName }, 回调) 这种带 query 的写法，而是监听全部事件、自己在回调里判断系列：
  // 实测带 query 的监听收不到连线上的事件（同一条线上提示框却能弹出），自己判断就绕开了它。
  // mousemove 在鼠标停留、移动时持续触发，每次都按这一刻鼠标下的订单决定高亮谁；
  // setActiveOrder 对同一个订单重复调用会直接返回，不会重复重绘
  chart.on('mousemove', (p) => {
    if (!isOrder(p)) return
    const n = p.data?.info?.n
    if (n != null) setActiveOrder(n)
  })
  chart.on('mouseout', (p) => {
    if (!isOrder(p)) return
    setActiveOrder(-1)
  })
  // 鼠标直接离开整个图表时也要熄灭
  chart.on('globalout', () => setActiveOrder(-1))
}

// ---------- 跟随鼠标的十字虚线 ----------
// 横向颗粒度 1 根 K 线：竖线吸附到鼠标所在那根 K 线的中心（用 crispX，和影线、成交点在同一条竖线上）；
// 纵向颗粒度 1：横线吸附到离鼠标最近的整数价格。轴上的标签分别显示这根 K 线的时间和这个整数价格。
//
// 没有用 ECharts 的 axisPointer：资金曲线那边的十字线是 tooltip.trigger: 'axis' 带出来的，而这张图的提示框是
// trigger: 'item'（只有压到订单图形才弹出），两者不能混用——之前试过单独开轴上的 axisPointer，虚线没出现、提示框还不消失。
// 也没有用 setOption({ graphic })：鼠标每动一下就 setOption，会干扰订单的悬停联动和提示框。
// 直接把图形加到 ZRender 画布上，不经过 setOption，也不属于任何系列；实测合并更新、整体替换、clear、resize 之后都还在。
// 所有元素 silent，不接收鼠标，不会挡住下面订单图形的悬停。
const CROSS_COLOR = '#B9BEC9'       // ECharts 默认十字指示器的线色，和资金曲线那边一致
const CROSS_DASH = [2, 2]           // 虚线：线段 2px、间隔 2px（原来 4/4），越小越密
const CROSS_OPACITY = 0.5           // 十字线的不透明度，越小越浅；只作用在两条线上，轴上的标签不受影响
const CROSS_LABEL_BG = '#6a7985'    // 轴上标签的底色（ECharts 默认指示器标签的灰底）
let cross = null                     // { group, vLine, hLine, xBg, xText, yBg, yText }

function createCross() {
  const { Group, Line, Rect, Text } = echarts.graphic
  const lineStyle = { stroke: CROSS_COLOR, lineWidth: 1, lineDash: CROSS_DASH, opacity: CROSS_OPACITY }
  const textStyle = { fill: '#fff', fontSize: 12 }
  const group = new Group()
  group.ignore = true
  const vLine = new Line({ silent: true, z: 100, style: lineStyle, shape: { x1: 0, y1: 0, x2: 0, y2: 0 } })
  const hLine = new Line({ silent: true, z: 100, style: lineStyle, shape: { x1: 0, y1: 0, x2: 0, y2: 0 } })
  const xBg = new Rect({ silent: true, z: 101, style: { fill: CROSS_LABEL_BG }, shape: { r: 3, x: 0, y: 0, width: 0, height: 0 } })
  const xText = new Text({ silent: true, z: 102, style: { ...textStyle, text: '' } })
  const yBg = new Rect({ silent: true, z: 101, style: { fill: CROSS_LABEL_BG }, shape: { r: 3, x: 0, y: 0, width: 0, height: 0 } })
  const yText = new Text({ silent: true, z: 102, style: { ...textStyle, text: '' } })
  ;[vLine, hLine, xBg, xText, yBg, yText].forEach((el) => group.add(el))
  chart.getZr().add(group)
  return { group, vLine, hLine, xBg, xText, yBg, yText }
}

// 把文字标签画在 (x, y) 附近：先量出文字的宽高，再按 align 放置背景框和文字
function placeLabel(bg, text, str, x, y, align) {
  text.attr({ style: { text: str } })
  const w = text.getBoundingRect().width + 14     // 左右各 7px 内边距，和 ECharts 默认标签一致
  const h = text.getBoundingRect().height + 10    // 上下各 5px
  const left = align === 'center' ? x - w / 2 : x - w            // center：以 x 为中心；right：右边贴着 x
  bg.attr({ shape: { x: left, y, width: w, height: h, r: 3 } })
  text.attr({ x: left + 7, y: y + 5 })
}

function hideCross() {
  if (cross) { cross.group.ignore = true; cross.group.markRedraw() }
}

function updateCross(offsetX, offsetY, index) {
  if (!cross) cross = createCross()
  const w = chart.getWidth()
  const h = chart.getHeight()
  const top = 30                         // 和 grid 的 top / bottom 一致
  const bottom = h - 90
  // 纵向颗粒度 1：鼠标处的价格取整，横线画在这个整数价对应的像素上
  const rawPrice = chart.convertFromPixel({ yAxisIndex: 0 }, offsetY)
  if (!Number.isFinite(rawPrice)) return hideCross()
  const price = Math.round(rawPrice)
  const y = chart.convertToPixel({ yAxisIndex: 0 }, price)
  // 横向颗粒度 1 根 K 线：竖线画在这根 K 线的中心
  const x = crispX(chart.convertToPixel({ xAxisIndex: 0 }, index))
  const left = GRID_LEFT
  const right = w - GRID_RIGHT
  // 吸附后的价格可能略出绘图区（鼠标在边缘时），夹回绘图区内
  const yy = Math.min(Math.max(y, top), bottom)

  cross.vLine.attr({ shape: { x1: x, y1: top, x2: x, y2: bottom } })
  cross.hLine.attr({ shape: { x1: left, y1: yy, x2: right, y2: yy } })
  // X 轴标签：贴着绘图区底边下方，显示这根 K 线的时间；Y 轴标签：贴着绘图区左边，显示整数价格
  placeLabel(cross.xBg, cross.xText, kline.value[index].time.slice(5, 16), x, bottom + 2, 'center')
  const yLabel = String(price)
  placeLabel(cross.yBg, cross.yText, yLabel, left - 2, yy - 11, 'right')
  cross.group.ignore = false
  cross.group.markRedraw()
}

// ---------- 鼠标所在 K 线的信息（右上角固定面板）+ 十字虚线 ----------
// 挂在 ZRender 层而不是 chart.on：chart.on('mousemove') 只有鼠标压在某个图形上才触发，
// 而这里希望鼠标在 K 线之间的空隙、影线旁边、甚至在订单图形上都能显示这一根 K 线的信息。
function bindKlineHover() {
  const zr = chart.getZr()
  zr.on('mousemove', (e) => {
    // 鼠标指针：鼠标悬停在订单的开仓点、连线、平仓点上时隐藏指针（cursor: none），移开后恢复。
    // ZRender 里图形的 cursor 默认是 pointer，被命中就把指针设成小手；custom 系列的 renderItem 返回值里写 cursor 无效
    // （ECharts 只透传 silent / ignore / invisible 等几个属性，实测写了也没用）。所以在这里覆盖：
    // ZRender 内部先设光标、再触发这个监听（实测顺序：pointer → 本监听），这里再改成 none 就是最终结果。
    // 恢复不用管：ZRender 每次 mousemove 都会按“鼠标下有没有图形”重设一遍光标，移到没有命中图形的地方它自己会设回 default。
    // 只改“命中了图形且光标是默认小手”的情况，dataZoom 滑块自己设的拖拽光标（move / ew-resize 等）不会被动到
    if (e.target && e.target.cursor === 'pointer') zr.setCursorStyle('none')
    if (!kline.value.length || !chart.containPixel('grid', [e.offsetX, e.offsetY])) {
      hoverIndex.value = -1
      hideCross()
      return
    }
    // 只给 x 轴（{ xAxisIndex: 0 }）时，convertFromPixel 要传一个像素标量、返回一个标量（K 线序号，带小数）；
    // 传数组会得到 NaN。四舍五入取最近的一根，再夹在有效范围内
    const idx = chart.convertFromPixel({ xAxisIndex: 0 }, e.offsetX)
    if (!Number.isFinite(idx)) {
      hoverIndex.value = -1
      hideCross()
      return
    }
    hoverIndex.value = Math.min(Math.max(Math.round(idx), 0), kline.value.length - 1)
    updateCross(e.offsetX, e.offsetY, hoverIndex.value)
  })
  // 鼠标离开整个图表：面板和十字线都隐藏
  zr.on('globalout', () => { hoverIndex.value = -1; hideCross() })
}

// ---------- 生命周期 ----------
// 图表要跟随容器的尺寸，而不是只跟随窗口：刚切换到这个视图时，父级的 flex 布局还没稳定，
// echarts.init 量到的是容器当时的高度（min-height 的 420px），之后容器被撑大了，ECharts 不会自己知道，
// 图就停在小尺寸上，直到窗口缩放触发 resize 才恢复。用 ResizeObserver 盯着容器本身，
// 它的尺寸只要变化（布局稳定、提示条出现、窗口缩放、侧边栏变化）就重新量一次。
let resizeObserver = null
const handleResize = () => {
  if (!chart || chart.isDisposed()) return
  chart.resize()
  // 容器宽度变了，一屏最多能放的 K 线根数也跟着变。合并模式（不带 true）只改这个值，不会重置用户当前的缩放窗口；
  // 没画过图（没有 K 线）时 dataZoom 组件还不存在，不用更新
  if (!kline.value.length) return
  const max = maxVisibleBars()
  chart.setOption({ dataZoom: [{ maxValueSpan: max }, { maxValueSpan: max }] })
}

// 日期列表变化（导入了新文件）：默认选最近一个交易日
watch(
  () => props.days,
  (list) => {
    if (!list.length) {
      day.value = ''
      symbols.value = []
      kline.value = []
      symbol.value = ''
      renderChart()
      return
    }
    if (!list.includes(day.value)) day.value = list[list.length - 1]
  },
  { immediate: true }
)
// 缓存：组件常驻（切 Tab 不卸载），数据只在“依赖变了”时重新请求。
// 隐藏期间依赖变了（比如在曲线 Tab 里改了筛选条件）只记脏标记，切回来才请求一次
let stale = false
// getter 必须返回原始值（字符串）而不是数组：返回数组时每次求值都是新引用，Vue 用 Object.is 比较，
// 值没变也会判定“变了”而触发回调（父组件重新渲染、props.products 换了新数组引用就会这样），
// 结果是隐藏期间被误打脏标记，切回 Tab 时白白重新请求一次
const loadKey = computed(() => [props.reviewId, props.products.join(','), day.value].join('|'))
watch(loadKey, () => {
  if (!props.active) {
    stale = true
    return
  }
  stale = false
  loadDay()
})
watch(
  () => props.active,
  (on) => {
    if (!on || !stale) return
    stale = false
    loadDay()
  }
)

onMounted(() => {
  // 不再 await nextTick()：onMounted 时模板已经渲染完，chartRef 一定有值；
  // 中间多一个 await 的话，用户快速切走时组件已卸载、chartRef 变成 null，init 就会在没人接的 Promise 里抛错
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  bindOrderHover()
  bindKlineHover()
  window.addEventListener('resize', handleResize)
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(chartRef.value)
  }
  // 首次加载的入口就是这里：监听 day 的 watch 是在 immediate 的 watch 改完 day 之后才创建的，
  // 创建时 day 已经是最新值，之后不会再变化，所以进入页面时不会自动触发 loadDay（实测 0 次）
  loadDay()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  resizeObserver?.disconnect()
  resizeObserver = null
  if (chart) {
    chart.dispose()
    chart = null
  }
  cross = null
})
</script>

<style scoped>
/* 空状态 / 加载中的样式（chart-empty、chart-loading 等）和复盘页共用同一份；.kline-* 是这个组件自己的 */
@import '@/styles/Review.css';
@import '@/styles/ReviewKline.css';
</style>
