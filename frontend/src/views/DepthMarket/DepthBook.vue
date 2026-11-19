<template>
  <div class="depth-book">
    <div class="book-head">
      <span class="book-title">历史盘口</span>
      <span v-if="book" class="book-mode">{{ live ? '回放中' : '定格' }}</span>
    </div>

    <div v-if="!book" class="book-empty">
      {{ loading ? '加载中...' : '移动鼠标到 K 线上，或点击 K 线 / 开始回放，查看当时的盘口' }}
    </div>

    <template v-else>
      <div class="book-time">
        {{ timeText }}<span class="book-seq">第 {{ (book.index + 1).toLocaleString() }} 笔</span>
      </div>

      <div class="book-table">
        <div class="book-row book-row-head">
          <span class="c-name"></span><span class="c-price">价格</span><span class="c-vol">挂单量</span><span class="c-bar"></span>
        </div>

        <!-- 卖盘：卖N 在上，卖1 贴近中间价 -->
        <div v-for="a in asksDesc" :key="'a' + a.level" class="book-row">
          <span class="c-name down-text">卖{{ a.level }}</span>
          <span class="c-price down-text">{{ fmt(a.price) }}</span>
          <span class="c-vol">{{ fmt(a.volume) }}</span>
          <span class="c-bar"><i class="bar ask" :style="{ width: barWidth(a.volume) }"></i></span>
        </div>

        <!-- 最新价：和上一笔比较涨跌，红涨绿跌 -->
        <div class="book-last" :class="lastClass">
          <span class="last-price">{{ fmt(book.price) }}</span>
          <span class="last-meta">现量 {{ fmt(book.volume) }}</span>
          <span v-if="book.position != null" class="last-meta">仓 {{ fmt(book.position) }}</span>
          <span v-if="book.bs" class="last-bs" :class="book.bs.startsWith('多') ? 'up-text' : book.bs.startsWith('空') ? 'down-text' : ''">{{ book.bs }}</span>
        </div>

        <div v-for="b in book.bids" :key="'b' + b.level" class="book-row">
          <span class="c-name up-text">买{{ b.level }}</span>
          <span class="c-price up-text">{{ fmt(b.price) }}</span>
          <span class="c-vol">{{ fmt(b.volume) }}</span>
          <span class="c-bar"><i class="bar bid" :style="{ width: barWidth(b.volume) }"></i></span>
        </div>
      </div>

      <!-- 买卖力量对比：委买总量 / (委买 + 委卖) -->
      <div v-if="book.asks.length" class="book-ratio">
        <div class="ratio-label">
          <span class="up-text">委买 {{ fmt(bidTotal) }}</span>
          <span class="down-text">委卖 {{ fmt(askTotal) }}</span>
        </div>
        <div class="ratio-bar">
          <i class="ratio-bid" :style="{ width: bidRatio + '%' }"></i>
        </div>
        <div class="ratio-pct">
          <span>{{ bidRatio.toFixed(1) }}%</span><span>{{ (100 - bidRatio).toFixed(1) }}%</span>
        </div>
      </div>
      <div v-if="book.asks.length === 0" class="book-empty small">文件里没有盘口列，只能看 K 线</div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  book: { type: Object, default: null },          // 后端 book 结构：{ time, price, volume, position, asks[], bids[] }
  prevPrice: { type: Number, default: null },     // 上一笔最新价，用来判断最新价涨跌
  loading: { type: Boolean, default: false },
  live: { type: Boolean, default: false }         // 是否在回放（仅影响右上角标签）
})

const fmt = (v) => (v == null ? '--' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 }))

// 卖盘倒序：卖5 在最上面，卖1 紧贴最新价
const asksDesc = computed(() => (props.book ? [...props.book.asks].reverse() : []))

const maxVol = computed(() => {
  if (!props.book) return 1
  const all = [...props.book.asks, ...props.book.bids].map((x) => x.volume || 0)
  return Math.max(...all, 1)
})
const barWidth = (v) => `${Math.min(100, ((v || 0) / maxVol.value) * 100)}%`

const sum = (list) => list.reduce((s, x) => s + (x.volume || 0), 0)
const askTotal = computed(() => (props.book ? sum(props.book.asks) : 0))
const bidTotal = computed(() => (props.book ? sum(props.book.bids) : 0))
const bidRatio = computed(() => {
  const t = askTotal.value + bidTotal.value
  return t > 0 ? (bidTotal.value / t) * 100 : 50
})

// 时间显示：毫秒位全是 0 时（数据只精确到秒 / 分钟）不显示 .000，避免误导成"精确到毫秒"
const timeText = computed(() => {
  const t = props.book?.time || ''
  return t.endsWith('.000') ? t.slice(0, -4) : t
})

const lastClass = computed(() => {
  const p = props.book?.price
  if (p == null || props.prevPrice == null || p === props.prevPrice) return ''
  return p > props.prevPrice ? 'up' : 'down'
})
</script>

<style scoped>
.depth-book {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  padding: 14px;
  background: var(--bg-chart);
  border-radius: 8px;
  overflow-y: auto;
  font-size: 12px;
  color: var(--text-body);
  font-variant-numeric: tabular-nums;
}

.book-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.book-title {
  color: var(--accent2);
  font-size: 15px;
  font-weight: 600;
}

.book-mode {
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  color: var(--accent2);
  background: rgba(var(--accent2-rgb), 0.12);
}

.book-time {
  color: var(--text-secondary);
}

.book-seq {
  margin-left: 10px;
  color: var(--text-muted);
}

.last-bs {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
}

.book-empty {
  padding: 24px 6px;
  color: var(--text-muted);
  line-height: 1.7;
  text-align: center;
}

.book-empty.small {
  padding: 6px;
}

.book-row {
  display: grid;
  grid-template-columns: 34px 62px 62px 1fr;
  align-items: center;
  gap: 6px;
  height: 24px;
}

.book-row-head {
  height: 20px;
  color: var(--text-muted);
  font-size: 11px;
}

.c-price,
.c-vol {
  text-align: right;
}

.c-bar {
  position: relative;
  height: 12px;
}

.bar {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  border-radius: 2px;
  opacity: 0.55;
}

/* 红涨绿跌：买盘（多）用红，卖盘（空）用绿 */
.bar.bid {
  background: var(--up);
}

.bar.ask {
  background: var(--down);
}

.up-text {
  color: var(--up);
}

.down-text {
  color: var(--down);
}

.book-last {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 4px 0;
  padding: 6px 4px;
  border-top: 1px solid var(--border-panel);
  border-bottom: 1px solid var(--border-panel);
}

.last-price {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-body);
}

.book-last.up .last-price {
  color: var(--up);
}

.book-last.down .last-price {
  color: var(--down);
}

.last-meta {
  color: var(--text-secondary);
}

.book-ratio {
  margin-top: 6px;
}

.ratio-label,
.ratio-pct {
  display: flex;
  justify-content: space-between;
}

.ratio-pct {
  color: var(--text-muted);
  font-size: 11px;
}

.ratio-bar {
  position: relative;
  height: 8px;
  margin: 4px 0;
  background: var(--down);
  border-radius: 4px;
  overflow: hidden;
  opacity: 0.9;
}

.ratio-bid {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  background: var(--up);
}
</style>
