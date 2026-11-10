<template>
  <div class="backtest-container">
    <!-- 顶部导航栏 -->
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
          <span class="username">{{ userStore.username || '未登录' }}</span>
        </div>
        <el-button type="danger" size="small" plain @click="handleLogout">退出登录</el-button>
      </div>
    </nav>

    <div class="main-container">
      <!-- 左侧控制面板 -->
      <aside class="sidebar">
        <div class="control-panel">
          <h3>⚙️ 回测参数设置</h3>
          <el-form label-position="top" size="default">
            <el-form-item label="合约代码">
              <el-select v-model="params.symbol" placeholder="请选择合约">
                <el-option label="燃料油FU2611" value="FU2611" />
              </el-select>
            </el-form-item>
            <el-form-item label="数据周期">
              <el-select v-model="params.period" placeholder="请选择周期">
                <el-option label="1分钟" value="1" />
                <el-option label="5分钟" value="5" />
                <el-option label="15分钟" value="15" />
                <el-option label="30分钟" value="30" />
                <el-option label="60分钟" value="60" />
              </el-select>
            </el-form-item>
            <el-form-item label="数据范围">
              <el-select v-model="params.days" placeholder="请选择范围">
                <el-option label="近7天" :value="7" />
                <el-option label="近30天" :value="30" />
                <el-option label="近60天" :value="60" />
                <el-option label="近90天" :value="90" />
              </el-select>
            </el-form-item>
            <el-button 
              type="primary" 
              @click="loadKlineData" 
              :loading="loading"
              :disabled="loading"
              style="width: 100%; margin-top: 10px;"
            >
              📈 加载数据
            </el-button>
          </el-form>
        </div>

        <el-button 
          type="danger" 
          @click="runBacktest"
          :loading="backtesting"
          :disabled="backtesting || !currentKlineData"
          style="width: 100%; margin-bottom: 20px;"
        >
          🔄 反转信号回测
        </el-button>

        <!-- 回测结果展示 -->
        <div v-if="backtestResult" class="backtest-result">
          <h4>📊 回测结果</h4>
          <div class="result-grid">
            <div class="result-item">
              <div class="result-label">开仓次数</div>
              <div class="result-value neutral">{{ backtestResult.openCount }}</div>
            </div>
            <div class="result-item">
              <div class="result-label">胜率</div>
              <div 
                class="result-value"
                :class="{
                  'positive': backtestResult.winRate >= 50,
                  'negative': backtestResult.winRate < 50
                }"
              >
                {{ backtestResult.winRate.toFixed(2) }}%
              </div>
            </div>
            <div class="result-item">
              <div class="result-label">总盈亏</div>
              <div 
                class="result-value"
                :class="{
                  'positive': backtestResult.totalProfit > 0,
                  'negative': backtestResult.totalProfit < 0,
                  'neutral': backtestResult.totalProfit === 0
                }"
              >
                {{ backtestResult.totalProfit > 0 ? '+' : '' }}{{ backtestResult.totalProfit.toFixed(2) }}
              </div>
            </div>
            <div class="result-item">
              <div class="result-label">跨越时间</div>
              <div class="result-value neutral time-span">{{ backtestResult.timeSpan }}</div>
            </div>
          </div>
        </div>

        <!-- 交易记录 -->
        <div v-if="backtestResult && backtestResult.trades.length > 0" class="backtest-result trade-records">
          <h4>📝 交易记录</h4>
          <div class="trade-list">
            <div 
              v-for="(trade, index) in backtestResult.trades" 
              :key="index"
              class="trade-item"
              :style="{ borderLeftColor: trade.type === 'long' ? '#ef4444' : '#22c55e' }"
            >
              <div class="trade-header">
                <span 
                  class="trade-type"
                  :style="{ color: trade.type === 'long' ? '#ef4444' : '#22c55e' }"
                >
                  #{{ index + 1 }} {{ trade.type === 'long' ? '多头' : '空头' }}
                </span>
                <span 
                  class="trade-profit"
                  :style="{ color: trade.profit > 0 ? '#ef4444' : trade.profit < 0 ? '#22c55e' : '#fff' }"
                >
                  {{ trade.profit > 0 ? '+' : '' }}{{ trade.profit.toFixed(2) }}元
                </span>
              </div>
              <div class="trade-details">
                <div>开仓: {{ trade.entryTime }}</div>
                <div>平仓: {{ trade.exitTime }}</div>
                <div>买点: {{ trade.entryPrice.toFixed(2) }} → 卖点: {{ trade.exitPrice.toFixed(2) }}</div>
                <div>原因: {{ trade.reason }}</div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 右侧图表区域 -->
      <div class="chart-container">
        <div class="chart-header">
          <h2>{{ chartTitle }}</h2>
          <div class="data-info">
            <div class="info-item">
              <span class="info-label">合约:</span>
              <span class="info-value">{{ params.symbol }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">周期:</span>
              <span class="info-value">{{ params.period }}分钟</span>
            </div>
            <div class="info-item">
              <span class="info-label">更新时间:</span>
              <span class="info-value">{{ updateTime }}</span>
            </div>
          </div>
        </div>
        
        <!-- 主K线图表 -->
        <div ref="klineChartRef" class="kline-chart"></div>
        
        <!-- 副指标图表 -->
        <div ref="indicatorChartRef" class="indicator-chart"></div>
      </div>
    </div>

    <!-- 加载遮罩 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在加载数据...</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { getKlineData, logout } from '@/api'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

// 全局状态
const loading = ref(false)
const backtesting = ref(false)
const params = reactive({
  symbol: 'FU2611',
  period: '5',
  days: 30
})

// 图表实例
const klineChartRef = ref(null)
const indicatorChartRef = ref(null)
let klineChart = null
let indicatorChart = null

// 数据存储
const currentKlineData = ref(null)
const currentIndicatorData = ref(null)
const backtestResult = ref(null)
const updateTime = ref('--')

// 图表标题
const chartTitle = computed(() => {
  return `${params.symbol} - ${params.period}分钟K线图`
})

// 期货品种配置
const INSTRUMENT_CONFIG = {
  'IF': { tickSize: 0.2, multiplier: 300 },
  'IC': { tickSize: 0.2, multiplier: 200 },
  'IH': { tickSize: 0.2, multiplier: 300 },
  'AU': { tickSize: 0.02, multiplier: 1000 },
  'AG': { tickSize: 1, multiplier: 15 },
  'CU': { tickSize: 10, multiplier: 5 },
  'RB': { tickSize: 1, multiplier: 10 },
  'I': { tickSize: 0.5, multiplier: 100 },
  'MA': { tickSize: 1, multiplier: 10 },
  'SA': { tickSize: 1, multiplier: 20 },
  'FG': { tickSize: 1, multiplier: 20 },
  'CF': { tickSize: 5, multiplier: 5 },
  'SR': { tickSize: 1, multiplier: 10 },
  'TA': { tickSize: 2, multiplier: 5 },
  'M': { tickSize: 1, multiplier: 10 },
  'Y': { tickSize: 2, multiplier: 10 },
  'P': { tickSize: 2, multiplier: 10 },
  'AP': { tickSize: 1, multiplier: 10 },
  'LH': { tickSize: 5, multiplier: 16 },
  'JD': { tickSize: 1, multiplier: 10 },
  'SC': { tickSize: 0.1, multiplier: 1000 },
  'FU': { tickSize: 1, multiplier: 10 },
  'RU': { tickSize: 5, multiplier: 10 },
  'SP': { tickSize: 2, multiplier: 10 }
}

const TRADE_LOTS = 5

// 获取品种配置
function getInstrumentConfig(symbol) {
  const code = symbol.replace(/\d+/g, '').toUpperCase()
  return INSTRUMENT_CONFIG[code] || { tickSize: 1, multiplier: 10 }
}

// 响应窗口大小变化 - 使用防抖
let resizeTimer = null
let isSyncing = false // 防止dataZoom无限循环

function handleResizeDebounced() {
  if (resizeTimer) {
    clearTimeout(resizeTimer)
  }
  resizeTimer = setTimeout(() => {
    if (klineChart) klineChart.resize()
    if (indicatorChart) indicatorChart.resize()
  }, 100)
}

function handleResize() {
  if (klineChart) klineChart.resize()
  if (indicatorChart) indicatorChart.resize()
}

// 初始化图表
function initCharts() {
  console.log('🔍 [initCharts] 开始初始化图表...')
  console.log('📊 klineChartRef.value:', klineChartRef.value)
  console.log('📊 klineChartRef尺寸:', klineChartRef.value?.getBoundingClientRect())
  
  klineChart = echarts.init(klineChartRef.value)
  
  const klineOption = {
    backgroundColor: '#16213e',
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross'
      },
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#00d4ff',
      textStyle: {
        color: '#fff'
      },
      formatter: function (params) {
        if (!params || !params[0]) return ''
        
        const param = params[0]
        const seriesData = param.seriesData?.[0] || param.data
        
        if (!seriesData || seriesData.length < 4) {
          return ''
        }
        
        const openPrice = seriesData[1]
        const closePrice = seriesData[2]
        const highPrice = seriesData[3]
        const lowPrice = seriesData[4]
        
        return `
          <div style="font-weight: bold; margin-bottom: 5px;">${param.axisValue}</div>
          <div>开盘: ${openPrice.toFixed(2)}</div>
          <div>收盘: ${closePrice.toFixed(2)}</div>
          <div>最高: ${highPrice.toFixed(2)}</div>
          <div>最低: ${lowPrice.toFixed(2)}</div>
        `
      }
    },
    grid: {
      left: '10%',
      right: '5%',
      top: '5%',
      bottom: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: [],
      axisLine: {
        lineStyle: {
          color: '#333'
        }
      },
      axisLabel: {
        show: false
      },
      axisTick: {
        show: false
      }
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: {
        lineStyle: {
          color: '#333'
        }
      },
      axisLabel: {
        color: '#aaa'
      },
      splitLine: {
        lineStyle: {
          color: '#2a2a3e'
        }
      }
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0],
        start: 0,
        end: 100
      },
      {
        show: true,
        xAxisIndex: [0],
        type: 'slider',
        bottom: '5%',
        height: 20,
        start: 0,
        end: 100,
        borderColor: '#00d4ff',
        backgroundColor: '#0f3460',
        dataBackground: {
          lineStyle: {
            color: '#00d4ff'
          },
          areaStyle: {
            color: 'rgba(0, 212, 255, 0.2)'
          }
        }
      }
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: [],
        itemStyle: {
          color: '#ef4444',
          color0: '#22c55e',
          borderColor: '#ef4444',
          borderColor0: '#22c55e'
        }
        // 不使用 encode 属性，让 ECharts 使用默认的数据解析
      }
    ]
  }
  
  console.log('📝 设置K线图表配置...')
  klineChart.setOption(klineOption)
  console.log('✅ K线图表配置设置完成')
  
  // 初始化副指标图表
  indicatorChart = echarts.init(indicatorChartRef.value)
  
  const indicatorOption = {
    backgroundColor: '#16213e',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#00d4ff',
      textStyle: {
        color: '#fff'
      }
    },
    grid: {
      left: '10%',
      right: '5%',
      top: '10%',
      bottom: '5%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: [],
      axisLine: {
        lineStyle: {
          color: '#333'
        }
      },
      axisLabel: {
        show: false
      },
      axisTick: {
        show: false
      }
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: {
        lineStyle: {
          color: '#333'
        }
      },
      axisLabel: {
        color: '#aaa'
      },
      splitLine: {
        lineStyle: {
          color: '#2a2a3e'
        }
      }
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0],
        start: 0,
        end: 100
      }
    ],
    series: [
      {
        name: 'VAR9',
        type: 'bar',
        data: [],
        itemStyle: {
          color: '#22c55e'
        }
      },
      {
        name: 'VAR9L',
        type: 'bar',
        data: [],
        itemStyle: {
          color: '#ef4444'
        }
      }
    ]
  }

  console.log('📝 设置副指标图表配置...')
  indicatorChart.setOption(indicatorOption)
  console.log('✅ 副指标图表配置设置完成')
  
  // 实现主副图表dataZoom联动
  klineChart.on('dataZoom', function() {
    if (isSyncing) return
    
    isSyncing = true
    const option = klineChart.getOption()
    const start = option.dataZoom[0].start
    const end = option.dataZoom[0].end
    
    const indicatorOption = indicatorChart.getOption()
    indicatorOption.dataZoom.forEach(dz => {
      dz.start = start
      dz.end = end
    })
    indicatorChart.setOption(indicatorOption)
    
    setTimeout(() => {
      isSyncing = false
    }, 100)
  })
  
  indicatorChart.on('dataZoom', function() {
    if (isSyncing) return
    
    isSyncing = true
    const option = indicatorChart.getOption()
    const start = option.dataZoom[0].start
    const end = option.dataZoom[0].end
    
    const mainOption = klineChart.getOption()
    mainOption.dataZoom.forEach(dz => {
      dz.start = start
      dz.end = end
    })
    klineChart.setOption(mainOption)
    
    setTimeout(() => {
      isSyncing = false
    }, 100)
  })
  
  // 响应窗口大小变化
  window.addEventListener('resize', handleResizeDebounced)
}

// 加载K线数据
async function loadKlineData() {
  loading.value = true
  
  console.log('🔍 [Backtest] 开始加载K线数据...')
  console.log('📋 请求参数:', {
    symbol: params.symbol,
    period: params.period,
    days: params.days
  })
  
  try {
    const result = await getKlineData({
      symbol: params.symbol,
      period: params.period,
      days: params.days
    })
    
    console.log('📦 API返回结果:', result)
    
    if (result.success && result.data) {
      console.log('✅ 数据加载成功！')
      console.log('📊 数据条数:', result.count || result.data.length)
      console.log('📈 第一条数据:', result.data[0])
      console.log('📉 最后一条数据:', result.data[result.data.length - 1])
      console.log('🔍 数据结构示例:', {
        time: result.data[0]?.time,
        open: result.data[0]?.open,
        high: result.data[0]?.high,
        low: result.data[0]?.low,
        close: result.data[0]?.close
      })
      
      updateCharts(result.data)
      ElMessage.success(`数据加载成功！共 ${result.count || result.data.length} 条数据`)
    } else {
      console.error('❌ 数据加载失败:', result.message)
      ElMessage.error(result.message || '数据加载失败')
    }
  } catch (error) {
    console.error('❌ 加载数据异常:', error)
    console.error('错误堆栈:', error.stack)
    ElMessage.error('加载失败: ' + (error.message || '网络请求失败'))
  } finally {
    loading.value = false
  }
}

// 更新图表
function updateCharts(data) {
  console.log('🔄 [updateCharts] 开始更新图表...')
  console.log('📊 传入数据条数:', data.length)
  
  currentKlineData.value = data
  
  const categoryData = []
  const klineData = []
  
  data.forEach(item => {
    categoryData.push(item.time)
    const kline = [item.open, item.close, item.high, item.low]
    klineData.push(kline)
  })
  
  console.log('📈 处理后的类别数据 (前5个):', categoryData.slice(0, 5))
  console.log('📊 处理后的K线数据 (前5个):', klineData.slice(0, 5))
  console.log('📉 处理后的K线数据 (后5个):', klineData.slice(-5))
  
  updateTime.value = new Date().toLocaleString('zh-CN')
  
  // 更新K线图表
  const option = klineChart.getOption()
  console.log('🔧 更新前 xAxis[0].data 长度:', option.xAxis[0].data.length)
  console.log('🔧 更新前 series[0].data 长度:', option.series[0].data.length)
  
  option.xAxis[0].data = categoryData
  option.series[0].data = klineData
  
  console.log('✅ 更新后 xAxis[0].data 长度:', option.xAxis[0].data.length)
  console.log('✅ 更新后 series[0].data 长度:', option.series[0].data.length)
  
  klineChart.setOption(option)
  console.log('✨ K线图表更新完成')
  
  // 计算并更新副指标
  const indicator = calculateIndicator(data)
  currentIndicatorData.value = indicator
  updateIndicatorChart(categoryData, indicator)
}

// 技术指标计算辅助函数
function SMA(data, period, weight) {
  const result = []
  const M = weight ?? 1
  const N = period
  let prevSma = null

  for (let i = 0; i < data.length; i++) {
    const val = data[i]
    if (isNaN(val) || val === null || val === undefined) {
      result.push(NaN)
      prevSma = null
      continue
    }
    if (prevSma === null) {
      prevSma = val
    } else {
      prevSma = (M * val + (N - M) * prevSma) / N
    }
    result.push(prevSma)
  }
  return result
}

function EMA(data, period) {
  const result = []
  const multiplier = 2 / (period + 1)
  
  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      result.push(data[0])
    } else {
      result.push((data[i] - result[i - 1]) * multiplier + result[i - 1])
    }
  }
  return result
}

function REF(data, n) {
  const result = []
  for (let i = 0; i < data.length; i++) {
    if (i < n) {
      result.push(data[i])
    } else {
      result.push(data[i - n])
    }
  }
  return result
}

function HHV(data, period) {
  const result = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(data[i])
    } else {
      let max = data[i]
      for (let j = 1; j < period; j++) {
        max = Math.max(max, data[i - j])
      }
      result.push(max)
    }
  }
  return result
}

function LLV(data, period) {
  const result = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(data[i])
    } else {
      let min = data[i]
      for (let j = 1; j < period; j++) {
        min = Math.min(min, data[i - j])
      }
      result.push(min)
    }
  }
  return result
}

function ABS(data) {
  return data.map(v => Math.abs(v))
}

function MAX(data1, data2) {
  return data1.map((v, i) => Math.max(v, data2[i] || 0))
}

function MA(data, period) {
  const result = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(data[i])
    } else {
      let sum = 0
      for (let j = 0; j < period; j++) {
        sum += data[i - j]
      }
      result.push(sum / period)
    }
  }
  return result
}

// 计算同花顺指标
function calculateIndicator(data) {
  const high = data.map(d => d.high)
  const low = data.map(d => d.low)
  const close = data.map(d => d.close)
  
  const VAR2 = REF(high, 1)
  const VAR3_temp1 = SMA(ABS(high.map((h, i) => h - VAR2[i])), 3, 1)
  const VAR3_temp2 = SMA(MAX(VAR2.map((v, i) => v - high[i]), 0), 3, 1)
  const VAR3 = VAR3_temp1.map((v, i) => VAR3_temp2[i] !== 0 ? (v / VAR3_temp2[i]) * 100 : 0)
  
  const closeRef = REF(close, 1)
  const VAR4_base = close.map((c, i) => {
    const ratio = i > 0 ? c / closeRef[i] : 1
    return ratio < 0.7 ? VAR3[i] * 10 : VAR3[i] / 10
  })
  const VAR4 = EMA(VAR4_base, 3)
  
  const VAR5 = HHV(high, 50)
  const VAR6 = LLV(VAR4, 50)
  const ma58 = MA(close, 58)
  const VAR7 = ma58.map(v => v > 0 ? 1 : 0)
  
  const VAR8_base = high.map((h, i) => {
    if (h >= VAR5[i]) {
      return (VAR4[i] + VAR6[i] * 2) / 2
    }
    return 0
  })
  const VAR8 = EMA(VAR8_base, 3).map((v, i) => v / 1000 * VAR7[i])
  const VAR9_raw = VAR8.map(v => v > 100 ? 100 : v)
  
  const VAR2L = REF(low, 1)
  const VAR3L_temp1 = SMA(ABS(low.map((l, i) => l - VAR2L[i])), 3, 1)
  const VAR3L_temp2 = SMA(MAX(low.map((l, i) => l - VAR2L[i]), 0), 3, 1)
  const VAR3L = VAR3L_temp1.map((v, i) => VAR3L_temp2[i] !== 0 ? (v / VAR3L_temp2[i]) * 100 : 0)
  
  const VAR4L_base = close.map((c, i) => {
    const ratio = i > 0 ? c / closeRef[i] : 1
    return ratio > 1.3 ? VAR3L[i] * 10 : VAR3L[i] / 10
  })
  const VAR4L = EMA(VAR4L_base, 3)
  
  const VAR5L = LLV(low, 50)
  const VAR6L = HHV(VAR4L, 50)
  const ma58L = MA(close, 58)
  const VAR7L = ma58L.map(v => v > 0 ? 1 : 0)
  
  const VAR8L_base = low.map((l, i) => {
    if (l <= VAR5L[i]) {
      return (VAR4L[i] + VAR6L[i] * 2) / 2
    }
    return 0
  })
  const VAR8L = EMA(VAR8L_base, 3).map((v, i) => v / 1000 * VAR7L[i])
  const VAR9L_raw = VAR8L.map(v => v > 100 ? 100 : v)
  
  const VAR9 = VAR9_raw.map(v => v > -120 ? v : 0)
  const VAR9L = VAR9L_raw.map(v => v > -120 ? v : 0)
  
  return { VAR9, VAR9L }
}

// 更新副指标图表
function updateIndicatorChart(categoryData, indicator) {
  const option = indicatorChart.getOption()
  option.xAxis[0].data = categoryData
  
  option.series[0].data = indicator.VAR9.map(v => {
    if (v > -120) {
      return -v
    }
    return 0
  })
  
  option.series[1].data = indicator.VAR9L.map(v => {
    if (v > -120) {
      return v
    }
    return 0
  })
  
  indicatorChart.setOption(option)
}

// 检查交易时间
function checkTradeTime(timeStr) {
  const timePart = timeStr.split(' ')[1]
  if (!timePart) return false
  
  const [hours, minutes] = timePart.split(':').map(Number)
  
  if (hours === 9 && minutes >= 0 && minutes <= 15) {
    return true
  }
  
  if (hours === 21 && minutes >= 0 && minutes <= 15) {
    return true
  }
  
  return false
}

// 运行回测
function runBacktest() {
  if (!currentKlineData.value || !currentIndicatorData.value) {
    ElMessage.error('请先加载K线数据！')
    return
  }
  
  if (params.period !== '5') {
    ElMessage.error('回测仅支持5分钟K线，请切换周期后再试！')
    return
  }
  
  backtesting.value = true
  
  setTimeout(() => {
    try {
      const result = executeBacktest()
      backtestResult.value = result
      updateKlineMarkPoints(result.markPoints)
      ElMessage.success('回测完成！')
    } catch (error) {
      console.error('回测执行出错:', error)
      ElMessage.error('回测执行出错：' + error.message)
    } finally {
      backtesting.value = false
    }
  }, 100)
}

// 执行回测逻辑
function executeBacktest() {
  const klineData = currentKlineData.value
  const indicator = currentIndicatorData.value
  const symbol = params.symbol
  
  let capital = 10000
  const initialCapital = 10000
  
  let trades = []
  let currentPosition = null
  let dailyTradeRecord = {}
  
  const config = getInstrumentConfig(symbol)
  const tickSize = config.tickSize
  const multiplier = config.multiplier
  const tickValue = tickSize * multiplier
  
  const lots = TRADE_LOTS
  const jumpValue = tickSize * 10
  
  let markPoints = []
  
  for (let i = 0; i < klineData.length; i++) {
    const kline = klineData[i]
    const time = kline.time
    const open = kline.open
    const high = kline.high
    const low = kline.low
    const close = kline.close
    
    const var9 = indicator.VAR9[i]
    const var9L = indicator.VAR9L[i]
    
    if (currentPosition) {
      let isClosed = false
      let exitPrice = 0
      let exitReason = ''
      
      if (currentPosition.type === 'long') {
        if (low <= currentPosition.stopLoss) {
          isClosed = true
          exitPrice = currentPosition.stopLoss
          exitReason = '止损'
        } else if (high >= currentPosition.stopProfit) {
          isClosed = true
          exitPrice = currentPosition.stopProfit
          exitReason = '止盈'
        }
      } else if (currentPosition.type === 'short') {
        if (low <= currentPosition.stopProfit) {
          isClosed = true
          exitPrice = currentPosition.stopProfit
          exitReason = '止盈'
        } else if (high >= currentPosition.stopLoss) {
          isClosed = true
          exitPrice = currentPosition.stopLoss
          exitReason = '止损'
        }
      }
      
      if (isClosed) {
        const priceDiff = currentPosition.type === 'long'
          ? (exitPrice - currentPosition.entryPrice)
          : (currentPosition.entryPrice - exitPrice)
        
        const ticks = priceDiff / tickSize
        const profit = ticks * tickValue * lots
        
        capital += profit
        
        trades.push({
          entryTime: currentPosition.entryTime,
          exitTime: time,
          type: currentPosition.type,
          entryPrice: currentPosition.entryPrice,
          exitPrice: exitPrice,
          reason: exitReason,
          profit: profit,
          capital: capital
        })
        
        if (currentPosition.type === 'long') {
          markPoints.push({
            name: '卖',
            coord: [time, exitPrice],
            value: '卖',
            itemStyle: { color: '#ef4444' }
          })
        } else {
          markPoints.push({
            name: '平',
            coord: [time, exitPrice],
            value: '平',
            itemStyle: { color: '#22c55e' }
          })
        }
        
        currentPosition = null
      }
    }
    
    if (!currentPosition) {
      const isTradeTime = checkTradeTime(time)
      const dateStr = time.split(' ')[0]
      const timePart = time.split(' ')[1]
      const [hours, minutes] = timePart.split(':').map(Number)
      
      let sessionKey = null
      if (hours === 9 && minutes >= 0 && minutes <= 15) {
        sessionKey = 'morning'
      } else if (hours === 21 && minutes >= 0 && minutes <= 15) {
        sessionKey = 'night'
      }
      
      let canTradeInSession = false
      if (isTradeTime && sessionKey) {
        if (!dailyTradeRecord[dateStr]) {
          dailyTradeRecord[dateStr] = { morning: false, night: false }
        }
        
        if (!dailyTradeRecord[dateStr][sessionKey]) {
          canTradeInSession = true
        }
      }
      
      const hasGreenBar = var9 < -0.1 && var9 !== null && !isNaN(var9)
      const hasRedBar = var9L > 0.1 && var9L !== null && !isNaN(var9L)
      
      if (hasGreenBar && hasRedBar) {
        // 跳过
      } else if (hasRedBar && canTradeInSession) {
        currentPosition = {
          type: 'long',
          entryPrice: close,
          entryTime: time,
          stopProfit: close + jumpValue,
          stopLoss: close - jumpValue
        }
        
        dailyTradeRecord[dateStr][sessionKey] = true
        
        markPoints.push({
          name: '买',
          coord: [time, close],
          value: '买',
          itemStyle: { color: '#ef4444' }
        })
      } else if (hasGreenBar && canTradeInSession) {
        currentPosition = {
          type: 'short',
          entryPrice: close,
          entryTime: time,
          stopProfit: close - jumpValue,
          stopLoss: close + jumpValue
        }
        
        dailyTradeRecord[dateStr][sessionKey] = true
        
        markPoints.push({
          name: '卖',
          coord: [time, close],
          value: '卖',
          itemStyle: { color: '#22c55e' }
        })
      }
    }
  }
  
  if (currentPosition) {
    const lastKline = klineData[klineData.length - 1]
    const exitPrice = lastKline.close
    
    const priceDiff = currentPosition.type === 'long'
      ? (exitPrice - currentPosition.entryPrice)
      : (currentPosition.entryPrice - exitPrice)
    
    const ticks = priceDiff / tickSize
    const profit = ticks * tickValue * lots
    
    capital += profit
    
    trades.push({
      entryTime: currentPosition.entryTime,
      exitTime: lastKline.time,
      type: currentPosition.type,
      entryPrice: currentPosition.entryPrice,
      exitPrice: exitPrice,
      reason: '强制平仓',
      profit: profit,
      capital: capital
    })
    
    if (currentPosition.type === 'long') {
      markPoints.push({
        name: '卖',
        coord: [lastKline.time, exitPrice],
        value: '卖',
        itemStyle: { color: '#ef4444' }
      })
    } else {
      markPoints.push({
        name: '平',
        coord: [lastKline.time, exitPrice],
        value: '平',
        itemStyle: { color: '#22c55e' }
      })
    }
  }
  
  const openCount = trades.length
  const winCount = trades.filter(t => t.profit > 0).length
  const winRate = openCount > 0 ? (winCount / openCount * 100) : 0
  const totalProfit = capital - initialCapital
  
  const startTime = klineData[0].time
  const endTime = klineData[klineData.length - 1].time
  const startDate = startTime.split(' ')[0].replace(/-/g, '/')
  const endDate = endTime.split(' ')[0].replace(/-/g, '/')
  const timeSpan = `${startDate} ~ ${endDate}`
  
  return {
    openCount,
    winCount,
    winRate,
    totalProfit,
    timeSpan,
    trades,
    markPoints
  }
}

// 更新K线图标记点
function updateKlineMarkPoints(markPoints) {
  if (markPoints.length === 0) {
    ElMessage.warning('本次回测没有产生任何交易信号')
    return
  }
  
  const option = klineChart.getOption()
  
  option.series[0].markPoint = {
    symbol: 'pin',
    symbolSize: 50,
    itemStyle: {
      borderWidth: 2,
      borderColor: '#fff'
    },
    label: {
      show: true,
      formatter: '{b}',
      color: '#fff',
      fontSize: 12,
      fontWeight: 'bold'
    },
    data: markPoints.map(point => ({
      name: point.value,
      coord: point.coord,
      value: point.value,
      itemStyle: {
        color: point.itemStyle.color,
        borderColor: '#fff',
        borderWidth: 2
      }
    }))
  }
  
  klineChart.setOption(option)
}

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

// 生命周期
let isComponentMounted = true // 跟踪组件挂载状态

onMounted(() => {
  // 使用 nextTick 确保 DOM 完全渲染
  setTimeout(() => {
    initCharts()
    
    // 再延迟一点确保图表容器有正确的高度
    setTimeout(() => {
      if (isComponentMounted) {
        loadKlineData()
        // 初始化后执行一次 resize
        if (klineChart) klineChart.resize()
        if (indicatorChart) indicatorChart.resize()
      }
    }, 100)
  }, 50)
})

onUnmounted(() => {
  isComponentMounted = false
  
  // 清理 resize 定时器
  if (resizeTimer) {
    clearTimeout(resizeTimer)
    resizeTimer = null
  }
  
  // 移除 resize 监听 - 使用防抖函数而非 handleResize
  window.removeEventListener('resize', handleResizeDebounced)
  
  //  dispose 图表实例
  if (klineChart) {
    klineChart.dispose()
    klineChart = null
  }
  if (indicatorChart) {
    indicatorChart.dispose()
    indicatorChart = null
  }
})
</script>

<style scoped>
@import '@/styles/Backtest.css';
</style>
