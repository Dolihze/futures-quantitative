// 回测详情页「K线与买卖点」切换显示周期时，把成交点按时间重新映射到新周期的 K 线上。
//
// 回测始终按策略声明的周期（如 1 分钟）跑，成交的 entryIndex / exitIndex 是那个周期 K 线的下标。
// 图上换成别的周期后下标就对不上了，所以改用时间定位：
//   新浪 K 线的时间戳是该根 K 线的【结束时间】（5 分钟线 10:05 = 10:00~10:05），
//   所以时刻 t 属于「时间戳 >= t 的第一根」K 线。
// 时间字符串是 'YYYY-MM-DD HH:MM:SS'，同一格式下字典序 = 时间序，可以直接比较字符串。

// 在升序的 bars 里找时间戳 >= time 的第一根的下标；time 晚于最后一根返回 -1，早于第一根返回 0
export function indexAtOrAfter(bars, time) {
  let lo = 0
  let hi = bars.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (bars[mid].time < time) lo = mid + 1
    else hi = mid
  }
  return lo < bars.length ? lo : -1
}

// 某个时刻在显示周期 K 线里的下标。
// 落在显示数据范围之外（比第一根还早很多 / 比最后一根还晚）时返回 -1：这笔交易在当前显示数据里看不到
export function locateTime(bars, time) {
  if (!bars.length || !time) return -1
  if (time > bars[bars.length - 1].time) return -1
  return indexAtOrAfter(bars, time)
}

// 把成交列表映射到显示周期的 K 线：返回 [{ ...trade, entryIndex, exitIndex }]，只保留两端都能定位的交易。
// 找不到的交易（超出显示数据范围）被丢弃，调用方可以用 hidden 数量提示用户。
// 起点早于显示数据第一根时（例如更长周期的数据比 1 分钟线早很多，反过来则是 1 分钟线只有 3 天）：
// 时间早于显示数据开头的成交认为在范围外，不硬贴到第一根上，避免把买卖点画到错误的位置。
export function mapTrades(trades, bars) {
  if (!bars.length) return { trades: [], hidden: trades.length }
  const first = bars[0].time
  const mapped = []
  let hidden = 0
  for (const t of trades) {
    if (t.entryTime < first || t.exitTime < first) {
      hidden++
      continue
    }
    const entryIndex = locateTime(bars, t.entryTime)
    const exitIndex = locateTime(bars, t.exitTime)
    if (entryIndex < 0 || exitIndex < 0) {
      hidden++
      continue
    }
    mapped.push({ ...t, entryIndex, exitIndex })
  }
  return { trades: mapped, hidden }
}
