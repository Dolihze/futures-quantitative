/**
 * 量化监控（跟单）接口：登录被监控账号（只读）+ 跟单引擎启停 / 状态 / 记录。
 * 全部 silent：由页面自己展示失败原因，避免全局 toast 与页面提示重复。
 */
import request from '@/utils/request'

// 登录被监控账号（CTP 登录最长约 25 秒）
export function monitorLogin(data) {
  return request({ url: '/api/monitor/login', method: 'post', data, timeout: 45000, silent: true })
}

// 读取「记住账号密码」保存的被监控账号，用于表单预填：{ saved, broker, username, password }
export function getMonitorCredentials() {
  return request({ url: '/api/monitor/credentials', method: 'get', silent: true })
}

export function monitorLogout() {
  return request({ url: '/api/monitor/logout', method: 'post', silent: true })
}

// 被监控账号的权益与持仓
export function getMonitorAccount() {
  return request({ url: '/api/monitor/account', method: 'get', silent: true })
}

// 跟单引擎状态（运行 / 暂停 / 配置 / 连接 / 权益）
export function getMonitorStatus() {
  return request({ url: '/api/monitor/status', method: 'get', silent: true })
}

// 跟单记录 + 运行日志
export function getMonitorRecords() {
  return request({ url: '/api/monitor/records', method: 'get', silent: true })
}

export function startCopy(config) {
  return request({ url: '/api/monitor/start', method: 'post', data: { config }, silent: true })
}

export function stopCopy() {
  return request({ url: '/api/monitor/stop', method: 'post', silent: true })
}

export function updateCopyConfig(config) {
  return request({ url: '/api/monitor/config', method: 'post', data: { config }, silent: true })
}

// 人工解除断连造成的自动暂停
export function resumeCopy() {
  return request({ url: '/api/monitor/resume', method: 'post', silent: true })
}
