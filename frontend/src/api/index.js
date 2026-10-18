import request from '@/utils/request'

// 获取期货公司列表
export function getBrokers() {
  return request({
    url: '/api/brokers',
    method: 'get'
  })
}

// 登录
export function login(data) {
  return request({
    url: '/login',
    method: 'post',
    data
  })
}

// 退出登录
export function logout() {
  return request({
    url: '/logout',
    method: 'post'
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

// 量化账号登录
export function quantLogin(data) {
  return request({
    url: '/api/quant-login',
    method: 'post',
    data
  })
}
