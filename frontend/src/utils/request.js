import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const request = axios.create({
  // 开发时为空（相对路径，走 Vite 代理）；Tauri 打包后由 main.js 启动时设置为 http://127.0.0.1:<随机端口>
  baseURL: '',
  timeout: 30000,
  withCredentials: true
})

/**
 * 设置后端根地址（Tauri 打包后端口是运行时决定的）。
 * @param {string} base 形如 http://127.0.0.1:53211，空串表示相对路径
 */
export function setBackendBase(base) {
  request.defaults.baseURL = base
}

// 请求拦截器
request.interceptors.request.use(
  config => {
    return config
  },
  error => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    // 调用方可通过 config.silent = true 关闭全局错误提示，自行处理失败
    if (error.config?.silent) {
      return Promise.reject(error)
    }
    if (error.response) {
      if (error.response.status === 401) {
        ElMessage.error('未登录，请先登录')
        router.push('/login')
      } else if (error.response.status === 500) {
        ElMessage.error('服务器错误')
      } else {
        ElMessage.error(error.response.data?.message || '请求失败')
      }
    } else if (error.request) {
      ElMessage.error('网络错误，请检查网络连接')
    } else {
      ElMessage.error('请求配置错误')
    }
    return Promise.reject(error)
  }
)

/**
 * 响应拦截器已把 AxiosResponse 解包成 response.data，所以对调用方来说返回的是业务 JSON，
 * 而不是 axios 声明的 AxiosResponse。这里给出准确的类型，api/*.js 用它声明返回值。
 * @template [T=import('@/api/types').ApiResult]
 * @param {import('axios').AxiosRequestConfig & { silent?: boolean }} config
 * @returns {Promise<T>}
 */
export function http(config) {
  return /** @type {Promise<any>} */ (request(config))
}

export default request
