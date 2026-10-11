<template>
  <div class="trading-container">
    <!-- 顶部导航 -->
    <nav class="navbar">
      <div class="nav-left">
        <router-link to="/" class="back-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          返回首页
        </router-link>
      </div>
      <div class="nav-right">
        <div class="user-info">
          <div class="user-avatar">{{ userStore.username[0]?.toUpperCase() || 'U' }}</div>
          <span>{{ userStore.username || '未登录' }}</span>
        </div>
        <el-button type="danger" size="small" plain @click="handleLogout">退出登录</el-button>
      </div>
    </nav>

    <!-- 主内容 -->
    <div class="main-content">
      <div class="welcome-section">
        <h1>欢迎回来，{{ userStore.username || '交易员' }}</h1>
        <p>今日市场概览 · 祝您交易顺利</p>
      </div>

      <!-- 数据统计 -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">账户权益</div>
          <div class="stat-value">¥ {{ accountInfo.balance }}</div>
          <div class="stat-change">{{ accountInfo.balanceChange }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">可用资金</div>
          <div class="stat-value">¥ {{ accountInfo.available }}</div>
          <div class="stat-change">{{ accountInfo.availableChange }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">使用率</div>
          <div class="stat-value">{{ accountInfo.usageRate }}%</div>
          <div class="stat-change">{{ accountInfo.usageRateChange }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">今日盈亏</div>
          <div class="stat-value" :class="accountInfo.profitClass">¥ {{ accountInfo.profit }}</div>
          <div class="stat-change">{{ accountInfo.profitChange }}</div>
        </div>
      </div>

      <!-- 下单交易模块 -->
      <h2 class="section-title">下单交易</h2>
      
      <!-- 量化账号连接状态 -->
      <div class="quant-account-status">
        <div class="status-left">
          <div class="status-indicator" :class="{ connected: isQuantConnected }"></div>
          <span class="status-text" :class="{ connected: isQuantConnected }">
            {{ isQuantConnected ? '量化账号已连接' : '未连接量化账号' }}
          </span>
        </div>
        <button 
          class="connect-btn" 
          :class="{ connected: isQuantConnected }"
          @click="toggleQuantConnection"
          :disabled="isConnecting"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
          <span>{{ connectBtnText }}</span>
        </button>
      </div>

      <!-- 下单交易面板 -->
      <div class="trading-panel" :class="{ disabled: !isQuantConnected }">
        <!-- 第一行：价格和手数 -->
        <div class="trading-row">
          <!-- 价格输入 -->
          <div class="input-group">
            <div class="input-label">价格</div>
            <div class="input-wrapper" @click="togglePriceSelector">
              <input 
                type="text" 
                v-model="priceInput" 
                :readonly="isMarketPrice"
                :placeholder="pricePlaceholder"
              >
              <div class="input-btn-group">
                <button class="input-btn" @click.stop="adjustPrice(1)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="18 15 12 9 6 15"/>
                  </svg>
                </button>
                <button class="input-btn" @click.stop="adjustPrice(-1)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
              </div>
            </div>
            <!-- 价格类型下拉选择器 -->
            <div class="price-type-selector" :class="{ active: showPriceSelector }">
              <div 
                v-for="option in priceOptions" 
                :key="option.type"
                class="price-type-option"
                :class="{ selected: selectedPriceType === option.type }"
                @click.stop="selectPriceType(option)"
              >
                {{ option.label }}
              </div>
            </div>
          </div>

          <!-- 手数输入 -->
          <div class="input-group">
            <div class="input-label">手数</div>
            <div class="input-wrapper">
              <input 
                type="number" 
                v-model.number="volumeInput" 
                min="1"
              >
              <div class="input-btn-group">
                <button class="input-btn" @click="adjustVolume(1)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="18 15 12 9 6 15"/>
                  </svg>
                </button>
                <button class="input-btn" @click="adjustVolume(-1)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 第二行：交易操作 -->
        <div class="trading-row">
          <button class="trading-btn long" @click="executeTrade('long')">
            买多
          </button>
          <button class="trading-btn short" @click="executeTrade('short')">
            卖空
          </button>
          <button class="trading-btn close" @click="executeTrade('close')">
            平仓
          </button>
          <button class="trading-btn reverse" @click="executeTrade('reverse')">
            反手
          </button>
        </div>

        <!-- 第三行：快捷下单 -->
        <div class="quick-order-section">
          <button class="quick-order-btn" @click="quickOrder">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            一键快捷下单
          </button>
        </div>
      </div>
    </div>

    <!-- 自定义弹窗 -->
    <div class="modal-overlay" :class="{ active: showModal }" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
        </div>
        <div class="modal-title">{{ modalTitle }}</div>
        <div class="modal-message">{{ modalMessage }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { logout, quantLogin } from '@/api'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

// 量化账号连接状态
const isQuantConnected = ref(false)
const isConnecting = ref(false)

// 账户信息
const accountInfo = reactive({
  balance: '0.00',
  balanceChange: '暂无数据',
  available: '0.00',
  availableChange: '暂无数据',
  usageRate: '0.00',
  usageRateChange: '暂无数据',
  profit: '0.00',
  profitClass: 'zero',
  profitChange: '暂无数据'
})

// 价格相关
const priceInput = ref('市价')
const showPriceSelector = ref(false)
const selectedPriceType = ref('market')
const isMarketPrice = ref(true)
const pricePlaceholder = ref('市价')

const priceOptions = [
  { type: 'latest', label: '最新价' },
  { type: 'opponent', label: '对手价' },
  { type: 'overprice', label: '超价' },
  { type: 'market', label: '市价' }
]

// 手数
const volumeInput = ref(1)

// 弹窗
const showModal = ref(false)
const modalTitle = ref('')
const modalMessage = ref('')

// 计算属性：连接按钮文本
const connectBtnText = computed(() => {
  if (isConnecting.value) return '连接中...'
  if (isQuantConnected.value) return '断开连接'
  return '连接账号'
})

// 退出登录
const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await logout()
    userStore.logout()
    ElMessage.success('已退出登录')
    router.push('/login')
  } catch (error) {
    // 用户取消操作
  }
}

// 连接/断开量化账号
const toggleQuantConnection = async () => {
  if (isQuantConnected.value) {
    disconnectQuantAccount()
    return
  }

  // 连接量化账号
  isConnecting.value = true

  try {
    const result = await quantLogin()
    
    if (result.success) {
      isQuantConnected.value = true
      ElMessage.success('量化账号连接成功')
    } else {
      ElMessage.error(result.message || '连接失败')
    }
  } catch (error) {
    console.error('连接错误:', error)
    ElMessage.error('连接失败，请稍后重试')
  } finally {
    isConnecting.value = false
  }
}

// 断开量化账号连接
const disconnectQuantAccount = () => {
  isQuantConnected.value = false
  ElMessage.info('已断开量化账号连接')
}

// 切换价格选择器
const togglePriceSelector = (event) => {
  // 如果点击的是加减按钮，不触发下拉框
  if (event.target.closest('.input-btn')) {
    return
  }
  showPriceSelector.value = !showPriceSelector.value
}

// 选择价格类型
const selectPriceType = (option) => {
  selectedPriceType.value = option.type
  priceInput.value = option.label
  
  if (option.type === 'market') {
    isMarketPrice.value = true
    pricePlaceholder.value = '市价'
  } else {
    isMarketPrice.value = false
    priceInput.value = ''
    pricePlaceholder.value = option.label
  }
  
  showPriceSelector.value = false
}

// 调整价格
const adjustPrice = (direction) => {
  const currentPrice = parseFloat(priceInput.value)
  if (isNaN(currentPrice)) return
  
  const tickSize = 1 // 最小变动价位，可根据品种调整
  const newPrice = currentPrice + (direction * tickSize)
  
  if (newPrice > 0) {
    priceInput.value = newPrice.toFixed(2)
  }
}

// 调整手数
const adjustVolume = (direction) => {
  const newValue = volumeInput.value + direction
  if (newValue >= 1) {
    volumeInput.value = newValue
  }
}

// 执行交易
const executeTrade = (type) => {
  const tradeTypes = {
    'long': '买多',
    'short': '卖空',
    'close': '平仓',
    'reverse': '反手'
  }
  
  showModal.value = true
  modalTitle.value = '执行交易'
  modalMessage.value = `${tradeTypes[type]} | 价格：${priceInput.value} | 手数：${volumeInput.value}`
  
  // TODO: 这里添加实际的下单逻辑
  console.log('执行交易:', {
    type,
    price: priceInput.value,
    volume: volumeInput.value
  })
}

// 快捷下单
const quickOrder = () => {
  showModal.value = true
  modalTitle.value = '快捷下单'
  modalMessage.value = `价格：${priceInput.value} | 手数：${volumeInput.value}`
  
  // TODO: 这里添加实际的快捷下单逻辑
  console.log('快捷下单:', {
    price: priceInput.value,
    volume: volumeInput.value
  })
}

// 关闭弹窗
const closeModal = () => {
  showModal.value = false
}

// 点击外部关闭价格选择器
const handleClickOutside = (event) => {
  if (!event.target.closest('.input-group')) {
    showPriceSelector.value = false
  }
}

// 生命周期
onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.trading-container {
  min-height: 100vh;
  background: #0f172a;
}

/* 顶部导航栏 */
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 24px;
  background: rgba(15, 23, 42, 0.95);
  border-bottom: 1px solid rgba(59, 130, 246, 0.15);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-btn {
  padding: 6px 14px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 6px;
  color: #3b82f6;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
  text-decoration: none;
}

.back-btn:hover {
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.5);
}

.back-btn svg {
  width: 14px;
  height: 14px;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #94a3b8;
}

.user-avatar {
  width: 30px;
  height: 30px;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: white;
}

/* 主内容区 */
.main-content {
  padding: 32px 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.welcome-section {
  margin-bottom: 32px;
}

.welcome-section h1 {
  font-size: 24px;
  font-weight: 700;
  color: #f1f5f9;
  margin-bottom: 8px;
}

.welcome-section p {
  font-size: 14px;
  color: #64748b;
}

/* 数据统计 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}

.stat-card {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(71, 85, 105, 0.3);
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.2s, transform 0.2s;
}

.stat-card:hover {
  border-color: rgba(59, 130, 246, 0.4);
  transform: translateY(-2px);
}

.stat-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #f1f5f9;
}

.stat-value.positive { color: #ef4444; }  /* 盈利 - 红色 */
.stat-value.negative { color: #22c55e; }  /* 亏损 - 绿色 */
.stat-value.zero { color: #f1f5f9; }  /* 0 - 白色 */

.stat-change {
  font-size: 12px;
  margin-top: 4px;
  color: #64748b;
}

/* 下单交易模块 */
.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 16px;
}

/* 量化账号连接状态 */
.quant-account-status {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(71, 85, 105, 0.3);
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.status-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.4);
  animation: pulse 2s infinite;
}

.status-indicator.connected {
  background: #22c55e;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.4);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.status-text {
  font-size: 13px;
  color: #94a3b8;
}

.status-text.connected {
  color: #22c55e;
}

.connect-btn {
  padding: 8px 16px;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 6px;
  color: #3b82f6;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.connect-btn:hover {
  background: rgba(59, 130, 246, 0.25);
  border-color: rgba(59, 130, 246, 0.5);
}

.connect-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.connect-btn.connected {
  background: rgba(34, 197, 94, 0.15);
  border-color: rgba(34, 197, 94, 0.3);
  color: #22c55e;
}

.connect-btn svg {
  width: 14px;
  height: 14px;
}

/* 交易面板禁用状态 */
.trading-panel.disabled {
  opacity: 0.5;
  pointer-events: none;
  position: relative;
}

.trading-panel.disabled::after {
  content: '请先连接量化账号';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(15, 23, 42, 0.9);
  padding: 12px 24px;
  border-radius: 8px;
  color: #f87171;
  font-size: 14px;
  font-weight: 600;
  border: 1px solid rgba(239, 68, 68, 0.3);
  z-index: 10;
}

.trading-panel {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(71, 85, 105, 0.3);
  border-radius: 12px;
  padding: 24px;
}

.trading-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: stretch;
}

.trading-row:last-child {
  margin-bottom: 0;
}

/* 输入框组件 */
.input-group {
  flex: 1;
  position: relative;
}

.input-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(71, 85, 105, 0.3);
  border-radius: 8px;
  transition: all 0.2s;
  height: 48px;
}

.input-wrapper:focus-within {
  border-color: rgba(59, 130, 246, 0.5);
  background: rgba(15, 23, 42, 0.8);
}

.input-wrapper input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: #f1f5f9;
  font-size: 16px;
  font-weight: 600;
  padding: 0 12px;
  height: 100%;
}

.input-wrapper input::-webkit-inner-spin-button,
.input-wrapper input::-webkit-outer-spin-button {
  -webkit-appearance: none;
}

.input-btn-group {
  display: flex;
  flex-direction: column;
  border-left: 1px solid rgba(71, 85, 105, 0.3);
}

.input-btn {
  flex: 1;
  width: 32px;
  background: transparent;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.input-btn:hover {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.input-btn:first-child {
  border-bottom: 1px solid rgba(71, 85, 105, 0.3);
}

.input-btn svg {
  width: 14px;
  height: 14px;
}

/* 价格下拉选择器 */
.price-type-selector {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  width: 100%;
  background: rgba(30, 41, 59, 0.98);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
  padding: 6px;
  display: none;
  z-index: 10;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.price-type-selector.active {
  display: block;
}

.price-type-option {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;
  color: #cbd5e1;
}

.price-type-option:hover {
  background: rgba(59, 130, 246, 0.1);
  color: #f1f5f9;
}

.price-type-option.selected {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

/* 交易按钮 */
.trading-btn {
  flex: 1;
  height: 48px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.trading-btn.long {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.trading-btn.long:hover {
  background: rgba(239, 68, 68, 0.25);
  border-color: rgba(239, 68, 68, 0.5);
}

.trading-btn.short {
  background: rgba(34, 197, 94, 0.15);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: #22c55e;
}

.trading-btn.short:hover {
  background: rgba(34, 197, 94, 0.25);
  border-color: rgba(34, 197, 94, 0.5);
}

.trading-btn.close {
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: #3b82f6;
}

.trading-btn.close:hover {
  background: rgba(59, 130, 246, 0.25);
  border-color: rgba(59, 130, 246, 0.5);
}

.trading-btn.reverse {
  background: rgba(139, 92, 246, 0.15);
  border: 1px solid rgba(139, 92, 246, 0.3);
  color: #8b5cf6;
}

.trading-btn.reverse:hover {
  background: rgba(139, 92, 246, 0.25);
  border-color: rgba(139, 92, 246, 0.5);
}

/* 快捷下单按钮 */
.quick-order-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(71, 85, 105, 0.3);
}

.quick-order-btn {
  width: 100%;
  height: 52px;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.quick-order-btn:hover {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.3);
}

.quick-order-btn svg {
  width: 18px;
  height: 18px;
}

/* 自定义弹窗样式 */
.modal-overlay {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  z-index: 1000;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.2s ease;
}

.modal-overlay.active {
  display: flex;
}

.modal-content {
  background: rgba(30, 41, 59, 0.95);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 16px;
  padding: 32px 40px;
  text-align: center;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  animation: slideUp 0.3s ease;
}

.modal-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 16px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(139, 92, 246, 0.2));
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-icon svg {
  width: 28px;
  height: 28px;
  color: #3b82f6;
}

.modal-title {
  font-size: 18px;
  font-weight: 600;
  color: #f1f5f9;
  margin-bottom: 8px;
}

.modal-message {
  font-size: 14px;
  color: #94a3b8;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Element Plus 样式覆盖 */
:deep(.el-button--danger.is-plain) {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: #f87171;
}

:deep(.el-button--danger.is-plain:hover) {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.5);
}
</style>
