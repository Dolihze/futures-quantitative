// 回测时间范围选项的共用逻辑（总览 / 详情）。
//
// 新浪每个周期只给最近约 1023 根 K 线（5 分钟线约 3 周），所以「60 天」「90 天」往往拿不到那么多数据。
// 后端会告诉我们实际可得的天数 availableDays，这里据此：
//   - 只给出不超过可得天数的固定档位（7/15/30/60/90），
//   - 再加一个「全部（N 天）」代表数据允许的最大范围；
//   - 超出可得数据的档位不显示，避免「60 天」「90 天」其实是同一份结果的误导。

export const DAY_CHOICES = [7, 15, 30, 60, 90]

// 根据可得天数生成选项：[{ value, label }]。可得天数未知（0）时退回固定档位，等第一次请求返回后再收敛。
export function buildDayOptions(availableDays) {
  if (!availableDays) return DAY_CHOICES.map((d) => ({ value: d, label: `${d}天` }))
  const opts = DAY_CHOICES.filter((d) => d < availableDays).map((d) => ({ value: d, label: `${d}天` }))
  // 「全部」= 数据允许的最大范围，value 就是可得天数，传给后端后不会被截断
  opts.push({ value: availableDays, label: `全部(${availableDays}天)` })
  return opts
}

// 把用户选择的天数收敛到可选项里：不在选项中（比如 URL 里带了 90，而数据只有 21 天）时取「全部」。
export function clampDays(days, availableDays) {
  if (!availableDays || days <= availableDays) return days
  return availableDays
}
