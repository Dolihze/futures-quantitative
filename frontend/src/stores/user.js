import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useUserStore = defineStore('user', () => {
  const username = ref(localStorage.getItem('username') || '')
  const broker = ref(localStorage.getItem('broker') || '')
  const isLoggedIn = ref(localStorage.getItem('isLoggedIn') === 'true')

  const userInfo = computed(() => ({
    username: username.value,
    broker: broker.value
  }))

  function setUser(user) {
    username.value = user.username
    broker.value = user.broker
    isLoggedIn.value = true
    
    localStorage.setItem('username', user.username)
    localStorage.setItem('broker', user.broker)
    localStorage.setItem('isLoggedIn', 'true')
  }

  function logout() {
    username.value = ''
    broker.value = ''
    isLoggedIn.value = false
    
    localStorage.removeItem('username')
    localStorage.removeItem('broker')
    localStorage.removeItem('isLoggedIn')
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
