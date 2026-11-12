<template>
  <div class="login-container">
    <!-- 浮动光点 -->
    <div class="glow-dot"></div>
    <div class="glow-dot"></div>
    <div class="glow-dot"></div>
    <div class="glow-dot"></div>
    <div class="glow-dot"></div>

    <!-- 右上角：主题切换 + 调试模式（只有一个扳手图标，悬停提示“调试模式”） -->
    <div class="theme-corner">
      <ThemeSwitcher />
      <el-tooltip content="调试模式" placement="bottom" :show-after="200">
        <button type="button" class="debug-btn" aria-label="调试模式" @click="handleDebugLogin">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
        </button>
      </el-tooltip>
    </div>

    <div class="login-wrapper">
      <!-- Logo -->
      <div class="logo-area">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 20h18M3 20l4-8 4 4 4-10 4 6" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          </svg>
        </div>
        <div class="logo-title">期货量化交易系统</div>
        <div class="logo-subtitle">Futures Quantitative Trading</div>
      </div>

      <!-- 登录卡片 -->
      <div class="login-card">
        <div class="card-header">
          <h2>账户登录</h2>
        </div>

        <!-- 错误提示 -->
        <div v-if="errorMsg" class="error-msg show">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{{ errorMsg }}</span>
        </div>

        <el-form
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          autocomplete="off"
          @submit.prevent="handleLogin"
        >
          <!-- 期货公司 -->
          <el-form-item label="期货公司" prop="broker">
            <div class="input-wrapper">
              <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 21h18"/>
                <path d="M5 21V7l7-4 7 4v14"/>
                <path d="M9 21v-6h6v6"/>
              </svg>
              <el-select
                v-model="loginForm.broker"
                placeholder="请选择期货公司"
                filterable
                class="custom-broker-select"
                popper-class="broker-select-popper"
              >
                <!-- 不展示分组标题，平铺所有选项（分组数据仍保留在 brokerGroups 中） -->
                <el-option
                  v-for="item in brokerOptions"
                  :key="item.value"
                  :label="item.name"
                  :value="item.value"
                >
                  <div class="broker-option">
                    <span>{{ item.name }}</span>
                    <span v-if="item.tag" :class="['option-tag', item.tagType || '']">{{ item.tag }}</span>
                  </div>
                </el-option>
              </el-select>
            </div>
          </el-form-item>

          <!-- 账号 -->
          <el-form-item label="交易账号" prop="username">
            <div class="input-wrapper">
              <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              <el-input
                v-model="loginForm.username"
                placeholder="请输入交易账号"
                class="custom-input"
              />
            </div>
          </el-form-item>

          <!-- 密码 -->
          <el-form-item label="交易密码" prop="password">
            <div class="input-wrapper">
              <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="请输入交易密码"
                show-password
                class="custom-input"
                @keyup.enter="handleLogin"
              />
            </div>
          </el-form-item>

          <!-- 记住密码 & 忘记密码 -->
          <div class="form-options">
            <label class="checkbox-wrapper">
              <el-checkbox v-model="rememberAccount">记住账号</el-checkbox>
            </label>
            <a href="#" class="forgot-link">忘记密码？</a>
          </div>

          <!-- 登录按钮 -->
          <el-form-item>
            <el-button
              type="primary"
              :loading="loading"
              @click="handleLogin"
              class="login-btn"
            >
              <span v-if="!loading">安 全 登 录</span>
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="footer-info">
        <p>本系统仅供合法期货交易使用 · 未经授权禁止访问</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getBrokers, login, getSavedCredentials } from '@/api'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const loginFormRef = ref(null)
const loading = ref(false)
const errorMsg = ref('')
const rememberAccount = ref(true)

const loginForm = reactive({
  broker: '',
  username: '',
  password: ''
})

const loginRules = reactive({
  broker: [
    { required: true, message: '请选择期货公司', trigger: 'change' }
  ],
  username: [
    { required: true, message: '请输入交易账号', trigger: 'blur' },
    { min: 3, message: '账号长度至少3位', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入交易密码', trigger: 'blur' },
    { min: 6, message: '密码长度至少6位', trigger: 'blur' }
  ]
})

const brokerGroups = ref([])

// 平铺后的下拉选项（不显示分组标题）
const brokerOptions = computed(() => brokerGroups.value.flatMap((group) => group.items))

// 当前对外开放的期货公司（value 对应 data/brokers.json）。
// 全量数据仍由接口返回、不做删除；以后要开放更多公司，往这里追加 value 即可，
// 设为 null 则展示全部。
// simnow / simnow_724：SimNow 仿真的第一套（交易时段）和 7x24 环境（公开参数，用于联调验证登录流程，
// 拿到真实参数后可移除）。
const ENABLED_BROKERS = ['citic', 'guoyuan', 'simnow', 'simnow_724']

const filterBrokerGroups = (groups) => {
  if (!ENABLED_BROKERS) return groups
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => ENABLED_BROKERS.includes(item.value))
    }))
    .filter((group) => group.items.length > 0)
}

// 加载期货公司列表
onMounted(async () => {
  try {
    const data = await getBrokers()
    brokerGroups.value = filterBrokerGroups(data)
  } catch (error) {
    console.error('加载期货公司列表失败:', error)
    errorMsg.value = '期货公司数据加载失败，请刷新重试'
    return
  }

  await restoreSavedCredentials()
})

// 恢复「记住账号」保存的期货公司 / 账号 / 密码（密码由后端用 Windows DPAPI 加密保存在本机）
const restoreSavedCredentials = async () => {
  try {
    const saved = await getSavedCredentials()
    if (!saved?.saved) return

    rememberAccount.value = true
    loginForm.username = saved.username
    loginForm.password = saved.password || ''
    // 仅当记住的期货公司仍在可选列表中时才恢复
    if (brokerGroups.value.some((g) => g.items.some((i) => i.value === saved.broker))) {
      loginForm.broker = saved.broker
    }
  } catch (error) {
    // 读取失败（后端未就绪等）不影响正常手动登录
    console.warn('读取已保存的账号失败:', error)
  }
}

// 处理登录
const handleLogin = async () => {
  if (!loginFormRef.value) return
  
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    errorMsg.value = ''
    
    try {
      // remember：由后端在登录成功后保存（勾选）或清除（未勾选）凭据
      const result = await login({ ...loginForm, remember: rememberAccount.value })
      
      if (result.success) {
        // 清理旧版本遗留在 localStorage 的账号信息
        localStorage.removeItem('futures_username')
        localStorage.removeItem('futures_broker')

        if (rememberAccount.value && !result.password_saved) {
          ElMessage.warning('已记住账号，但当前系统不支持安全保存密码，下次需重新输入密码')
        }

        // 保存用户信息到 store
        userStore.setUser({
          username: loginForm.username,
          broker: loginForm.broker
        })
        
        ElMessage.success('登录成功')
        router.push('/')
      } else {
        errorMsg.value = result.message || '账号或密码错误'
      }
    } catch (error) {
      errorMsg.value = error.code === 'ECONNABORTED'
        ? '登录超时，请检查网络后重试'
        : '网络连接失败，请检查网络后重试'
    } finally {
      loading.value = false
    }
  })
}

// 调试模式登录
const handleDebugLogin = async () => {
  userStore.setUser({
    username: '管理员',
    broker: 'debug'
  })
  
  ElMessage.success('调试模式登录成功')
  router.push('/')
}
</script>

<style scoped>
@import '@/styles/Login.css';
</style>

<!-- 下拉面板通过 teleport 挂到 body 下，scoped / :deep 命中不了，需以非 scoped 方式引入 -->
<style>
@import '@/styles/LoginPopper.css';
</style>
