import request from '@/utils/request'

// 获取期货公司列表
export function getBrokers() {
  return request({
    url: '/api/brokers',
    method: 'get'
  })
}

// 登录：后端通过 CTP 连接期货公司（终端认证 + 登录），最长约 25 秒，因此放宽超时
export function login(data) {
  return request({
    url: '/api/login',
    method: 'post',
    data,
    timeout: 45000
  })
}

// 当前账号的资金、持仓快照（来自后端 CTP 会话）
export function getAccount() {
  return request({
    url: '/api/account',
    method: 'get',
    silent: true
  })
}

// 退出登录
// 服务端 session 清理失败（后端未启动/网络异常）不应阻止用户在本地退出，
// 因此这里吞掉错误且不弹全局提示，调用方随后会清理本地登录态。
export function logout() {
  return request({
    url: '/api/logout',
    method: 'post',
    silent: true
  }).catch(error => {
    console.warn('退出登录：服务端会话清理失败，仅清理本地登录态', error)
  })
}

// 获取K线数据
export function getKlineData(params) {
  console.log('🌐 [API] getKlineData 请求:')
  console.log('   URL:', '/api/backtest/kline')
  console.log('   参数:', params)
  
  return request({
    url: '/api/backtest/kline',
    method: 'get',
    params
  }).then(response => {
    console.log('📨 [API] getKlineData 响应:', response)
    return response
  }).catch(error => {
    console.error('❌ [API] getKlineData 错误:', error)
    throw error
  })
}

// 交易复盘：上传交易记录 Excel（multipart）。
// 业务错误（格式不对、列缺失等）后端返回 400 + message，这里由页面自己展示，不弹全局错误提示。
// overwrite=true：文件夹里已有同名文件时直接覆盖。不带时后端对同名文件返回 409（error.response.data.exists），
// 由页面弹窗让用户确认后再带 overwrite 重传。
export function uploadReviewFile(file, overwrite = false) {
  const form = new FormData()
  form.append('file', file)
  if (overwrite) form.append('overwrite', '1')
  return request({
    url: '/api/review/upload',
    method: 'post',
    data: form,
    timeout: 120000,
    silent: true
  })
}

// 交易复盘：列出项目 review_files 文件夹里已导入的交易记录文件（最近修改的在前）
export function getReviewFiles() {
  return request({
    url: '/api/review/files',
    method: 'get',
    silent: true
  })
}

// 交易复盘：删除 review_files 文件夹里的一个文件（只删磁盘文件，已经在分析的数据不受影响）
export function deleteReviewFile(name) {
  return request({
    url: '/api/review/files',
    method: 'delete',
    data: { name },
    silent: true
  })
}

// 交易复盘：选择 review_files 文件夹里已有的文件进行分析，返回结构和 uploadReviewFile 完全一致
export function openReviewFile(name) {
  return request({
    url: '/api/review/open',
    method: 'post',
    data: { name },
    timeout: 120000,
    silent: true
  })
}

// 交易复盘：按品种/时间范围获取累计盈亏曲线。
// 记录失效（expired）时由页面提示重新上传，因此同样不弹全局提示。
export function getReviewCurve(params) {
  return request({
    url: '/api/review/curve',
    method: 'get',
    params,
    silent: true
  })
}

// 交易复盘：某个交易日的所有交易（开仓/平仓已配对，按合约分组）
export function getReviewDayTrades(params) {
  return request({
    url: '/api/review/day-trades',
    method: 'get',
    params,
    silent: true
  })
}

// 交易复盘：某个合约在某个交易日的 1 分钟 K 线（新浪数据，只有最近几个交易日）
export function getReviewDayKline(params) {
  return request({
    url: '/api/review/day-kline',
    method: 'get',
    params,
    timeout: 60000,
    silent: true
  })
}

// 量化账号登录
export function quantLogin(data) {
  return request({
    url: '/api/quant-login',
    method: 'post',
    data
  })
}
