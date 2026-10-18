<template>
  <div class="login-container">
    <!-- 浮动光点 -->
    <div class="glow-dot"></div>
    <div class="glow-dot"></div>
    <div class="glow-dot"></div>
    <div class="glow-dot"></div>
    <div class="glow-dot"></div>

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
          <p>请输入您的期货交易账户信息</p>
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
              >
                <el-option-group
                  v-for="group in brokerGroups"
                  :key="group.label"
                  :label="group.label"
                >
                  <el-option
                    v-for="item in group.items"
                    :key="item.value"
                    :label="item.name"
                    :value="item.value"
                  >
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                      <span>{{ item.name }}</span>
                      <span v-if="item.tag" :class="['option-tag', item.tagType || '']">{{ item.tag }}</span>
                    </div>
                  </el-option>
                </el-option-group>
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

        <!-- 调试模式按钮 -->
        <div style="text-align: center;">
          <el-button
            type="warning"
            plain
            @click="handleDebugLogin"
            class="debug-btn"
          >
            🔧 调试模式（跳过登录）
          </el-button>
        </div>
      </div>

      <div class="footer-info">
        <p>本系统仅供合法期货交易使用 · 未经授权禁止访问</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getBrokers, login } from '@/api'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const loginFormRef = ref(null)
const loading = ref(false)
const errorMsg = ref('')
const rememberAccount = ref(false)

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

// 加载期货公司列表
onMounted(async () => {
  try {
    const data = await getBrokers()
    brokerGroups.value = data
    
    // 恢复记住的账号
    const savedUsername = localStorage.getItem('futures_username')
    const savedBroker = localStorage.getItem('futures_broker')
    if (savedUsername) {
      loginForm.username = savedUsername
      rememberAccount.value = true
    }
    if (savedBroker) {
      loginForm.broker = savedBroker
    }
  } catch (error) {
    console.error('加载期货公司列表失败:', error)
    errorMsg.value = '期货公司数据加载失败，请刷新重试'
  }
})

// 处理登录
const handleLogin = async () => {
  if (!loginFormRef.value) return
  
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    errorMsg.value = ''
    
    try {
      const result = await login(loginForm)
      
      if (result.success) {
        // 保存账号信息
        if (rememberAccount.value) {
          localStorage.setItem('futures_username', loginForm.username)
          localStorage.setItem('futures_broker', loginForm.broker)
        } else {
          localStorage.removeItem('futures_username')
          localStorage.removeItem('futures_broker')
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
      errorMsg.value = '网络连接失败，请检查网络后重试'
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
