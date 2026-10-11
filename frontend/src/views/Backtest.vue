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

// 初始化图表
function initCharts() {
  // 初始化主K线图表
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
        start: 70,
        end: 100
      },
      {
        show: true,
        xAxisIndex: [0],
        type: 'slider',
        bottom: '5%',
        height: 20,
        start: 70,
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
        },
        encode: {
          x: 0,
          y: [1, 2, 3, 4]
        }
      }
    ]
  }
  
  klineChart.setOption(klineOption)
  
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
        start: 70,
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
  
  indicatorChart.setOption(indicatorOption)
  
  // 实现主副图表dataZoom联动
  klineChart.on('dataZoom', function() {
    const option = klineChart.getOption()
    const start = option.dataZoom[0].start
    const end = option.dataZoom[0].end
    
    const indicatorOption = indicatorChart.getOption()
    indicatorOption.dataZoom[0].start = start
    indicatorOption.dataZoom[0].end = end
    indicatorChart.setOption(indicatorOption)
  })
  
  indicatorChart.on('dataZoom', function() {
    const option = indicatorChart.getOption()
    const start = option.dataZoom[0].start
    const end = option.dataZoom[0].end
    
    const mainOption = klineChart.getOption()
    mainOption.dataZoom[0].start = start
    mainOption.dataZoom[0].end = end
    klineChart.setOption(mainOption)
  })
  
  // 响应窗口大小变化
  window.addEventListener('resize', handleResize)
}

function handleResize() {
  if (klineChart) klineChart.resize()
  if (indicatorChart) indicatorChart.resize()
}

// 加载K线数据
async function loadKlineData() {
  loading.value = true
  
  try {
    const result = await getKlineData({
      symbol: params.symbol,
      period: params.period,
      days: params.days
    })
    
    if (result.success && result.data) {
      updateCharts(result.data)
      ElMessage.success(`数据加载成功！共 ${result.count || result.data.length} 条数据`)
    } else {
      ElMessage.error(result.message || '数据加载失败')
    }
  } catch (error) {
    console.error('加载数据失败:', error)
    ElMessage.error('加载失败: ' + (error.message || '网络请求失败'))
  } finally {
    loading.value = false
  }
}

// 更新图表
function updateCharts(data) {
  currentKlineData.value = data
  
  const categoryData = []
  const klineData = []
  
  data.forEach(item => {
    categoryData.push(item.time)
    const kline = [item.open, item.close, item.high, item.low]
    klineData.push(kline)
  })
  
  updateTime.value = new Date().toLocaleString('zh-CN')
  
  // 更新K线图表
  const option = klineChart.getOption()
  option.xAxis[0].data = categoryData
  option.series[0].data = klineData
  klineChart.setOption(option)
  
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
onMounted(() => {
  initCharts()
  loadKlineData()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (klineChart) klineChart.dispose()
  if (indicatorChart) indicatorChart.dispose()
})
</script>

<style scoped>
.backtest-container {
  min-height: 100vh;
  background: #1a1a2e;
}

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

.username {
  color: #94a3b8;
}

.main-container {
  display: flex;
  height: calc(100vh - 56px);
}

.sidebar {
  width: 300px;
  background: #16213e;
  padding: 20px;
  overflow-y: auto;
  border-right: 1px solid #0f3460;
}

.control-panel {
  background: #0f3460;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 20px;
}

.control-panel h3 {
  color: #00d4ff;
  margin-bottom: 15px;
  font-size: 16px;
}

.chart-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 20px;
  background: #1a1a2e;
  min-height: 0;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  flex-shrink: 0;
}

.chart-header h2 {
  color: #00d4ff;
  font-size: 20px;
}

.data-info {
  display: flex;
  gap: 30px;
  font-size: 14px;
}

.info-item {
  display: flex;
  gap: 5px;
}

.info-label {
  color: #888;
}

.info-value {
  color: #00d4ff;
  font-weight: bold;
}

.kline-chart {
  flex: 3;
  background: #16213e;
  border-radius: 10px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
  min-height: 300px;
}

.indicator-chart {
  flex: 1;
  background: #16213e;
  border-radius: 10px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
  margin-top: 10px;
  min-height: 150px;
}

.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.9);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.loading-spinner {
  border: 4px solid #333;
  border-top: 4px solid #00d4ff;
  border-radius: 50%;
  width: 60px;
  height: 60px;
  animation: spin 1s linear infinite;
  margin: 0 auto 20px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-text {
  color: #00d4ff;
  font-size: 18px;
  font-weight: bold;
  text-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
}

.backtest-result {
  background: #0f3460;
  border-radius: 10px;
  padding: 15px;
  margin-top: 20px;
}

.backtest-result h4 {
  color: #00d4ff;
  margin-bottom: 15px;
  font-size: 14px;
}

.result-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.result-item {
  background: #16213e;
  padding: 12px;
  border-radius: 5px;
  text-align: center;
}

.result-label {
  color: #888;
  font-size: 12px;
  margin-bottom: 5px;
}

.result-value {
  color: #00d4ff;
  font-size: 18px;
  font-weight: bold;
}

.result-value.positive {
  color: #ef4444;
}

.result-value.negative {
  color: #22c55e;
}

.result-value.neutral {
  color: #ffffff;
}

.result-value.time-span {
  font-size: 13px;
  color: #999;
  font-weight: normal;
}

.trade-records {
  max-height: 400px;
  overflow-y: auto;
}

.trade-list {
  margin-top: 10px;
}

.trade-item {
  background: #16213e;
  padding: 10px;
  margin-bottom: 8px;
  border-radius: 5px;
  border-left: 3px solid;
}

.trade-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
}

.trade-type {
  font-weight: bold;
}

.trade-profit {
  font-weight: bold;
}

.trade-details {
  font-size: 11px;
  color: #888;
  line-height: 1.6;
}

:deep(.el-button--danger.is-plain) {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: #f87171;
}

:deep(.el-button--danger.is-plain:hover) {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.5);
}

:deep(.el-form-item__label) {
  color: #aaa;
  font-size: 13px;
}

:deep(.el-select) {
  width: 100%;
}
</style>
