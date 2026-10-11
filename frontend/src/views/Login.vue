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
.login-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%);
  overflow: hidden;
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
}

/* 动态背景网格 */
.login-container::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image:
    linear-gradient(rgba(59, 130, 246, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(59, 130, 246, 0.08) 1px, transparent 1px);
  background-size: 40px 40px;
  animation: gridMove 20s linear infinite;
}

@keyframes gridMove {
  0%   { transform: translate(0, 0); }
  100% { transform: translate(40px, 40px); }
}

/* 浮动光点 */
.glow-dot {
  position: absolute;
  border-radius: 50%;
  background: rgba(59, 130, 246, 0.4);
  filter: blur(2px);
  animation: float 8s ease-in-out infinite;
}
.glow-dot:nth-child(1) { width: 6px; height: 6px; top: 20%; left: 15%; animation-delay: 0s; }
.glow-dot:nth-child(2) { width: 4px; height: 4px; top: 60%; left: 80%; animation-delay: 2s; }
.glow-dot:nth-child(3) { width: 8px; height: 8px; top: 80%; left: 25%; animation-delay: 4s; }
.glow-dot:nth-child(4) { width: 5px; height: 5px; top: 30%; left: 70%; animation-delay: 1s; }
.glow-dot:nth-child(5) { width: 3px; height: 3px; top: 70%; left: 50%; animation-delay: 3s; }

@keyframes float {
  0%, 100% { transform: translateY(0) scale(1); opacity: 0.4; }
  50%       { transform: translateY(-30px) scale(1.5); opacity: 1; }
}

.login-wrapper {
  position: relative;
  z-index: 10;
  width: 100%;
  max-width: 420px;
  padding: 0 20px;
}

/* Logo 区域 */
.logo-area {
  text-align: center;
  margin-bottom: 32px;
}

.logo-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 32px rgba(59, 130, 246, 0.4);
}

.logo-icon svg {
  width: 36px;
  height: 36px;
}

.logo-title {
  font-size: 22px;
  font-weight: 700;
  color: #f1f5f9;
  letter-spacing: 2px;
}

.logo-subtitle {
  font-size: 13px;
  color: #64748b;
  margin-top: 6px;
  letter-spacing: 1px;
}

/* 登录卡片 */
.login-card {
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 20px;
  padding: 36px 32px;
  backdrop-filter: blur(20px);
  box-shadow:
    0 20px 60px rgba(0, 0, 0, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.card-header {
  text-align: center;
  margin-bottom: 28px;
}

.card-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: #e2e8f0;
}

.card-header p {
  font-size: 13px;
  color: #64748b;
  margin-top: 6px;
}

/* 输入框容器 */
.input-wrapper {
  position: relative;
  width: 100%;
}

.input-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: #475569;
  pointer-events: none;
  transition: color 0.2s;
  z-index: 10;
}

.input-wrapper:focus-within .input-icon {
  color: #3b82f6;
}

/* 错误提示 */
.error-msg {
  display: none;
  align-items: center;
  gap: 8px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 20px;
  font-size: 13px;
  color: #f87171;
}

.error-msg.show {
  display: flex;
}

.error-msg svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* 表单选项 */
.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.forgot-link {
  font-size: 13px;
  color: #3b82f6;
  text-decoration: none;
  transition: color 0.2s;
}

.forgot-link:hover {
  color: #60a5fa;
}

/* 登录按钮 */
.login-btn {
  width: 100%;
  height: 48px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border: none;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  color: white;
  cursor: pointer;
  letter-spacing: 1px;
  transition: all 0.3s;
  position: relative;
  overflow: hidden;
}

.login-btn:hover {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.4);
  transform: translateY(-1px);
}

.login-btn:active {
  transform: translateY(0);
}

.login-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
}

/* 底部信息 */
.footer-info {
  text-align: center;
  margin-top: 24px;
  font-size: 12px;
  color: #334155;
}

.footer-info a {
  color: #475569;
  text-decoration: none;
}

.footer-info a:hover {
  color: #64748b;
}

/* 调试模式按钮 */
.debug-btn {
  margin-top: 20px;
  padding: 10px 28px;
  background: rgba(249, 115, 22, 0.15);
  border: 1px solid rgba(249, 115, 22, 0.4);
  border-radius: 8px;
  color: #fb923c;
  font-size: 13px;
  text-decoration: none;
  transition: all 0.2s;
}

.debug-btn:hover {
  background: rgba(249, 115, 22, 0.25);
  border-color: rgba(249, 115, 22, 0.6);
}

/* Element Plus 样式覆盖 */
:deep(.el-form-item__label) {
  color: #94a3b8;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
}

:deep(.el-input__wrapper) {
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 10px;
  box-shadow: none;
  height: 46px;
  padding-left: 42px;
}

:deep(.el-input__wrapper:hover) {
  border-color: rgba(59, 130, 246, 0.5);
}

:deep(.el-input__wrapper.is-focus) {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

:deep(.el-input__inner) {
  color: #e2e8f0;
  font-size: 14px;
}

:deep(.el-input__prefix) {
  display: none;
}

/* 自定义下拉选择器样式 */
.custom-broker-select {
  width: 100%;
}

:deep(.custom-broker-select .el-input__wrapper) {
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 10px;
  box-shadow: none;
  height: 46px;
  padding-left: 42px;
  cursor: pointer;
}

:deep(.custom-broker-select .el-input__wrapper:hover) {
  border-color: rgba(59, 130, 246, 0.5);
}

:deep(.custom-broker-select .el-input__wrapper.is-focus) {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

:deep(.el-select-dropdown) {
  background: #1e293b;
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.55);
}

:deep(.el-select-dropdown__item) {
  color: #cbd5e1;
  padding: 8px 14px;
}

:deep(.el-select-dropdown__item:hover) {
  background: rgba(59, 130, 246, 0.12);
  color: #f1f5f9;
}

:deep(.el-select-dropdown__item.selected) {
  background: rgba(59, 130, 246, 0.18);
  color: #60a5fa;
}

:deep(.el-select-group__title) {
  color: #475569;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1px;
  padding: 6px 14px 4px;
}

:deep(.el-checkbox__label) {
  color: #94a3b8;
  font-size: 13px;
}

:deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: #3b82f6;
  border-color: #3b82f6;
}

:deep(.el-button--primary) {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border: none;
}

:deep(.el-button--primary:hover) {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.4);
  transform: translateY(-1px);
}

:deep(.el-button--warning.is-plain) {
  background: rgba(249, 115, 22, 0.15);
  border-color: rgba(249, 115, 22, 0.4);
  color: #fb923c;
}

:deep(.el-button--warning.is-plain:hover) {
  background: rgba(249, 115, 22, 0.25);
  border-color: rgba(249, 115, 22, 0.6);
}

/* 选项标签 */
.option-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(59, 130, 246, 0.15);
  color: #60a5fa;
}

.option-tag.hot {
  background: rgba(249, 115, 22, 0.15);
  color: #fb923c;
}
</style>
