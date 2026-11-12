/**
 * 交易页使用的接口入口：真实账号走后端 CTP 接口；调试模式（broker === 'debug'）走前端假数据。
 *
 * 每次调用时才判断模式（而不是模块加载时），因为同一个窗口里可能先后用调试模式和真实账号登录。
 * 调试模式的假数据实现见 @/mock/tradingDebug.js。
 */
import * as real from '@/api'
import * as mock from '@/mock/tradingDebug'
import { useUserStore } from '@/stores/user'

export const DEBUG_BROKER = 'debug'

export const isDebugMode = () => useUserStore().broker === DEBUG_BROKER

// 交易页用到的接口。logout 不在其中：调试模式下退出登录也会请求后端清理会话，失败已被吞掉，行为无需区别
const NAMES = [
  'getAccount',
  'getContracts',
  'getQuote',
  'placeOrder',
  'getOrders',
  'cancelOrder',
  'getPositions',
  'getTrades',
  'startReverse'
]

const pick = (name) => (...args) => (isDebugMode() ? mock : real)[name](...args)

export const {
  getAccount,
  getContracts,
  getQuote,
  placeOrder,
  getOrders,
  cancelOrder,
  getPositions,
  getTrades,
  startReverse
} = Object.fromEntries(NAMES.map((name) => [name, pick(name)]))
