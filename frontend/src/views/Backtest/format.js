// 回测页面（总览 / 详情）共用的格式化函数。红涨绿跌：盈利 positive（红），亏损 negative（绿）。

// 金额：带正负号，两位小数；null / undefined 显示 --
export function fmtMoney(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}`
}

// 盈亏比 = 平均盈利 / 平均亏损。没有亏损单时无法计算：有盈利显示 ∞，没有交易显示 --
export function fmtRatio(st) {
  if (!st || !st.tradeCount) return '--'
  if (st.plRatio === null || st.plRatio === undefined) return st.winCount > 0 ? '∞' : '--'
  return st.plRatio.toFixed(2)
}

export function pnlClass(v) {
  if (v > 0) return 'positive'
  if (v < 0) return 'negative'
  return 'neutral'
}

export function sideText(side) {
  return side === 'long' ? '多' : '空'
}
