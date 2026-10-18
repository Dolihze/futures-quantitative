<template>
  <div class="home-container">
    <!-- 顶部导航 -->
    <nav class="navbar">
      <div class="nav-left">
        <div class="nav-logo">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 20h18M3 20l4-8 4 4 4-10 4 6" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          </svg>
        </div>
        <span class="nav-title">期货量化交易系统</span>
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
        <p>选择您需要的功能模块，开始今天的交易</p>
      </div>

      <!-- 功能卡片 -->
      <div class="feature-grid">
        <!-- 交易卡片 -->
        <router-link to="/trading" class="feature-card">
          <div class="feature-icon trading">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>
              <polyline points="16 7 22 7 22 13"/>
            </svg>
          </div>
          <div class="feature-title">下单交易</div>
          <div class="feature-description">
            实时行情数据，支持买多、卖空、平仓、反手等操作，快捷下单功能
          </div>
          <div class="feature-arrow">
            <span>进入交易</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </div>
        </router-link>

        <!-- 量化回测卡片 -->
        <router-link to="/backtest" class="feature-card" @click="handleBacktestClick">
          <div class="feature-icon backtest">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
              <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
              <line x1="12" y1="22.08" x2="12" y2="12"/>
            </svg>
          </div>
          <div class="feature-title">量化回测</div>
          <div class="feature-description">
            历史数据回测，策略验证，绩效分析，风险评估
          </div>
          <div class="feature-arrow">
            <span>进入回测</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </div>
        </router-link>
      </div>
    </div>

    <!-- 加载遮罩层 -->
    <div v-if="loading" class="loading-overlay">
      <div class="spinner"></div>
      <div class="loading-text">正在加载...</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { logout } from '@/api'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)

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

// 回测卡片点击处理（显示加载遮罩）
const handleBacktestClick = (e) => {
  e.preventDefault()
  loading.value = true
  // 延迟跳转，确保遮罩层能显示出来
  setTimeout(() => {
    router.push('/backtest')
  }, 100)
}
</script>

<style scoped>
@import '@/styles/Home.css';
</style>
