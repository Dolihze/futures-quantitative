import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { uploadDepthArchive, getDepthArchiveTask } from '@/api'

/**
 * 数据库管理 - 批量导入（全量压缩包 -> 指定品种）的状态。
 *
 * 为什么放在 store 而不是页面组件里：导入要几分钟，期间用户可能切到别的页面。
 * 组件销毁后组件内的状态和轮询都会丢，回来就看不到进度；放在 store 里，上传请求和轮询的生命周期
 * 跟页面无关，回到页面时直接显示最新状态。
 * 应用被整体刷新 / 重启后 store 也会清空，此时 restore() 向后端要「最近的任务」来恢复
 * （导入在后端线程里跑，不受前端影响；但上传阶段被中断的任务后端没收到完整文件，无法恢复）。
 */

const POLL_INTERVAL = 800
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** @param {any} error @param {string} fallback */
function errorText(error, fallback) {
  const data = error?.response?.data
  if (data?.message) return data.message
  if (error?.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (error?.request && !error?.response) return '无法连接后端服务，请确认应用已正常启动'
  if (error?.response?.status) return `${fallback}（HTTP ${error.response.status}）`
  return error?.message || fallback
}

export const useDepthImportStore = defineStore('depthImport', () => {
  // 表单（也放这里，回到页面时选的品种还在）
  const products = ref(/** @type {string[]} */ ([]))
  const overwrite = ref(false)

  // 任务状态
  const busy = ref(false)
  // upload = 浏览器把压缩包传给后端（按字节），import = 后端查找并导入合约（按合约文件数）
  const stage = ref('upload')
  const uploadPercent = ref(0)
  const done = ref(0)
  const total = ref(0)
  const current = ref('')
  const fileName = ref('')
  const activeProducts = ref(/** @type {string[]} */ ([]))   // 当前（或刚完成）任务的品种，恢复时来自后端
  const result = ref(/** @type {import('@/api/types').DepthArchiveResult | null} */ (null))
  const error = ref('')
  // 每次任务完成（成功）自增，页面据此刷新合约列表
  const finishedSeq = ref(0)

  let polling = false

  const percent = computed(() => {
    if (stage.value === 'upload') return uploadPercent.value
    return total.value ? Math.min(100, Math.round((done.value / total.value) * 100)) : 0
  })
  const productText = computed(() => activeProducts.value.join('、'))
  const stageText = computed(() => {
    if (stage.value === 'upload') return `① 正在上传「${fileName.value}」...`
    if (!total.value) return `② 上传完成，正在扫描压缩包里「${productText.value}」的合约数据...`
    return `② 正在导入 ${done.value} / ${total.value} 份${current.value ? ` · ${current.value}` : ''}`
  })

  function resetRun() {
    stage.value = 'upload'
    uploadPercent.value = 0
    done.value = 0
    total.value = 0
    current.value = ''
    result.value = null
    error.value = ''
  }

  /** 轮询任务直到结束；同一时刻只会有一个轮询在跑。结束时更新 result / error / busy。 */
  async function poll(taskId) {
    if (polling) return
    polling = true
    let failures = 0
    try {
      for (;;) {
        let t
        try {
          t = await getDepthArchiveTask(taskId)
          failures = 0
        } catch (e) {
          // 偶发网络错误容忍几次；任务不存在（后端重启）直接失败
          if (e?.response?.status === 404 || ++failures >= 5) throw e
          await sleep(POLL_INTERVAL)
          continue
        }
        stage.value = 'import'
        done.value = t.done
        total.value = t.total
        current.value = t.current
        if (t.status === 'done') {
          result.value = t.result
          finishedSeq.value++
          return
        }
        if (t.status === 'error') throw new Error(t.message || '批量导入失败')
        await sleep(POLL_INTERVAL)
      }
    } catch (e) {
      error.value = e?.response ? errorText(e, '批量导入失败') : (e?.message || '批量导入失败')
    } finally {
      polling = false
      busy.value = false
    }
  }

  /**
   * 开始批量导入：上传压缩包，然后轮询后端任务。返回的 Promise 在任务结束后 resolve（出错也不 reject，
   * 错误写在 error 里），调用方不需要 try/catch；也可以不 await，离开页面不影响执行。
   * @param {File} file
   */
  async function start(file) {
    if (busy.value) return
    const list = [...products.value]
    busy.value = true
    resetRun()
    fileName.value = file.name
    activeProducts.value = list
    let taskId = ''
    try {
      const started = await uploadDepthArchive(file, list, overwrite.value, (p) => { uploadPercent.value = p })
      taskId = started.taskId
      activeProducts.value = started.products || list
      stage.value = 'import'
    } catch (e) {
      error.value = errorText(e, '批量导入失败')
      busy.value = false
      return
    }
    await poll(taskId)
  }

  /**
   * 页面（重新）进入时调用：
   * - store 里本来就有进行中的任务（切页面回来）：什么也不用做，轮询还在跑；
   * - 否则问后端有没有运行中的任务（应用被刷新 / 重新打开）：有就接管轮询并显示进度。
   * 只恢复「运行中」的任务，已结束的旧结果不再展示，避免一进页面就看到很久以前的结果。
   */
  async function restore() {
    if (busy.value || polling) return
    try {
      const t = await getDepthArchiveTask()
      if (t.status !== 'running') return
      busy.value = true
      resetRun()
      stage.value = 'import'
      fileName.value = t.originalName
      activeProducts.value = t.products || []
      done.value = t.done
      total.value = t.total
      current.value = t.current
      poll(t.taskId)
    } catch {
      // 没有任务（404 + noTask）或后端暂时不可用：保持空闲状态
    }
  }

  return {
    products, overwrite,
    busy, stage, percent, stageText, done, total, current, fileName, activeProducts, result, error, finishedSeq,
    start, restore
  }
})
