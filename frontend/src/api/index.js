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
  return request({
    url: '/api/backtest/kline',
    method: 'get',
    params
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
