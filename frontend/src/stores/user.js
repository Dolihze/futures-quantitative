import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// 登录态只保存在 sessionStorage：应用窗口关闭后自动失效，
// 每次启动客户端都会先进入登录页（localStorage 会在重启后残留，导致直接进入主页）。
const AUTH_KEYS = ['username', 'broker', 'isLoggedIn']

// 清理旧版本遗留在 localStorage 中的登录态
AUTH_KEYS.forEach(key => localStorage.removeItem(key))

export const useUserStore = defineStore('user', () => {
  const username = ref(sessionStorage.getItem('username') || '')
  const broker = ref(sessionStorage.getItem('broker') || '')
  const isLoggedIn = ref(sessionStorage.getItem('isLoggedIn') === 'true')

  const userInfo = computed(() => ({
    username: username.value,
    broker: broker.value
  }))

  function setUser(user) {
    username.value = user.username
    broker.value = user.broker
    isLoggedIn.value = true

    sessionStorage.setItem('username', user.username)
    sessionStorage.setItem('broker', user.broker)
    sessionStorage.setItem('isLoggedIn', 'true')
  }

  function logout() {
    username.value = ''
    broker.value = ''
    isLoggedIn.value = false

    AUTH_KEYS.forEach(key => sessionStorage.removeItem(key))
  }

  return {
    username,
    broker,
    isLoggedIn,
    userInfo,
    setUser,
    logout
  }
})
