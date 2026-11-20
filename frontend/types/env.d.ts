// 手写的全局类型声明（生成的声明在 types/generated/，已 gitignore）

interface TauriGlobal {
  core: {
    invoke<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T>
  }
  event: {
    listen<T = unknown>(
      event: string,
      handler: (e: { payload: T }) => void
    ): Promise<() => void>
  }
}

interface Window {
  /** tauri.conf.json 里 withGlobalTauri: true 时由 Tauri 注入 */
  __TAURI__?: TauriGlobal
}
