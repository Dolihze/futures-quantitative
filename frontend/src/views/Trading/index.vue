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

      <!-- 下单交易模块标题 -->
      <div class="section-header">
        <h2 class="section-title">下单交易</h2>
        <div class="connection-status">
          <div class="status-indicator" :class="{ connected: isQuantConnected }"></div>
          <span class="status-text" :class="{ connected: isQuantConnected }">
            {{ isQuantConnected ? '量化账号已连接' : '未连接量化账号' }}
          </span>
          <el-switch
            v-model="isQuantConnected"
            :loading="isConnecting"
            @change="toggleQuantConnection"
            :disabled="isConnecting"
            size="small"
            class="connection-switch"
            style="--el-switch-button-size: 14px; --el-switch-height: 20px;"
          >
            <template #loading>
              <svg class="switch-loading-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" stroke-opacity="0.25" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round" />
              </svg>
            </template>
          </el-switch>
        </div>
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
const toggleQuantConnection = async (val) => {
  // 如果正在连接中，不执行任何操作
  if (isConnecting.value) {
    return
  }

  // 如果新状态是已连接，执行连接逻辑
  if (val) {
    isConnecting.value = true
    try {
      const result = await quantLogin()
      
      if (result.success) {
        isQuantConnected.value = true
        ElMessage.success('量化账号连接成功')
      } else {
        ElMessage.error(result.message || '连接失败')
        isQuantConnected.value = false
      }
    } catch (error) {
      console.error('连接错误:', error)
      ElMessage.error('连接失败，请稍后重试')
      isQuantConnected.value = false
    } finally {
      isConnecting.value = false
    }
  } else {
    // 断开连接
    disconnectQuantAccount()
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
@import '@/styles/Trading.css';
</style>
