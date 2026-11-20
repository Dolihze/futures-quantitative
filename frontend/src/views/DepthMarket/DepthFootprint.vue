<template>
  <div ref="wrapRef" class="footprint" @mouseleave="onLeave">
    <canvas
      ref="canvasRef"
      class="footprint-canvas"
      @wheel.prevent="onWheel"
      @mousedown="onDown"
      @mousemove="onMove"
      @click="onClick"
    ></canvas>

    <!-- 悬停信息：固定在左上角，不跟随鼠标 -->
    <div v-if="hoverInfo" class="fp-info">
      <span class="info-time">{{ hoverInfo.time }}</span>
      <template v-if="hoverInfo.level">
        <span>价位 <b>{{ hoverInfo.level.price }}</b></span>
        <span>卖 <b class="down">{{ fmt(hoverInfo.level.sell) }}</b></span>
        <span>买 <b class="up">{{ fmt(hoverInfo.level.buy) }}</b></span>
        <span v-if="hoverInfo.level.neutral">中性 <b>{{ fmt(hoverInfo.level.neutral) }}</b></span>
      </template>
      <template v-else-if="hoverInfo.bar">
        <span>开 <b>{{ hoverInfo.bar.open }}</b></span>
        <span>高 <b>{{ hoverInfo.bar.high }}</b></span>
        <span>低 <b>{{ hoverInfo.bar.low }}</b></span>
        <span>收 <b>{{ hoverInfo.bar.close }}</b></span>
        <span>量 <b>{{ hoverInfo.bar.volume }}</b></span>
      </template>
      <span v-if="hoverInfo.big" class="info-big">
        大单 {{ hoverInfo.big.volume }} 手
        <template v-if="hoverInfo.big.count > 1">（{{ hoverInfo.big.count }} 笔：{{ hoverInfo.big.bsList.join('、') }}）</template>
        <template v-else>{{ hoverInfo.big.bs }}</template>
        @ {{ hoverInfo.big.price }}
      </span>
    </div>

    <div class="fp-legend">
      <span><i class="lg sell"></i>卖方主动</span>
      <span><i class="lg buy"></i>买方主动</span>
      <span><i class="lg big"></i>大单 ≥ {{ bigOrder }} 手</span>
      <span class="fp-hint">滚轮缩放 · 拖动平移 · Shift+滚轮纵向缩放</span>
    </div>

    <div v-if="!bars.length" class="chart-empty">
      <div class="empty-icon">👣</div>
      <div class="empty-title">{{ emptyTitle }}</div>
      <div class="empty-desc">{{ emptyDesc }}</div>
    </div>
    <div v-if="loading" class="chart-loading">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在生成足迹图...</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { chartColors, onThemeChange } from '@/utils/chartTheme'

const props = defineProps({
  // 后端 footprint 的 bars：[{ time, open, high, low, close, volume, levels: [{price, buy, sell, neutral}] }]
  bars: { type: /** @type {import('vue').PropType<import('@/api/types').DepthFootprintBar[]>} */ (Array), default: () => [] },
  // 大单列表：[{ bar, index, price, volume, side, bs }]。阈值过滤在前端做，调阈值不用重新请求
  bigOrders: { type: /** @type {import('vue').PropType<import('@/api/types').DepthBigOrder[]>} */ (Array), default: () => [] },
  bigOrder: { type: Number, default: 100 },     // 大单阈值（手）
  tickSize: { type: Number, default: 1 },       // 最小价位间隔
  loading: { type: Boolean, default: false },
  selectedIndex: { type: Number, default: -1 },
  emptyTitle: { type: String, default: '还没有数据' },
  emptyDesc: { type: String, default: '先在左侧导入历史 tick CSV' }
})
const emit = defineEmits(['hover', 'select'])

// 红涨绿跌：买方主动红、卖方主动绿（与全站一致）
const UP = '#dc2626'
const DOWN = '#16a34a'
const BIG = '#a855f7'

const wrapRef = ref(null)
const canvasRef = ref(null)
let ctx = null
let dpr = 1
let width = 0
let height = 0
let resizeObserver = null
let raf = 0

// ---------- 视图状态 ----------
// colW：每根 K 线的列宽（像素）；rowH：每个价位的行高（像素）；
// offsetX：第 0 根 K 线左边缘相对画布的像素；priceTop：画布顶部对应的价格
const view = { colW: 96, rowH: 18, offsetX: 0, priceTop: 0 }
const PAD = { left: 8, right: 64, top: 30, bottom: 26 }   // 右侧留给价格轴，底部给时间轴

const hoverInfo = ref(null)
const bigOrder = computed(() => props.bigOrder)
const fmt = (v) => (v == null ? '--' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 }))

// 价位 -> 每根 K 线 levels 的快速查找：[{ price: level }, ...]，只在 bars 变化时构建一次
let levelMaps = []
let priceMin = 0
let priceMax = 0
let globalMaxVol = 1      // 全局单价位最大成交量，色块深浅按它归一化（每根 K 线内部归一会让小量 K 线也很深，误导）

function prepare() {
  levelMaps = []
  let lo = Infinity
  let hi = -Infinity
  let mx = 1
  for (const b of props.bars) {
    const m = new Map()
    for (const lv of b.levels || []) {
      m.set(lv.price, lv)
      const t = (lv.buy || 0) + (lv.sell || 0) + (lv.neutral || 0)
      if (t > mx) mx = t
    }
    levelMaps.push(m)
    if (b.low < lo) lo = b.low
    if (b.high > hi) hi = b.high
  }
  priceMin = Number.isFinite(lo) ? lo : 0
  priceMax = Number.isFinite(hi) ? hi : 0
  globalMaxVol = mx
}

// 大单按所在 K 线分组（只含 >= 当前阈值的）
let bigByBar = new Map()
function prepareBig() {
  // 同一根 K 线、同一价位的多笔大单合并成一个圆圈：手数相加、方向取手数多的一方，count 记笔数。
  // 否则圆圈互相覆盖，数字叠在一起看不清；合并后详情仍可在悬停信息里看到「N 笔」
  const merged = new Map()
  for (const o of props.bigOrders) {
    if (o.volume < props.bigOrder) continue
    const key = `${o.bar}|${o.price}`
    const m = merged.get(key)
    if (!m) {
      merged.set(key, { ...o, count: 1, buyVol: o.side > 0 ? o.volume : 0, sellVol: o.side < 0 ? o.volume : 0, bsList: [o.bs] })
    } else {
      m.volume += o.volume
      m.count += 1
      if (o.side > 0) m.buyVol += o.volume
      if (o.side < 0) m.sellVol += o.volume
      m.bsList.push(o.bs)
      m.side = m.buyVol > m.sellVol ? 1 : m.sellVol > m.buyVol ? -1 : 0
    }
  }
  bigByBar = new Map()
  for (const o of merged.values()) {
    if (!bigByBar.has(o.bar)) bigByBar.set(o.bar, [])
    bigByBar.get(o.bar).push(o)
  }
}

// 初始视图：横向显示最后若干根，纵向让最后一根 K 线的价格区间居中
function fitView() {
  const n = props.bars.length
  if (!n || !width) return
  const ts = props.tickSize || 1
  view.rowH = 18
  view.colW = 96
  const plotW = width - PAD.left - PAD.right
  const visible = Math.max(1, Math.floor(plotW / view.colW))
  view.offsetX = PAD.left - Math.max(0, n - visible) * view.colW
  const last = props.bars[n - 1]
  const mid = (last.high + last.low) / 2
  const plotH = height - PAD.top - PAD.bottom
  view.priceTop = snapTop(mid + (plotH / 2 / view.rowH) * ts)
}

// 吸附到价位：保证每一行恰好对应一个价位（行的上边缘 = 价位 + 半格不会出现）。
// 纵向平移 / 缩放产生的任意浮点 priceTop 必须经过它，否则格子和价格会错位。
function snapTop(price) {
  const ts = props.tickSize || 1
  return Math.round(Math.round(price / ts) * ts * 1e6) / 1e6
}

// ---------- 坐标换算 ----------
const rowsOf = (p) => (view.priceTop - p) / (props.tickSize || 1)          // 价格 -> 距顶部的行数
const yOfPrice = (p) => PAD.top + rowsOf(p) * view.rowH                    // 价位格子的上边缘（该价位占 [y, y+rowH]）
const xOfBar = (i) => view.offsetX + i * view.colW

function barAt(x) {
  const i = Math.floor((x - view.offsetX) / view.colW)
  return i >= 0 && i < props.bars.length ? i : -1
}
function priceAt(y) {
  const ts = props.tickSize || 1
  return Math.round((view.priceTop - Math.floor((y - PAD.top) / view.rowH) * ts) * 1e6) / 1e6
}

// 大单圆圈半径：随手数平方根增长，上限为列宽的 0.48，下限 8px。绘制和悬停命中检测共用，保证一致
function bigRadius(o) {
  // 基础半径 = 半行高；手数越大越大（平方根缩放），但封顶 0.95 行高：相邻价位各画一个圆也不会互相压住
  const base = view.rowH * 0.5
  const extra = Math.sqrt(o.volume / props.bigOrder) * view.rowH * 0.12
  return Math.max(5, Math.min(view.rowH * 0.95, view.colW * 0.3, base + extra))
}

// 圆心 x：放在列的右侧边缘附近（买量数字在右半格靠中线，卖量在左半格靠中线，列边缘一般是空的），
// 这样圆圈不会盖住价位格子里的数字
function bigCenterX(i, r) {
  return xOfBar(i) + view.colW - r - 3
}

// ---------- 绘制 ----------
function schedule() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    draw()
  })
}

function draw() {
  if (!ctx || !width) return
  const c = chartColors()
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.fillStyle = c.bg
  ctx.fillRect(0, 0, width, height)
  const n = props.bars.length
  if (!n) return

  const ts = props.tickSize || 1
  const plotLeft = PAD.left
  const plotRight = width - PAD.right
  const plotTop = PAD.top
  const plotBottom = height - PAD.bottom

  // 可见范围
  const i0 = Math.max(0, Math.floor((plotLeft - view.offsetX) / view.colW))
  const i1 = Math.min(n - 1, Math.floor((plotRight - view.offsetX) / view.colW))
  const pTop = view.priceTop
  const pBottom = view.priceTop - ((plotBottom - plotTop) / view.rowH) * ts

  // 缩放程度决定细节：格子够大才画数字
  const showNumbers = view.rowH >= 11 && view.colW >= 56
  const showBars = view.colW >= 30

  ctx.save()
  ctx.beginPath()
  ctx.rect(plotLeft, plotTop, plotRight - plotLeft, plotBottom - plotTop)
  ctx.clip()

  // 横向网格线（价位分隔）：只在行够高时画，避免缩小后一片线
  if (view.rowH >= 8) {
    ctx.strokeStyle = c.splitLine
    ctx.lineWidth = 1
    ctx.beginPath()
    const startRow = Math.max(0, Math.floor(rowsOf(pTop)))
    for (let r = startRow; ; r++) {
      const price = view.priceTop - r * ts
      const y = Math.round(yOfPrice(price) + view.rowH) + 0.5
      if (y > plotBottom) break
      ctx.moveTo(plotLeft, y)
      ctx.lineTo(plotRight, y)
    }
    ctx.stroke()
  }

  ctx.font = `${Math.min(12, Math.max(9, view.rowH - 3))}px "Consolas", "Microsoft YaHei", monospace`
  ctx.textBaseline = 'middle'

  for (let i = i0; i <= i1; i++) {
    const bar = props.bars[i]
    const x = xOfBar(i)
    const w = view.colW
    const map = levelMaps[i]
    const isSel = i === props.selectedIndex

    // 选中列高亮背景
    if (isSel) {
      ctx.fillStyle = `rgba(${c.accentRgb}, 0.10)`
      ctx.fillRect(x, plotTop, w, plotBottom - plotTop)
    }

    // 这根 K 线的价位格子
    const colPad = 2
    const half = (w - colPad * 2) / 2
    for (const lv of bar.levels || []) {
      if (lv.price > pTop + ts || lv.price < pBottom - ts) continue
      const y = yOfPrice(lv.price)
      const h = view.rowH
      const buy = lv.buy || 0
      const sell = lv.sell || 0
      const neu = lv.neutral || 0
      const total = buy + sell + neu

      if (showBars) {
        // 左半边卖（绿），右半边买（红）：深浅 = 该价位量 / 全局最大价位量
        if (sell > 0) {
          ctx.fillStyle = `rgba(22, 163, 74, ${0.12 + 0.6 * Math.min(1, sell / globalMaxVol)})`
          ctx.fillRect(x + colPad, y + 1, half, h - 1)
        }
        if (buy > 0) {
          ctx.fillStyle = `rgba(220, 38, 38, ${0.12 + 0.6 * Math.min(1, buy / globalMaxVol)})`
          ctx.fillRect(x + colPad + half, y + 1, half, h - 1)
        }
      } else if (total > 0) {
        // 很窄时只画一个整体色块：买多偏红、卖多偏绿
        const dom = buy >= sell ? '220, 38, 38' : '22, 163, 74'
        ctx.fillStyle = `rgba(${dom}, ${0.15 + 0.6 * Math.min(1, total / globalMaxVol)})`
        ctx.fillRect(x, y + 1, w - 1, h - 1)
      }

      if (showNumbers) {
        ctx.fillStyle = c.textStrong
        ctx.textAlign = 'right'
        if (sell > 0) ctx.fillText(String(sell), x + colPad + half - 3, y + h / 2 + 0.5)
        ctx.textAlign = 'left'
        if (buy > 0) ctx.fillText(String(buy), x + colPad + half + 3, y + h / 2 + 0.5)
      }
    }

    // K 线的开收价标记：用细竖线贴在列的左右边缘区分涨跌（不遮挡价位数字）
    const up = bar.close >= bar.open
    ctx.strokeStyle = up ? UP : DOWN
    ctx.lineWidth = 2
    const yHigh = yOfPrice(bar.high)
    const yLow = yOfPrice(bar.low) + view.rowH
    ctx.beginPath()
    ctx.moveTo(x + 0.5, yHigh)
    ctx.lineTo(x + 0.5, yLow)
    ctx.stroke()

    // 列分隔线
    ctx.strokeStyle = c.axisLine
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(Math.round(x + w) + 0.5, plotTop)
    ctx.lineTo(Math.round(x + w) + 0.5, plotBottom)
    ctx.stroke()
  }

  // 大单圆圈：画在对应 K 线列、对应价位格子的中心；半径随手数增大（平方根缩放），圈内写手数
  for (let i = i0; i <= i1; i++) {
    const list = bigByBar.get(i)
    if (!list) continue
    const x = xOfBar(i)
    for (const o of list) {
      const cy = yOfPrice(o.price) + view.rowH / 2
      if (cy < plotTop - 40 || cy > plotBottom + 40) continue
      const r = bigRadius(o)
      const cx = bigCenterX(i, r)
      const color = o.side > 0 ? UP : o.side < 0 ? DOWN : BIG
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fillStyle = hexA(BIG, 0.28)
      ctx.fill()
      ctx.lineWidth = 1.5
      ctx.strokeStyle = color
      ctx.stroke()
      if (r >= 9) {
        ctx.textAlign = 'center'
        ctx.font = `bold ${Math.min(12, Math.max(8, r * 0.85))}px "Consolas", monospace`
        // 深色描边 + 白字：叠在红绿色块上也清楚
        ctx.lineWidth = 2.5
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.8)'
        ctx.strokeText(String(o.volume), cx, cy + 0.5)
        ctx.fillStyle = '#ffffff'
        ctx.fillText(String(o.volume), cx, cy + 0.5)
      }
    }
  }
  ctx.restore()

  drawAxes(c, i0, i1, pTop, pBottom)
}

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}

// 价格轴（右）+ 时间轴（下）
function drawAxes(c, i0, i1, pTop, pBottom) {
  const ts = props.tickSize || 1
  const plotRight = width - PAD.right
  const plotTop = PAD.top
  const plotBottom = height - PAD.bottom

  ctx.fillStyle = c.bg
  ctx.fillRect(plotRight, 0, PAD.right, height)
  ctx.fillRect(0, plotBottom, width, PAD.bottom)

  // 价格轴：行太密时隔几行标一次
  ctx.fillStyle = c.axisLabel
  ctx.font = '11px "Consolas", monospace'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  const step = Math.max(1, Math.ceil(14 / view.rowH))
  const startRow = Math.max(0, Math.floor(rowsOf(pTop)))
  for (let r = startRow; ; r++) {
    const price = Math.round((view.priceTop - r * ts) * 1e6) / 1e6
    const y = yOfPrice(price) + view.rowH / 2
    if (y > plotBottom) break
    if (r % step !== 0 || y < plotTop) continue
    ctx.fillText(price.toFixed(priceDigits()), plotRight + 6, y)
  }

  // 时间轴：列够宽时每根标，否则隔几根标
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  const every = Math.max(1, Math.ceil(54 / view.colW))
  const multiDay = new Set(props.bars.map((b) => b.time.slice(0, 10))).size > 1
  for (let i = i0; i <= i1; i++) {
    if (i % every !== 0) continue
    const t = props.bars[i].time
    const label = t.length <= 10 ? t : multiDay ? t.slice(5) : t.slice(11)
    ctx.fillText(label, xOfBar(i) + view.colW / 2, plotBottom + 6)
  }

  // 轴与绘图区之间的分隔线
  ctx.strokeStyle = c.axisLine
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(0, plotBottom + 0.5)
  ctx.lineTo(width, plotBottom + 0.5)
  ctx.moveTo(plotRight + 0.5, 0)
  ctx.lineTo(plotRight + 0.5, height)
  ctx.stroke()
}

// ---------- 交互 ----------
function clampView() {
  const n = props.bars.length
  if (!n) return
  const ts = props.tickSize || 1
  const plotH = height - PAD.top - PAD.bottom
  // 横向：至少留一根 K 线在可视区
  const minOffset = PAD.left + 40 - n * view.colW
  const maxOffset = width - PAD.right - 40
  view.offsetX = Math.min(maxOffset, Math.max(minOffset, view.offsetX))
  // 纵向：价格区间至少有一部分在可视区
  const visibleRows = plotH / view.rowH
  const top = Math.max(view.priceTop, priceMin)
  view.priceTop = Math.min(top, priceMax + visibleRows * ts * 0.9)
  view.priceTop = Math.max(view.priceTop, priceMin + visibleRows * ts * 0.1)
  view.priceTop = snapTop(view.priceTop)
}

function onWheel(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
  if (e.shiftKey) {
    // 纵向缩放：以鼠标所在价格为锚点
    const ts = props.tickSize || 1
    const anchorPrice = view.priceTop - ((my - PAD.top) / view.rowH) * ts
    view.rowH = Math.min(60, Math.max(3, view.rowH * factor))
    view.priceTop = anchorPrice + ((my - PAD.top) / view.rowH) * ts
  } else {
    // 横向缩放：以鼠标所在 K 线为锚点
    const anchorBar = (mx - view.offsetX) / view.colW
    view.colW = Math.min(240, Math.max(6, view.colW * factor))
    view.offsetX = mx - anchorBar * view.colW
  }
  clampView()
  schedule()
}

let dragging = null
let moved = false
function onDown(e) {
  dragging = { x: e.clientX, y: e.clientY, ox: view.offsetX, pt: view.priceTop }
  moved = false
  window.addEventListener('mouseup', onUp)
}
function onUp() {
  dragging = null
  window.removeEventListener('mouseup', onUp)
}

function onMove(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  if (dragging) {
    const dx = e.clientX - dragging.x
    const dy = e.clientY - dragging.y
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true
    view.offsetX = dragging.ox + dx
    view.priceTop = dragging.pt + (dy / view.rowH) * (props.tickSize || 1)
    clampView()
    schedule()
    return
  }
  updateHover(mx, my)
}

function updateHover(mx, my) {
  const plotRight = width - PAD.right
  if (mx < PAD.left || mx > plotRight || my < PAD.top || my > height - PAD.bottom) {
    setHover(null, -1)
    return
  }
  const bi = barAt(mx)
  if (bi < 0) {
    setHover(null, -1)
    return
  }
  const bar = props.bars[bi]
  const price = priceAt(my)
  const level = levelMaps[bi]?.get(price) || null
  // 鼠标在大单圆圈内：显示大单详情
  let big = null
  const list = bigByBar.get(bi)
  if (list) {
    for (const o of list) {
      const cy = yOfPrice(o.price) + view.rowH / 2
      const r = bigRadius(o)
      const cx = bigCenterX(bi, r)
      if ((mx - cx) ** 2 + (my - cy) ** 2 <= r * r) { big = o; break }
    }
  }
  setHover({ time: bar.time, bar, level: level ? { ...level, price } : (price >= bar.low && price <= bar.high ? { price, buy: 0, sell: 0, neutral: 0 } : null), big }, bi)
}

function setHover(info, bi) {
  hoverInfo.value = info
  emit('hover', bi)
}

// 价格显示的小数位数：由 tickSize 决定（1 -> 0 位，0.5 -> 1 位，0.05 -> 2 位）
function priceDigits() {
  const ts = props.tickSize || 1
  let d = 0
  while (d < 6 && Math.abs(ts * 10 ** d - Math.round(ts * 10 ** d)) > 1e-9) d++
  return d
}

function onLeave() {
  setHover(null, -1)
}

function onClick(e) {
  if (moved) return   // 拖动结束不算点击
  const rect = canvasRef.value.getBoundingClientRect()
  const bi = barAt(e.clientX - rect.left)
  if (bi >= 0) emit('select', bi)
}

// ---------- 生命周期 ----------
function resize() {
  const el = wrapRef.value
  const cv = canvasRef.value
  if (!el || !cv) return
  const rect = el.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  dpr = window.devicePixelRatio || 1
  width = Math.floor(rect.width)
  height = Math.floor(rect.height)
  cv.width = Math.floor(width * dpr)
  cv.height = Math.floor(height * dpr)
  cv.style.width = `${width}px`
  cv.style.height = `${height}px`
  ctx = cv.getContext('2d')
  schedule()
}

watch(() => props.bars, () => {
  prepare()
  prepareBig()
  hoverInfo.value = null
  nextTick(() => {
    resize()
    fitView()
    schedule()
  })
})
// 只改阈值：不重置视图，只重算大单分组并重绘
watch(() => [props.bigOrders, props.bigOrder], () => {
  prepareBig()
  schedule()
})
watch(() => props.selectedIndex, schedule)
onThemeChange(schedule)

onMounted(() => {
  prepare()
  prepareBig()
  resize()
  fitView()
  resizeObserver = new ResizeObserver(() => {
    const first = !width
    resize()
    if (first) fitView()
  })
  resizeObserver.observe(wrapRef.value)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  cancelAnimationFrame(raf)
  window.removeEventListener('mouseup', onUp)
})

defineExpose({ resize, fitView: () => { fitView(); schedule() } })
</script>

<style scoped>
.footprint {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border-radius: 8px;
  background: var(--bg-chart);
}

.footprint-canvas {
  display: block;
  cursor: crosshair;
}

.fp-info {
  position: absolute;
  top: 6px;
  left: 12px;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  padding: 3px 10px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-overlay-chart);
  border-radius: 4px;
  pointer-events: none;
}

.fp-info b {
  color: var(--text-body);
  font-weight: 600;
}

.fp-info b.up {
  color: var(--up);
}

.fp-info b.down {
  color: var(--down);
}

.info-time {
  color: var(--accent2);
  font-weight: 600;
}

.info-big {
  color: #c084fc;
  font-weight: 600;
}

.fp-legend {
  position: absolute;
  right: 72px;
  bottom: 30px;
  z-index: 5;
  display: flex;
  gap: 14px;
  font-size: 11px;
  color: var(--text-muted);
  pointer-events: none;
}

.fp-legend .lg {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 4px;
  border-radius: 2px;
  vertical-align: -1px;
}

.lg.sell {
  background: var(--down);
}

.lg.buy {
  background: var(--up);
}

.lg.big {
  border: 2px solid #a855f7;
  border-radius: 50%;
  background: rgba(168, 85, 247, 0.38);
}

.fp-hint {
  color: var(--text-muted);
}

.chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 40px;
  text-align: center;
  background: var(--bg-chart);
}

.empty-icon {
  font-size: 44px;
}

.empty-title {
  color: var(--text-body);
  font-size: 17px;
  font-weight: 600;
}

.empty-desc {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.chart-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg-overlay-chart);
  z-index: 10;
}

.loading-spinner {
  border: 4px solid var(--spinner-track);
  border-top: 4px solid var(--primary);
  border-radius: 50%;
  width: 44px;
  height: 44px;
  animation: fp-spin 1s linear infinite;
  margin-bottom: 14px;
}

.loading-text {
  color: var(--primary);
  font-size: 14px;
  font-weight: 600;
}

@keyframes fp-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
