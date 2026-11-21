/**
 * 量化监控（跟单）接口：登录被监控账号（只读）+ 跟单引擎启停 / 状态 / 记录。
 * 全部 silent：由页面自己展示失败原因，避免全局 toast 与页面提示重复。
 * @typedef {import('./types').ApiResult} ApiResult
 */
import { http } from '@/utils/request'

// 登录被监控账号（CTP 登录最长约 25 秒）
/**
 * @param {import('./types').LoginPayload} data
 * @returns {Promise<import('./types').LoginResult>}
 */
export function monitorLogin(data) {
  return http({ url: '/api/monitor/login', method: 'post', data, timeout: 45000, silent: true })
}

// 读取「记住账号密码」保存的被监控账号，用于表单预填：{ saved, broker, username, password }
/** @returns {Promise<import('./types').SavedCredentials>} */
export function getMonitorCredentials() {
  return http({ url: '/api/monitor/credentials', method: 'get', silent: true })
}

/** @returns {Promise<ApiResult>} */
export function monitorLogout() {
  return http({ url: '/api/monitor/logout', method: 'post', silent: true })
}

// 被监控账号的权益与持仓
/** @returns {Promise<ApiResult & { data?: any }>} */
export function getMonitorAccount() {
  return http({ url: '/api/monitor/account', method: 'get', silent: true })
}

// 跟单引擎状态（运行 / 暂停 / 配置 / 连接 / 权益）
/** @returns {Promise<ApiResult & { data?: any }>} */
export function getMonitorStatus() {
  return http({ url: '/api/monitor/status', method: 'get', silent: true })
}

// 跟单记录 + 运行日志
/** @returns {Promise<ApiResult & { data?: { records: any[], logs: any[] } }>} */
export function getMonitorRecords() {
  return http({ url: '/api/monitor/records', method: 'get', silent: true })
}

// 导出运行日志为 Excel：返回 xlsx 二进制（Blob），不是 JSON
/** @returns {Promise<Blob>} */
export function exportMonitorLogs() {
  return http({ url: '/api/monitor/logs/export', method: 'get', responseType: 'blob', silent: true })
}

/**
 * @param {Record<string, any>} config
 * @returns {Promise<ApiResult>}
 */
export function startCopy(config) {
  return http({ url: '/api/monitor/start', method: 'post', data: { config }, silent: true })
}

/** @returns {Promise<ApiResult>} */
export function stopCopy() {
  return http({ url: '/api/monitor/stop', method: 'post', silent: true })
}

/**
 * @param {Record<string, any>} config
 * @returns {Promise<ApiResult>}
 */
export function updateCopyConfig(config) {
  return http({ url: '/api/monitor/config', method: 'post', data: { config }, silent: true })
}

// 只保存配置到本地（不启动跟单），下次打开软件时恢复
/**
 * @param {Record<string, any>} config
 * @returns {Promise<ApiResult>}
 */
export function saveCopyConfig(config) {
  return http({ url: '/api/monitor/config/save', method: 'post', data: { config }, silent: true })
}

// 人工解除断连造成的自动暂停
/** @returns {Promise<ApiResult>} */
export function resumeCopy() {
  return http({ url: '/api/monitor/resume', method: 'post', silent: true })
}
