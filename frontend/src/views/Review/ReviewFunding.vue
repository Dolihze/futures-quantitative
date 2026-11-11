<template>
  <div class="chart-wrapper">
    <div ref="chartRef" class="pnl-chart"></div>

    <!-- 空状态 / 提示 -->
    <div v-if="!fileInfo" class="chart-empty">
      <div class="empty-icon">📈</div>
      <div class="empty-title">还没有数据</div>
      <div class="empty-desc">在左侧导入期货公司结算单（含「成交明细」工作表的 Excel），即可生成盈亏曲线</div>
      <div class="empty-desc">需要「成交时间」「合约」「买/卖」「开/平」「成交价」「手数」，有「手续费」「平仓盈亏」更准确</div>
    </div>
    <!-- 筛选条件下一笔“平”都没有，有两种原因：这段时间只有开仓（还没平仓），或者筛选范围里本来就没有成交 -->
    <div v-else-if="curve && curve.trades === 0 && !loading" class="chart-empty">
      <div class="empty-icon">🔍</div>
      <template v-if="curve.openOnly">
        <div class="empty-title">当前筛选下只有开仓，没有平仓</div>
        <div class="empty-desc">曲线只统计「平」的成交，还没有平仓就没有盈亏可画</div>
        <div class="empty-desc">可以把时间范围拉长，或选择有平仓的品种</div>
      </template>
      <template v-else>
        <div class="empty-title">当前筛选条件下没有成交记录</div>
        <div class="empty-desc">请调整时间范围或交易品种</div>
      </template>
    </div>
    <div v-if="loading" class="chart-loading">
      <div class="loading-spinner"></div>
      <div class="loading-text">{{ loadingText }}</div>
    </div>
  </div>
</template>

<script setup>
// 账户盈亏曲线：只负责画图。数据（curve）、筛选、加载状态都由父组件 Review.vue 管理，通过 props 传进来；
// 曲线数据一变就自动重画。
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { chartColors, onThemeChange } from '@/utils/chartTheme'

const props = defineProps({
  curve: { type: Object, default: null },        // { points, xs, segments, details, openMarks, stats, trades, openOnly }
  fileInfo: { type: Object, default: null },     // 没有文件时显示“还没有数据”的空状态
  loading: { type: Boolean, default: false },
  loadingText: { type: String, default: '' }
})
// 绘图出错时通知父组件，由它显示在左侧的错误区（和重构前一样）
const emit = defineEmits(['error'])

// ---------- 格式化（红涨绿跌，与项目其它页面一致）----------
const plain = (v) => Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const money = (v) => (v > 0 ? '+' : '') + plain(v)

// ---------- 图表 ----------
const chartRef = ref(null)
let chart = null

// 当前图上的段（renderChart 每次更新）。缩放事件的回调要用它重算刻度
let currentSegments = []

// 鼠标在图表容器里最新的横向像素位置（相对图表左边缘），-1 表示鼠标不在图上。
// 提示框要用它判断“鼠标是否靠近某个交易点”：axis 型提示框拿到的 axisValue 始终是吸附到最近数据点的值
// （ECharts 源码 axisTrigger.js 里注明 Tooltip should always be snapToValue），不是鼠标的真实位置。
// 用 DOM 捕获阶段监听：比 ZRender 内部的鼠标处理（以及挂在它上面的提示框）更早执行，所以提示框的 formatter 被调用时
// 读到的已经是这一次移动的位置，而不是上一次的
let mouseOffsetX = -1
function onDomMouseMove(e) {
  const rect = chartRef.value?.getBoundingClientRect()
  mouseOffsetX = rect ? e.clientX - rect.left : -1
}
function onDomMouseLeave() {
  mouseOffsetX = -1
}

function initChart() {
  chart = echarts.init(chartRef.value)
  chartRef.value.addEventListener('mousemove', onDomMouseMove, true)
  chartRef.value.addEventListener('mouseleave', onDomMouseLeave, true)
  // 缩放（滚轮、拖滑块）时，按“当前可见的范围”重新生成刻度、标签和段名：
  // 8 个交易日全显示时每段很窄，只能标日期；放大到一两天后每段有几百像素，所有边界时间标签才放得下。
  // 监听只在这里挂一次（renderChart 每次筛选都会调用，挂在那里会越积越多、一次缩放重算 N 次）。
  chart.on('datazoom', onDataZoom)
  renderChart()
}

function onDataZoom() {
  if (!chart || !currentSegments.length) return
  const dz = chart.getOption().dataZoom?.[0]
  if (dz?.startValue == null || dz?.endValue == null) return
  const plotWidthPx = Math.max(200, chart.getWidth() - 70 - 56)
  const y = chart.getOption().yAxis?.[0]
  const view = viewDependentOptions(currentSegments, plotWidthPx, [dz.startValue, dz.endValue], y?.min, y?.max)
  // 合并模式（不带 true）：只更新刻度、段名和段间虚线，不会把用户刚设好的缩放窗口重置掉。
  // markLine 的第一项是 0 线，合并更新会整体替换 data，所以必须把它带上，否则 0 线会消失
  chart.setOption({
    xAxis: view.xAxis,
    series: [{
      markArea: { silent: true, data: view.areas },
      markLine: {
        silent: true,
        symbol: 'none',
        label: { show: false },
        lineStyle: { color: chartColors().text, type: 'dashed' },
        data: [{ yAxis: 0 }, ...view.sepLines]
      }
    }]
  })
}

// y 轴范围：覆盖 0 线并留出一点边距。
// 线条/面积的红绿分界依赖这个范围来定位 0 线，所以轴范围和渐变必须用同一组数。
function valueRange(points) {
  let lo = 0
  let hi = 0
  for (const p of points) {
    if (p[1] < lo) lo = p[1]
    if (p[1] > hi) hi = p[1]
  }
  const pad = (hi - lo) * 0.05 || 1
  // 取整到“好看”的数：13,651.2 这样带小数的上下限像是数据值，容易被误读。
  // 间隔取范围的约 1/10，取整后多出来的空白不会超过一格，曲线能占满大部分高度
  const step = niceStep((hi - lo + 2 * pad) / 10)
  return { min: Math.floor((lo - pad) / step) * step, max: Math.ceil((hi + pad) / step) * step }
}

// 取一个 1 / 2 / 5 × 10^n 的间隔，使 5 格左右能盖住整个范围
function niceStep(raw) {
  if (!(raw > 0)) return 1
  const pow = Math.pow(10, Math.floor(Math.log10(raw)))
  const f = raw / pow
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * pow
}

// 红涨绿跌：按“值”以 0 为界给线条和数据点上色。
// - 之前用过按 y 轴范围算偏移的线性渐变，但 ECharts 把渐变铺在“线条自己的包围盒”上，
//   整段为正的曲线（从 0 起步）开头一小段会被画成绿色（已用像素统计验证）。
// - piecewise 类型的 visualMap 在这里会抛 "Cannot read properties of undefined (reading 'coord')"。
// continuous 类型不受这两个问题影响：min/max 取 0 附近极小的区间，等价于“<=0 绿，>0 红”。
// dimension 固定为 1：时间轴的数据是 [时间, 值]，值在第 1 维；类目轴的数据虽然是纯数值，
// 但 ECharts 把“类目序号”算作第 0 维，值同样在第 1 维。
// 如果用 0，类目轴上读到的是序号（恒为正），整条线会被画成红色（已用像素统计验证）。
function pnlVisualMap() {
  return {
    show: false,
    type: 'continuous',
    dimension: 1,
    seriesIndex: 0,
    min: -0.0001,
    max: 0.0001,
    inRange: { color: ['#22c55e', '#ef4444'] },
    outOfRange: { color: '#22c55e' }
  }
}

// ---- x 轴 / tooltip ----
// 横轴是“固定的四个交易时段”：夜盘 21:00-23:00 → 早盘一 09:00-10:15 → 早盘二 10:30-11:30 → 午盘 13:30-15:00。
// 段与段首尾相接（休息时间不画），段宽与真实时长成正比，所以横轴仍然是时间。每个出现过成交的交易日都有完整的四段。
// 后端已经把每个点的横坐标（xs）和所有的段（segments: name / x0 / x1 / start / end）算好了，前端只负责画：
//   刻度 = 每段的起点、终点和段内的整刻度，标签直接由段的真实起止时刻推出，不需要从压缩坐标反推时间；
//   段名用 markArea 写（不画底色）；日期标在交易日的早盘一起点上。

const pad2 = (n) => String(n).padStart(2, '0')
const fmtHM = (d) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
const fmtMDHMS = (d) => `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
const fmtMD = (d) => `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
const parseTime = (s) => new Date(s.replace(' ', 'T'))
const fmtFull = (iso) => iso.replace('T', ' ')

// 段内某个横坐标 x 对应的真实时刻
function segTimeAt(seg, x) {
  return new Date(parseTime(seg.start).getTime() + (x - seg.x0) * 60000)
}

// 横轴上任意一个位置 x（轴单位，1 单位 = 1 分钟）对应的真实时刻，精确到秒。十字线在 X 轴上显示的标签用它。
// 段与段之间有一段空隙（实际是每个休市间隔留的 14 个单位，用来画分隔线和交界标签），鼠标落在空隙里或轴两端的补白里时
// 没有真实时间，取离得最近的段端点的时间（比如 10:15 和 10:30 之间显示较近的那个）。
// 1 秒 = 1/60 单位，所以先换算成毫秒再四舍五入到整秒。
function axisTimeAt(segments, x) {
  if (!segments.length || !Number.isFinite(x)) return null
  let seg = segments.find((s) => x >= s.x0 && x <= s.x1)
  let xx = x
  if (!seg) {
    // 不在任何一段里：找离 x 最近的段，并把 x 夹到这一段的端点上
    seg = segments.reduce((best, s) => {
      const d = x < s.x0 ? s.x0 - x : x - s.x1
      return d < best.d ? { s, d } : best
    }, { s: segments[0], d: Infinity }).s
    xx = Math.min(Math.max(x, seg.x0), seg.x1)
  }
  const ms = parseTime(seg.start).getTime() + (xx - seg.x0) * 60000
  return new Date(Math.round(ms / 1000) * 1000)
}

const LABEL_PX = 56      // 一个 HH:mm 标签（含间距）大约占的像素
const JOINT_PX = 84      // 相邻两个“交界标签”（如 10:15 | 10:30）的中心至少隔这么多像素：一个交界标签约 70px 宽
const SEG_NAME_PX = 72   // 一段至少这么宽才写段名。最长的段名“早盘（上）”约 60px，写在图的上方；时间标签在 X 轴下方，纵向不冲突，
                         // 所以只取决于段名自己放不放得下。（以前定 100，两个交易日时早盘一/早盘二的名字全被丢了，看着像漏了两段）
const SEG_FULL_PX = 130  // 一段至少这么宽才加段内的整刻度
const DATE_PX = 54       // 两个日期标签之间至少隔这么多像素，否则会叠在一起
const HOVER_NEAR_PX = 12 // 鼠标离交易点的横坐标不超过这么多像素，才弹出该笔交易的详情

// 刻度、标签和段名。关键：按“当前可见的范围”算，而不是整条轴——
// 8 个交易日全显示时每段只有几十个像素，64 个边界标签放不下（已截图验证：糊成 28900013003300…）；
// 放大到一两天后每段有几百像素，所有边界标签就应该出现。所以缩放时要重算。
// 标签分三类：
//  - 交界标签：相邻两段之间一个，写“上一段的终点 | 下一段的起点”（黄 | 蓝），这是用户最关心的四个时段的边界时间；
//    相邻两个交界标签的中心至少隔 JOINT_PX，放不下就隔一个丢一个（带日期的交界优先保留）；
//  - 段名：一段够宽（>= SEG_NAME_PX）才写；
//  - 段内整刻度：一段更宽（>= SEG_FULL_PX）才加，并且不能和已有标签挤在一起。
// 日期是**交易日**，写在“夜盘 | 早盘一”这个交界标签的上面一行。交界标签一个都放不下的多天视图里，
// 退回成每个交易日一个孤立的日期。
// 返回 { ticks: [x...], labels: Map(x -> 文字), names: Set(段下标) 需要写段名的段 }
function buildSessionTicks(segments, plotWidthPx, range) {
  if (!segments.length) return { ticks: [], labels: new Map(), names: new Set() }
  const [vx0, vx1] = range ?? [segments[0].x0, segments[segments.length - 1].x1]
  const visible = Math.max(vx1 - vx0, 1)
  const pxPerUnit = plotWidthPx / visible
  const labels = new Map()
  const ticks = []
  const names = new Set()
  const put = (x, text) => { if (!labels.has(x)) { ticks.push(x); labels.set(x, text) } }
  const inView = (x) => x >= vx0 - 1e-6 && x <= vx1 + 1e-6
  const hm = (s) => fmtHM(parseTime(s))

  // 1) 段名：只给当前够宽的段写
  segments.forEach((seg, idx) => {
    if (seg.x1 < vx0 || seg.x0 > vx1) return
    const segPx = (Math.min(seg.x1, vx1) - Math.max(seg.x0, vx0)) * pxPerUnit
    if (segPx >= SEG_NAME_PX) names.add(idx)
  })

  // 2) 交界标签：相邻两段之间只有一个刻度，把“上一段的终点 | 下一段的起点”写在同一个标签里（黄 | 蓝）。
  //    不能分别给两个刻度点各放一个标签：它们只隔一个很窄的间隔（约 17px），每个标签文字约 28px，
  //    居中摆放一定叠在一起。曾尝试用 rich 的 align 左右错开，但那个 align 只控制文字在文本块内部靠哪边，
  //    不改变整个标签相对刻度点的位置，没有效果（已用画布像素验证：黄蓝文字全都挤进了两个刻度之间）。
  //    合并成一个标签后，黄蓝在同一个文本块里从左到右排，不依赖任何对齐。
  //    日期放在“夜盘 | 早盘一”这个交界上（日期是交易日，早盘一起点所在的位置）。
  let lastPx = -Infinity
  const jointText = (prev, next, withDate) => {
    const body = `{e|${hm(prev.end)}}{sep| | }{s|${hm(next.start)}}`
    return withDate ? `{d|${next.day.slice(5)}}\n${body}` : body
  }
  for (let i = 0; i < segments.length - 1; i++) {
    const prev = segments[i]
    const next = segments[i + 1]
    const x = (prev.x1 + next.x0) / 2
    if (!inView(x)) {
      // 放大到某个交易日后，它和相邻交易日的交界（午盘 15:00 | 夜盘 21:00）的中点落在可见范围之外，
      // 但这一侧的端点（这个交易日的夜盘起点 21:00 或午盘终点 15:00）仍然在可见范围内，不能整个丢掉
      // （已发现：放大到一天后缺了 21:00 和 15:00 两个边界）。把还看得见的那一侧单独标出来。
      if (inView(next.x0) && !ticks.some((t) => Math.abs((t - next.x0) * pxPerUnit) < LABEL_PX)) put(next.x0, `{s|${hm(next.start)}}`)
      if (inView(prev.x1) && !ticks.some((t) => Math.abs((t - prev.x1) * pxPerUnit) < LABEL_PX)) put(prev.x1, `{e|${hm(prev.end)}}`)
      continue
    }
    const px = (x - vx0) * pxPerUnit
    const isDateJoint = prev.key === 'night' && next.key === 'am1'   // 夜盘 | 早盘一：交易日的日期放这里
    // 相邻两个交界标签的中心至少隔 JOINT_PX，否则丢掉后一个；带日期的交界优先保留
    if (px - lastPx < JOINT_PX) {
      if (isDateJoint && labels.size) {
        // 带日期的交界不能丢：把前一个冲突的标签去掉
        const lastX = ticks[ticks.length - 1]
        ticks.pop(); labels.delete(lastX)
      } else {
        continue
      }
    }
    put(x, jointText(prev, next, isDateJoint))
    lastPx = px
  }

  // 3) 整条轴最左端（第一段起点）和最右端（最后一段终点）：只有一边，居中标出
  const first = segments[0]
  const last = segments[segments.length - 1]
  if (inView(first.x0) && (first.x0 - vx0) * pxPerUnit >= 0 && ((first.x0 + 0) - vx0) * pxPerUnit < plotWidthPx) {
    if (!ticks.some((t) => Math.abs((t - first.x0) * pxPerUnit) < JOINT_PX / 2)) put(first.x0, `{s|${hm(first.start)}}`)
  }
  if (inView(last.x1) && !ticks.some((t) => Math.abs((t - last.x1) * pxPerUnit) < JOINT_PX / 2)) put(last.x1, `{e|${hm(last.end)}}`)

  // 4) 段内整刻度：只有整段够宽才加，按像素宽度决定能放几个，离两端太近的不要
  segments.forEach((seg) => {
    if (seg.x1 < vx0 || seg.x0 > vx1) return
    const segPx = (Math.min(seg.x1, vx1) - Math.max(seg.x0, vx0)) * pxPerUnit
    if (segPx < SEG_FULL_PX) return
    const fit = Math.floor(segPx / LABEL_PX) - 1
    if (fit < 1) return
    const start = parseTime(seg.start)
    const end = parseTime(seg.end)
    const minutes = seg.x1 - seg.x0
    const step = [15, 30, 60, 120].find((s) => minutes / s - 1 <= fit) ?? 120
    const base = new Date(start); base.setHours(0, 0, 0, 0)
    const stepMs = step * 60000
    const minGap = JOINT_PX / 2 / pxPerUnit + (LABEL_PX * 0.5) / pxPerUnit
    for (let t = base.getTime() + Math.ceil((start.getTime() - base.getTime()) / stepMs) * stepMs; t < end.getTime(); t += stepMs) {
      const x = seg.x0 + (t - start.getTime()) / 60000
      if (!inView(x)) continue
      if (x - seg.x0 < minGap || seg.x1 - x < minGap) continue
      if (ticks.some((tx) => Math.abs((tx - x) * pxPerUnit) < LABEL_PX)) continue   // 和已有标签太近就不放
      put(x, `{h|${fmtHM(new Date(t))}}`)
    }
  })

  // 5) 多个交易日同时显示、交界标签一个都放不下时，至少保留每个交易日的日期（交易日的锚点）
  if (!ticks.length || segments.length > 8) {
    let lastDatePx = -Infinity
    segments.forEach((seg) => {
      if (seg.key !== 'am1' || !inView(seg.x0)) return
      const px = (seg.x0 - vx0) * pxPerUnit
      if (px - lastDatePx < DATE_PX) return
      if (labels.has(seg.x0) || ticks.some((tx) => Math.abs((tx - seg.x0) * pxPerUnit) < DATE_PX / 2)) return
      put(seg.x0, `{d|${seg.day.slice(5)}}`)
      lastDatePx = px
    })
  }
  return { ticks, labels, names }
}

// 随“当前可见范围”变化的那部分：X 轴的刻度/标签，以及每段的段名。
// 初始渲染用整条轴的范围；缩放（滚轮、滑块）时用当前范围重新算，放大后边界标签才会出现。
function viewDependentOptions(segments, plotWidthPx, range, yMin, yMax) {
  const { ticks, labels, names } = buildSessionTicks(segments, plotWidthPx, range)
  // 段名：只给“当前够宽”的段写，否则 8 天的段名会互相盖住（已截图验证）。
  // 不画底色：各段交替的深浅底色看得眼花（用户反馈）。段与段之间已经有竖向虚线分隔，不需要再用底色区分。
  // markArea 只用来写段名，色块设成完全透明。
  const areas = segments.map((seg, i) => [
    {
      xAxis: seg.x0,
      itemStyle: { color: 'transparent' },
      label: { show: names.has(i), position: 'insideTop', color: chartColors().text, fontSize: 11, formatter: seg.name }
    },
    { xAxis: seg.x1 }
  ])
  // 段与段之间（休息时间）的竖向虚线，同样按当前可见范围决定画不画：
  // 8 个交易日全显示时有三十多条虚线铺满绘图区，看着像一张网格——和被去掉的交替底色是同一类“看花眼”（用户反馈）。
  // 规则：交易日与交易日之间的分界总是画（多天视图里唯一有用的分界）；一个交易日内部的三条分界，
  // 只有前后两段都够宽（能写下段名）时才画，放大到一两天后它们就都回来了。
  const sepLines = []
  for (let i = 0; i < segments.length - 1; i++) {
    const prev = segments[i]
    const next = segments[i + 1]
    const x = (prev.x1 + next.x0) / 2
    if (range && (x < range[0] || x > range[1])) continue
    const betweenDays = prev.day !== next.day
    if (!betweenDays && !(names.has(i) && names.has(i + 1))) continue
    // 竖线用“两个端点”的写法，显式指定从 y 轴最小值画到最大值。
    // 单点写法 { xAxis: x } 理论上会贯穿整个绘图区，但缩放后实际只画了下半截（顶端落在 +68,000 上下，
    // 既不是曲线最高点也不是图顶，已截图验证），原因没有查清；显式指定两端点就不依赖这个默认行为。
    // 颜色用不透明的实色，不用半透明：半透明的虚线叠在“曲线下方的面积填充”和“纯深蓝背景”两种底色上，
    // 上半段（纯深蓝）的对比度只有下半段的三分之一（实测亮度差 15 vs 45），肉眼看起来像只画了一半。
    sepLines.push([
      { xAxis: x, yAxis: yMin, lineStyle: { color: chartColors().muted, type: 'dashed', width: 1 } },
      { xAxis: x, yAxis: yMax }
    ])
  }
  return {
    xAxis: {
      // 刻度线和标签各自读取 customValues，两处都要设
      axisTick: { customValues: ticks },
      axisLabel: { customValues: ticks, formatter: (v) => labels.get(v) ?? '' }
    },
    areas,
    sepLines
  }
}

function timeAxisOptions(points, xs, segments, details, openMarks, plotWidthPx, yMin, yMax) {
  const view = viewDependentOptions(segments, plotWidthPx, null, yMin, yMax)
  const areas = view.areas
  const sepLines = view.sepLines
  return {
    xAxis: {
      type: 'value',
      // 不设轴名：刻度本身就是时间（21:00、09:00、10:15……），每段还有段名、每个交易日有日期，“交易时间”是冗余信息。
      // 而且这块区域没有给它留位置：放在右端被边缘裁掉，放在最左端和 y 轴的 0 刻度挤在一起（看着像“0 交易时间”），
      // 居中又压在缩放滑块上（三次截图都验证过），所以去掉
      min: segments[0].x0 - 2,
      max: segments[segments.length - 1].x1 + 1,
      axisLine: { lineStyle: { color: chartColors().axisLineSoft } },
      axisTick: { show: true, ...view.xAxis.axisTick },
      splitLine: { show: false },
      // 十字线的竖线：不吸附交易点，连续地跟着鼠标走；X 轴上的标签显示这个位置的真实时间，精确到秒。
      // snap 必须写在轴自己的 axisPointer 里：tooltip.axisPointer.snap 对“触发提示框的那根轴”无效，
      // ECharts 在 modelHelper.js 里把它写死成 value 轴 + 触发提示框 = true，轴自己的配置才能覆盖它。
      // 1 秒 = 1/60 个轴单位，竖线本身是连续的（一秒不到一个像素），秒级的颗粒度体现在标签上
      axisPointer: {
        snap: false,
        label: {
          formatter: (p) => {
            const t = axisTimeAt(segments, Number(p.value))
            return t ? fmtMDHMS(t) : ''
          }
        }
      },
      axisLabel: {
        color: chartColors().text,
        ...view.xAxis.axisLabel,
        // 不用 hideOverlap：标签是否重叠由 buildSessionTicks 按可见范围的像素预算负责，
        // 交界处的两个时间合并成了一个标签（10:15 | 10:30），不会再互相叠在一起
        hideOverlap: false,
        rich: {
          h: { color: chartColors().text, fontSize: 11, lineHeight: 16 },
          d: { color: chartColors().textStrong, fontSize: 11, lineHeight: 16 },
          // 交界标签写成“终点（黄）| 起点（蓝）”，三个片段在同一个文本块里从左到右排，不依赖任何对齐。
          // （之前用 align 左右错开没有效果：rich 里的 align 只控制文字在文本块内部靠哪边）
          s: { color: chartColors().sky, fontSize: 11, lineHeight: 16 },
          e: { color: chartColors().amber, fontSize: 11, lineHeight: 16 },
          sep: { color: chartColors().muted, fontSize: 11, lineHeight: 16 }
        }
      }
    },
    tooltipFormatter: (items) => {
      if (!items || !items.length) return ''
      // 十字线跟着鼠标走（可以停在任意横坐标，不吸附交易点），但只有鼠标靠近某个交易点的横坐标时才弹出详情。
      // 鼠标所在的横坐标不能取 items[0].axisValue：它始终是吸附到最近数据点的值，用它判断“靠近”永远成立。
      // 改用 DOM 监听记下的鼠标真实像素位置，再换算成轴值。
      if (mouseOffsetX < 0 || !chart) return ''
      const mouseX = chart.convertFromPixel({ xAxisIndex: 0 }, mouseOffsetX)
      if (!Number.isFinite(mouseX)) return ''
      // 在“可见范围”内按像素判断是否靠近：放大后同样的像素距离对应更小的横坐标差
      const dz = chart?.getOption()?.dataZoom?.[0]
      const vx0 = dz?.startValue ?? segments[0].x0
      const vx1 = dz?.endValue ?? segments[segments.length - 1].x1
      const pxPerUnit = plotWidthPx / Math.max(vx1 - vx0, 1)
      // 鼠标附近（HOVER_NEAR_PX 像素内）的开仓点和平仓点都列出来，各自按真实成交时间排列。
      // 同一时刻、不同合约（或买卖方向不同）的几笔成交不合并，它们的横坐标完全相同；
      // 被归入最近时段的成交（集合竞价、夜盘延续到凌晨等）在轴上贴着段的边界，同一个边界上也可能叠着不同时刻的几笔，
      // 所以不是只取最近的一个点，而是把范围内的全部列出来。
      const near = (x) => Math.abs(x - mouseX) * pxPerUnit <= HOVER_NEAR_PX
      const same = []
      for (let j = 1; j < xs.length; j++) if (near(xs[j])) same.push(j)
      const opensNear = openMarks.filter((m) => near(m.x))
      if (!same.length && !opensNear.length) return ''
      const openBlock = (m) => {
        return `<div style="font-weight:bold;margin-bottom:4px">${fmtFull(m.time)}</div>
              <div>${m.symbol} ${m.direction}开 ${m.lots} 手 @ ${m.price}</div>`
      }
      const block = (i) => {
        const d = details[i]
        const value = points[i][1]
        const tc = chartColors()
        const color = value > 0 ? '#ef4444' : value < 0 ? '#22c55e' : tc.neutral
        const pc = d.pnl > 0 ? '#ef4444' : d.pnl < 0 ? '#22c55e' : tc.neutral
        return `<div style="font-weight:bold;margin-bottom:4px">${fmtFull(d.time)}</div>
              <div>${d.symbol} ${d.direction}平 ${d.lots} 手 @ ${d.price}</div>
              <div>本笔盈亏：<b style="color:${pc}">${money(d.pnl)}</b></div>
              <div style="color:${tc.text}">手续费：${plain(d.fee)}</div>
              <div>累计盈亏：<b style="color:${color}">${money(value)}</b></div>`
      }
      const blocks = [
        ...opensNear.map((m) => ({ time: m.time, html: openBlock(m) })),
        ...same.map((i) => ({ time: details[i].time, html: block(i) }))
      ].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0))
      const head = blocks.length > 1 ? `<div style="color:${chartColors().amber};margin-bottom:6px">此位置共 ${blocks.length} 笔成交</div>` : ''
      return head + blocks.map((b) => b.html).join(`<div style="height:1px;background:${chartColors().divider};margin:6px 0"></div>`)
    },
    areas,
    sepLines,
    // 相邻两笔之间直接用斜线连接，每个拐点都落在一笔真实的平仓上。
    // 不用阶梯线（只有水平和垂直，看不出盈亏的变化趋势），也不用平滑曲线（会在拐点处画出数据里不存在的弧形和超调）
    seriesExtra: {}
  }
}

// 曲线上的点 = 开仓点 + 平仓点，按横坐标从左到右排好，相邻点之间用直线连接。
// 规则：
//  - 空仓时（总持仓为 0）曲线是水平的，保持上一次平仓后的累计盈亏；
//  - 从空仓到第一笔开仓，这个开仓点是“起点”，纵坐标 = 当前累计盈亏；从这里开始曲线不再水平，
//    直线连到下一个平仓点（累计盈亏变成平仓后的新值）；
//  - 持仓期间夹在中间的其它开仓点不改变这条直线，只是标在直线上（纵坐标按直线插值）；
//  - 平仓后如果仍有持仓，这个平仓点就是下一段直线的起点；平仓后空仓，之后又是水平线。
// 持仓量按合约统计：开仓手数 - 平仓手数（details / openMarks 里的手数都是合并后的成交手数，和方向无关）。
// 横坐标相同时开仓排在平仓前面（同一时刻先开后平）。
// 开仓点画成空心圆（和平仓点的实心红绿圆区分），端点和轴两端补的水平延长线不画圆点。
function buildSeriesData(points, xs, details, openMarks, axisMin, axisMax) {
  // kind: 0 = 开仓，1 = 平仓（同 x 时开仓在前）
  const events = []
  openMarks.forEach((m, i) => events.push({ x: m.x, kind: 0, symbol: m.symbol, lots: m.lots, t: m.time, order: i }))
  for (let i = 1; i < points.length; i++) {
    events.push({ x: xs[i], kind: 1, symbol: details[i].symbol, lots: details[i].lots, t: details[i].time, y: points[i][1], order: i })
  }
  events.sort((a, b) => a.x - b.x || a.kind - b.kind || (a.t < b.t ? -1 : a.t > b.t ? 1 : 0) || a.order - b.order)

  const held = {}   // 合约 -> 持仓手数
  const total = () => Object.values(held).reduce((s, v) => s + Math.max(v, 0), 0)
  // 每个事件的纵坐标：先记下“锚点”（上一段直线的起点），遇到平仓时回填这一段里的开仓点
  const ys = new Array(events.length)
  let cum = 0                 // 已实现的累计盈亏（空仓时曲线停在这里）
  let anchor = null           // 当前这段直线的起点 { idx, x, y }
  let pendingOpens = []       // 这段直线上、还没有确定纵坐标的开仓点下标
  events.forEach((e, idx) => {
    if (e.kind === 0) {
      held[e.symbol] = (held[e.symbol] || 0) + e.lots
      if (!anchor) {
        anchor = { x: e.x, y: cum }
        ys[idx] = cum
      } else {
        pendingOpens.push(idx)
      }
      return
    }
    // 平仓：纵坐标就是平仓后的累计盈亏；把这一段里夹着的开仓点按直线插值回填
    held[e.symbol] = (held[e.symbol] || 0) - e.lots
    const y = e.y
    if (anchor) {
      const span = e.x - anchor.x
      for (const k of pendingOpens) {
        const r = span > 1e-9 ? (events[k].x - anchor.x) / span : 1
        ys[k] = anchor.y + (y - anchor.y) * r
      }
    }
    pendingOpens = []
    ys[idx] = y
    cum = y
    // 平仓后仍有持仓：这个平仓点是下一段直线的起点；否则回到空仓
    anchor = total() > 1e-9 ? { x: e.x, y } : null
  })
  // 文件结束时还没平掉的开仓：没有对应的平仓，只能停在当前累计值上
  for (const k of pendingOpens) ys[k] = cum

  const data = [{ value: [axisMin, 0], symbolSize: 0 }]
  events.forEach((e, idx) => {
    if (e.kind === 1) {
      data.push([e.x, ys[idx]])
    } else {
      // 开仓点：空心圆。itemStyle 的 color 覆盖 visualMap，边框用金色，避免和红绿平仓点混淆
      data.push({
        value: [e.x, ys[idx]],
        symbol: 'circle',
        symbolSize: 8,
        itemStyle: { color: chartColors().bg, borderColor: chartColors().amber, borderWidth: 2 }
      })
    }
  })
  data.push({ value: [axisMax, cum], symbolSize: 0 })
  return data
}

function renderChart() {
  if (!chart) return
  const points = props.curve?.points || []
  const xs = props.curve?.xs || []
  const segments = props.curve?.segments || []
  const details = props.curve?.details || []
  const { min, max } = valueRange(points)
  // 没有数据（还没导入、或筛选后没有平仓）：清空图表，不要拿空数组去算坐标
  if (!points.length) {
    chart.clear()
    return
  }
  // 绘图区的实际宽度（图表宽度减去左右留白），用来决定能放下多少个 X 轴标签
  const plotWidthPx = Math.max(200, chart.getWidth() - 70 - 56)
  currentSegments = segments
  const mode = timeAxisOptions(points, xs, segments, details, props.curve?.openMarks || [], plotWidthPx, min, max)
  // 与 timeAxisOptions 里 x 轴的 min / max 保持一致：曲线从轴的最左端画到最右端
  const axisMin = segments[0].x0 - 2
  const axisMax = segments[segments.length - 1].x1 + 1
  const c = chartColors()
  chart.setOption(
    {
      backgroundColor: c.bg,
      animation: points.length < 5000,
      // bottom 要给 x 轴标签（序号 + 日期两行）和下方的缩放滑块都留出位置
      // top 30 -> 40：y 轴标题「累计盈亏（元）」随绘图区下移，它上方多留 10px
      grid: { left: 70, right: 56, top: 40, bottom: 96 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        backgroundColor: c.tooltipBg,
        borderColor: c.accent,
        textStyle: { color: c.tooltipText },
        formatter: mode.tooltipFormatter
      },
      xAxis: mode.xAxis,
      visualMap: pnlVisualMap(),
      yAxis: {
        type: 'value',
        name: '累计盈亏（元）',
        nameTextStyle: { color: c.text },
        min,
        max,
        axisLine: { show: true, lineStyle: { color: c.axisLineSoft } },
        axisLabel: { color: c.text, formatter: (v) => v.toLocaleString('zh-CN') },
        splitLine: { lineStyle: { color: c.splitLineSoft } }
      },
      // 默认显示全部数据（不设初始窗口）；数据多时可以用滚轮缩放、拖动滑块查看局部。
      // filterMode: 'none'：默认的 'filter' 会把窗口外的点直接丢掉，缩放后窗口左侧进入的那条线也就没了，
      // 只剩几个孤零零的点（已用像素统计验证）。保留全部点，ECharts 只裁剪画不进窗口的部分。
      // y 轴范围已由 valueRange 按全部点固定，所以不会因为不过滤而乱跳。
      dataZoom: [
        { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
        {
          type: 'slider',
          xAxisIndex: 0,
          filterMode: 'none',
          height: 24,
          bottom: 20,
          borderColor: c.sliderBorder,
          textStyle: { color: c.text }
        }
      ],
      series: [
        {
          name: '累计盈亏',
          type: 'line',
          ...mode.seriesExtra,
          // 圆点由 buildSeriesData 按点单独设置（开仓空心、平仓实心）；成交太多时全部隐藏，避免糊成一片
          showSymbol: points.length + (props.curve?.openMarks?.length || 0) <= 300,
          symbolSize: 6,
          // 线和数据点的红绿由上面的 visualMap 按“值”决定。
          // 面积填充不做红绿分界：面积的渐变也是按它自己的包围盒定位，红绿分界会落在错误的高度（已截图验证），
          // 所以面积只用一层中性色，由线条本身表达盈亏方向。
          lineStyle: { width: 2 },
          areaStyle: { color: c.area, origin: 0 },
          // 横坐标用固定四段交易时间里的位置（xs），而不是真实时间戳。
          // 曲线要覆盖整条时间轴：开头补一个累计 0 的点（轴的最左端），结尾补一个与最后一笔累计盈亏相同的点（轴的最右端），
          // 第一笔之前、最后一笔之后没有交易的时间段就是水平线。补的点只用于画线，不显示圆点，悬停详情也不使用它们。
          data: buildSeriesData(points, xs, details, props.curve?.openMarks || [], axisMin, axisMax),
          // 每一段的段名（夜盘 / 早盘一 / 早盘二 / 午盘），不画底色
          markArea: { silent: true, data: mode.areas },
          markLine: {
            silent: true,
            symbol: 'none',
            label: { show: false },
            lineStyle: { color: chartColors().text, type: 'dashed' },
            // 0 线 + 段与段之间（休息时间）的竖向虚线
            data: [{ yAxis: 0 }, ...mode.sepLines]
          }
        }
      ]
    },
    true
  )
}

const handleResize = () => chart && chart.resize()

// 主题切换：颜色分散在多个辅助函数里，直接整体重绘；重绘前记下缩放窗口，重绘后恢复
onThemeChange(() => {
  if (!chart || !props.curve?.points?.length) return
  const dz = chart.getOption().dataZoom?.[0]
  renderChart()
  if (dz?.startValue != null && dz?.endValue != null) {
    chart.dispatchAction({ type: 'dataZoom', startValue: dz.startValue, endValue: dz.endValue })
  }
})

// 曲线数据变了（重新取了数据、筛选变了、过期被清空）就重画。数据先到、图表可能还没初始化（组件刚挂载），
// 所以没有图表时先初始化；画之前等一个 tick，让空状态 / 加载遮罩的 DOM 先更新完
watch(() => props.curve, async () => {
  await nextTick()
  try {
    if (!chart) initChart()
    else renderChart()
  } catch (renderError) {
    // 数据已经取到了，绘图出错不能被当成“获取曲线失败”（网络错误）报给用户
    console.error('[ReviewFunding] 绘制盈亏曲线失败', renderError)
    emit('error', '图表绘制失败，请重试；如果反复出现，请把导入的文件反馈给开发者')
  }
})

// 父组件从别的标签切回来时调用：图表容器之前被 display:none 隐藏过，尺寸要重新量一次
function resize() {
  chart && chart.resize()
}
defineExpose({ resize })

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartRef.value?.removeEventListener('mousemove', onDomMouseMove, true)
  chartRef.value?.removeEventListener('mouseleave', onDomMouseLeave, true)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
/* 空状态 / 加载中 / 图表容器的样式和复盘页共用同一份 */
@import '@/styles/Review.css';
</style>
