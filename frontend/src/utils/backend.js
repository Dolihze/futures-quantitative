// 后端地址解析与就绪等待。
//  - 请求地址：
//      开发（vite dev）：baseURL 为 ''，请求走 Vite 代理（/api -> BACKEND_PORT，默认 5000）。
//      Tauri 打包：端口由 Rust 随机选取，通过 `get_backend_url` 命令取得。
//  - 就绪等待：只要运行在 Tauri 里（开发或打包），Rust 在后端端口可连接后发出 backend-ready 事件，
//    前端等它再挂载，避免首屏请求 ECONNREFUSED。纯浏览器访问 vite dev 时没有 Tauri，直接放行。

/** @returns {boolean} */
export function isTauri() {
  return typeof window !== 'undefined' && !!window.__TAURI__?.core
}

/**
 * 解析 axios 的 baseURL。
 * @returns {Promise<string>}
 */
export async function resolveBackendBase() {
  // 开发时端口固定，走 Vite 代理即可，不需要绝对地址（也避免跨域）
  if (import.meta.env.DEV || !isTauri()) return ''
  try {
    return await /** @type {NonNullable<Window['__TAURI__']>} */ (window.__TAURI__).core.invoke('get_backend_url')
  } catch (e) {
    console.error('获取后端地址失败:', e)
    return ''
  }
}

/**
 * 等待后端就绪。非 Tauri 环境立即返回 true。
 * @param {number} [timeoutMs]
 * @returns {Promise<boolean>}
 */
export async function waitBackendReady(timeoutMs = 90000) {
  if (!isTauri()) return true
  const { core, event } = /** @type {NonNullable<Window['__TAURI__']>} */ (window.__TAURI__)
  if (await core.invoke('is_backend_ready')) return true
  return new Promise((resolve) => {
    let done = false
    let unlisten = () => {}
    /** @param {boolean} ok */
    const finish = (ok) => {
      if (done) return
      done = true
      clearTimeout(timer)
      unlisten()
      resolve(ok)
    }
    const timer = setTimeout(() => finish(false), timeoutMs)
    event.listen('backend-ready', (e) => finish(!!e.payload)).then((fn) => {
      unlisten = fn
      if (done) fn()
    })
    // 监听注册期间事件可能已经发出，补查一次
    core.invoke('is_backend_ready').then((ok) => ok && finish(true))
  })
}
