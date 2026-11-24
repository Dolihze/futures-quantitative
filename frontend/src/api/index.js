/**
 * 后端接口。返回类型见 ./types.js（改后端响应字段时同步修改）。
 * @typedef {import('./types').ApiResult} ApiResult
 */
import { http } from '@/utils/request'

// 获取期货公司列表
/** @returns {Promise<import('./types').BrokerGroup[]>} */
export function getBrokers() {
  return http({
    url: '/api/brokers',
    method: 'get'
  })
}

// 登录：后端通过 CTP 连接期货公司（终端认证 + 登录），最长约 25 秒，因此放宽超时
/**
 * @param {import('./types').LoginPayload} data
 * @returns {Promise<import('./types').LoginResult>}
 */
export function login(data) {
  return http({
    url: '/api/login',
    method: 'post',
    data,
    timeout: 45000
  })
}

// 读取「记住账号」保存的凭据（期货公司 / 账号 / 密码），用于登录页预填
/** @returns {Promise<import('./types').SavedCredentials>} */
export function getSavedCredentials() {
  return http({
    url: '/api/credentials',
    method: 'get',
    silent: true
  })
}

// 当前账号的资金、持仓快照（来自后端 CTP 会话）
/** @returns {Promise<ApiResult & { connected?: boolean, data?: any }>} */
export function getAccount() {
  return http({
    url: '/api/account',
    method: 'get',
    silent: true
  })
}

// 退出登录
// 服务端 session 清理失败（后端未启动/网络异常）不应阻止用户在本地退出，
// 因此这里吞掉错误且不弹全局提示，调用方随后会清理本地登录态。
/** @returns {Promise<ApiResult | void>} */
export function logout() {
  return http({
    url: '/api/logout',
    method: 'post',
    silent: true
  }).catch(error => {
    console.warn('退出登录：服务端会话清理失败，仅清理本地登录态', error)
  })
}

// 量化回测：可回测的合约 = 「数据库管理 → 历史行情数据管理」里已导入的合约
/** @returns {Promise<ApiResult & { default: string, data: import('./types').BacktestContract[] }>} */
export function getBacktestContracts() {
  return http({
    url: '/api/backtest/contracts',
    method: 'get',
    silent: true
  })
}

// 量化回测首页：所选合约（本地行情库）上，所有策略在最近 days 天内的胜率、盈亏比、总盈亏、缩略净值曲线。
// 后端要对每个策略取 K 线并回测，首次可能较慢，放宽超时；失败由页面自己展示，不弹全局提示。
/**
 * @param {import('./types').BacktestParams} params
 * @returns {Promise<import('./types').BacktestOverview>}
 */
export function getBacktestOverview(params) {
  return http({
    url: '/api/backtest/overview',
    method: 'get',
    params,
    timeout: 90000,
    silent: true
  })
}

// 量化回测详情：单个策略的 K 线、买卖成交点、逐笔明细、净值曲线、完整统计
/**
 * @param {import('./types').BacktestParams} params
 * @returns {Promise<ApiResult & Record<string, any>>}
 */
export function runBacktest(params) {
  return http({
    url: '/api/backtest/run',
    method: 'get',
    params,
    timeout: 90000,
    silent: true
  })
}

// 量化回测详情：只取某合约某周期的 K 线（不重跑回测），用于「K线与买卖点」切换显示周期
/**
 * @param {import('./types').BacktestParams} params
 * @returns {Promise<ApiResult & { data: import('./types').BacktestKlineBar[], symbol: string, symbolName: string, count: number }>}
 */
export function getBacktestKline(params) {
  return http({
    url: '/api/backtest/kline',
    method: 'get',
    params,
    timeout: 60000,
    silent: true
  })
}

// 交易复盘：上传交易记录 Excel（multipart）。
// 业务错误（格式不对、列缺失等）后端返回 400 + message，这里由页面自己展示，不弹全局错误提示。
// overwrite=true：文件夹里已有同名文件时直接覆盖。不带时后端对同名文件返回 409（error.response.data.exists），
// 由页面弹窗让用户确认后再带 overwrite 重传。
/**
 * @param {File} file
 * @param {boolean} [overwrite]
 * @returns {Promise<import('./types').ReviewOpenResult>}
 */
export function uploadReviewFile(file, overwrite = false) {
  const form = new FormData()
  form.append('file', file)
  if (overwrite) form.append('overwrite', '1')
  return http({
    url: '/api/review/upload',
    method: 'post',
    data: form,
    timeout: 120000,
    silent: true
  })
}

// 交易复盘：列出项目 review_files 文件夹里已导入的交易记录文件（最近修改的在前）
/** @returns {Promise<ApiResult & { dir: string, files: import('./types').ReviewFile[] }>} */
export function getReviewFiles() {
  return http({
    url: '/api/review/files',
    method: 'get',
    silent: true
  })
}

// 交易复盘：删除 review_files 文件夹里的一个文件（只删磁盘文件，已经在分析的数据不受影响）
/**
 * @param {string} name
 * @returns {Promise<ApiResult & { name?: string }>}
 */
export function deleteReviewFile(name) {
  return http({
    url: '/api/review/files',
    method: 'delete',
    data: { name },
    silent: true
  })
}

// 交易复盘：选择 review_files 文件夹里已有的文件进行分析，返回结构和 uploadReviewFile 完全一致
/**
 * @param {string} name
 * @returns {Promise<import('./types').ReviewOpenResult>}
 */
export function openReviewFile(name) {
  return http({
    url: '/api/review/open',
    method: 'post',
    data: { name },
    timeout: 120000,
    silent: true
  })
}

// 交易复盘：按品种/时间范围获取累计盈亏曲线。
// 记录失效（expired）时由页面提示重新上传，因此同样不弹全局提示。
/**
 * @param {import('./types').ReviewCurveParams} params
 * @returns {Promise<ApiResult & Record<string, any>>}
 */
export function getReviewCurve(params) {
  return http({
    url: '/api/review/curve',
    method: 'get',
    params,
    silent: true
  })
}

// 交易复盘：某个交易日的所有交易（开仓/平仓已配对，按合约分组）
/**
 * @param {{ reviewId: string, day: string, products?: string }} params
 * @returns {Promise<ApiResult & Record<string, any>>}
 */
export function getReviewDayTrades(params) {
  return http({
    url: '/api/review/day-trades',
    method: 'get',
    params,
    silent: true
  })
}

// 交易复盘：某个合约在某个交易日的 1 分钟 K 线（取自本地历史行情库，需先在数据库管理导入该合约的 tick）
/**
 * @param {{ symbol: string, day: string }} params
 * @returns {Promise<ApiResult & { available?: boolean, symbol?: string, day?: string, period?: number, data: import('./types').BacktestKlineBar[], count?: number, partial?: boolean }>}
 */
export function getReviewDayKline(params) {
  return http({
    url: '/api/review/day-kline',
    method: 'get',
    params,
    timeout: 60000,
    silent: true
  })
}

// 可交易的期货合约列表（登录后由 CTP 异步查询，刚登录时可能还没就绪）
/** @returns {Promise<ApiResult & { data?: any[] }>} */
export function getContracts() {
  return http({
    url: '/api/contracts',
    method: 'get',
    silent: true
  })
}

// 订阅并获取合约最新行情，symbol 形如 ag2612.SHFE
/**
 * @param {string} symbol
 * @returns {Promise<ApiResult & { data?: any }>}
 */
export function getQuote(symbol) {
  return http({
    url: '/api/quote',
    method: 'get',
    params: { symbol },
    silent: true
  })
}

// 限价下单：action = open_long 买多开仓 / open_short 卖空开仓 / close_long 平多 / close_short 平空
// 业务失败（校验不通过、柜台拒单）由页面自己展示原因，不弹全局提示
/**
 * @param {import('./types').OrderPayload} data
 * @returns {Promise<ApiResult & Record<string, any>>}
 */
export function placeOrder(data) {
  return http({
    url: '/api/order',
    method: 'post',
    data,
    silent: true
  })
}

// 委托列表（最新的在前）
/** @returns {Promise<ApiResult & { data?: any[] }>} */
export function getOrders() {
  return http({
    url: '/api/orders',
    method: 'get',
    silent: true
  })
}

// 持仓列表：含今昨仓、开仓均价、按最新价算的浮动盈亏
/** @returns {Promise<ApiResult & { data?: any[] }>} */
export function getPositions() {
  return http({
    url: '/api/positions',
    method: 'get',
    silent: true
  })
}

// 成交明细（最新的在前）
/** @returns {Promise<ApiResult & { data?: any[] }>} */
export function getTrades() {
  return http({
    url: '/api/trades',
    method: 'get',
    silent: true
  })
}

// 反手：先按 closePrice 平掉 volume 手 fromSide（'多' / '空'）持仓，
// 平仓【全部成交】后才按 openPrice 反向开同样手数。业务失败由页面自己展示原因。
/**
 * @param {import('./types').ReversePayload} data
 * @returns {Promise<ApiResult & Record<string, any>>}
 */
export function startReverse(data) {
  return http({
    url: '/api/reverse',
    method: 'post',
    data,
    silent: true
  })
}

// 撤单
/**
 * @param {string} orderId
 * @returns {Promise<ApiResult>}
 */
export function cancelOrder(orderId) {
  return http({
    url: '/api/order/cancel',
    method: 'post',
    data: { orderId },
    silent: true
  })
}

// 交易复盘·账户总览：合并 review_files 全部交易记录，按交易日 / 品种聚合。
// params = { fee(1/0), start, end }；返回的 reviewId 可直接用于 getReviewCurve / getReviewDayTrades 等单日接口
/**
 * @param {import('./types').ReviewOverviewParams} params
 * @returns {Promise<import('./types').ReviewOverview>}
 */
export function getReviewOverview(params) {
  return http({ url: '/api/review/overview', method: 'get', params, timeout: 120000, silent: true })
}

// 交易记录文件列表 + 每个文件的元信息（品种 / 交易日 / 成交手数），数据库管理用
/** @returns {Promise<ApiResult & { dir: string, files: import('./types').ReviewFileDetail[] }>} */
export function getReviewFilesDetail() {
  return http({ url: '/api/review/files/detail', method: 'get', silent: true })
}

// ===== 深度行情：历史 tick CSV -> K 线 + 历史盘口 =====
// 上传 tick CSV（multipart）。文件可能很大（几十 MB），超时放宽到 10 分钟；
// 同名文件 409 + exists 的处理同交易复盘（overwrite=true 覆盖）。
/**
 * @param {File} file
 * @param {boolean} [overwrite]
 * @returns {Promise<import('./types').DepthOpenResult>}
 */
export function uploadDepthFile(file, overwrite = false) {
  const form = new FormData()
  form.append('file', file)
  if (overwrite) form.append('overwrite', '1')
  return http({ url: '/api/depth/upload', method: 'post', data: form, timeout: 600000, silent: true })
}

// 已导入的合约列表（按合约合并多个文件）+ 无法识别的文件。深度行情左侧列表和数据库管理共用
/** @returns {Promise<import('./types').DepthContractsResult>} */
export function getDepthContracts() {
  return http({ url: '/api/depth/contracts', method: 'get', silent: true })
}

// 打开一个合约：后端把它名下所有文件合并成一条时间线，返回结构同 uploadDepthFile
/**
 * @param {string} symbol
 * @returns {Promise<import('./types').DepthOpenResult>}
 */
export function openDepthContract(symbol) {
  return http({ url: '/api/depth/open-contract', method: 'post', data: { symbol }, timeout: 600000, silent: true })
}

// 删除一个合约（删掉它名下的全部文件）
/**
 * @param {string} symbol
 * @returns {Promise<ApiResult & { deleted?: string[], failed?: {name: string, error: string}[] }>}
 */
export function deleteDepthContract(symbol) {
  return http({ url: '/api/depth/contracts', method: 'delete', data: { symbol }, silent: true })
}

// 列出项目 depth_files 文件夹里已导入的 tick CSV
/** @returns {Promise<ApiResult & { dir: string, files: import('./types').ReviewFile[] }>} */
export function getDepthFiles() {
  return http({ url: '/api/depth/files', method: 'get', silent: true })
}

// 删除 depth_files 里的一个文件
/**
 * @param {string} name
 * @returns {Promise<ApiResult & { name?: string }>}
 */
export function deleteDepthFile(name) {
  return http({ url: '/api/depth/files', method: 'delete', data: { name }, silent: true })
}

// 选择 depth_files 里已有文件进行解析，返回结构同 uploadDepthFile
/**
 * @param {string} name
 * @returns {Promise<import('./types').DepthOpenResult>}
 */
export function openDepthFile(name) {
  return http({ url: '/api/depth/open', method: 'post', data: { name }, timeout: 600000, silent: true })
}

// 由 tick 聚合 K 线：params = { depthId, period(1/5/15/30/60/1440), day }
/**
 * @param {import('./types').DepthChartParams} params
 * @returns {Promise<ApiResult & Record<string, any>>}
 */
export function getDepthKline(params) {
  return http({ url: '/api/depth/kline', method: 'get', params, timeout: 120000, silent: true })
}

// 足迹图：每根 K 线每个价位的买 / 卖 / 中性成交量 + 大单列表。
// params = { depthId, period, day, bigOrder }。文件没有 BS 列时后端返回 400 + message（页面自己展示）
/**
 * @param {import('./types').DepthChartParams} params
 * @returns {Promise<ApiResult & Record<string, any>>}
 */
export function getDepthFootprint(params) {
  return http({ url: '/api/depth/footprint', method: 'get', params, timeout: 120000, silent: true })
}

// 某一时刻的历史盘口：params = { depthId, ts } 或 { depthId, index }
/**
 * @param {{ depthId: string, ts?: number, index?: number }} params
 * @returns {Promise<ApiResult & Record<string, any>>}
 */
export function getDepthBook(params) {
  return http({ url: '/api/depth/book', method: 'get', params, silent: true })
}

// 一段连续 tick（含盘口），用于回放预取：params = { depthId, start, count }
/**
 * @param {{ depthId: string, start?: number, count?: number }} params
 * @returns {Promise<ApiResult & Record<string, any>>}
 */
export function getDepthTicks(params) {
  return http({ url: '/api/depth/ticks', method: 'get', params, silent: true })
}
