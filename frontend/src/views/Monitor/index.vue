<template>
  <div class="monitor-container">
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
        <UserMenu />
      </div>
    </nav>

    <div class="main-container">
      <!-- 左侧：账号与跟单配置 -->
      <aside class="sidebar">
        <!-- 步骤 1：被监控账号 -->
        <section class="control-panel">
          <h3>监控账号</h3>

          <template v-if="!monitorOn">
            <el-form class="inline-label-form" label-position="left" label-width="72px" size="small"
                     @submit.prevent>
              <el-form-item label="期货公司">
                <el-select v-model="form.broker" placeholder="请选择期货公司" filterable style="width: 100%"
                           popper-class="monitor-broker-popper" :fit-input-width="true" :offset="7">
                  <el-option v-for="b in brokerOptions" :key="b.value" :label="b.name" :value="b.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="账号">
                <el-input v-model="form.username" placeholder="被监控的交易账号" autocomplete="off" />
              </el-form-item>
              <el-form-item label="密码">
                <el-input v-model="form.password" type="password" show-password placeholder="交易密码"
                          autocomplete="new-password" @keyup.enter="handleMonitorLogin" />
              </el-form-item>
              <el-form-item class="remember-row">
                <el-checkbox v-model="rememberAccount">记住账号密码</el-checkbox>
              </el-form-item>
              <el-button type="primary" :loading="loggingIn" style="width: 100%" @click="handleMonitorLogin">
                登录并开始监控
              </el-button>
            </el-form>
          </template>

          <template v-else>
            <div class="kv"><span>账号</span><b>{{ account?.username }}</b></div>
            <div class="kv"><span>权益</span><b>{{ money(account?.account?.balance) }}</b></div>
            <div class="kv"><span>可用</span><b>{{ money(account?.account?.available) }}</b></div>
            <div class="kv"><span>持仓</span><b>{{ account?.positions?.length || 0 }} 个</b></div>
            <el-button size="small" style="width: 100%; margin-top: 8px" :disabled="running"
                       @click="handleMonitorLogout">
              断开监控账号
            </el-button>
            <p v-if="running" class="hint">跟单运行中，需先停止跟单才能断开。</p>
          </template>
        </section>

        <!-- 步骤 2：跟单配置 -->
        <section class="control-panel">
          <h3>跟单配置</h3>
          <el-form label-position="top" size="small" @submit.prevent>
            <el-form-item label="手数模式">
              <el-radio-group v-model="cfg.size_mode" :disabled="running" class="size-mode-group">
                <el-radio-button value="multiple">固定倍数</el-radio-button>
                <el-radio-button value="fixed">固定手数</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item v-if="cfg.size_mode !== 'fixed'">
              <template #label>
                <span>倍数</span>
                <el-tooltip :content="preview" placement="top" :show-after="200">
                  <el-icon class="field-help"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-input-number v-model="cfg.multiplier" :min="0.01" :max="100" :step="0.1" :precision="2"
                               controls-position="right" style="width: 100%" />
            </el-form-item>
            <el-form-item v-else>
              <template #label>
                <span>每笔固定手数</span>
                <el-tooltip :content="preview" placement="top" :show-after="200">
                  <el-icon class="field-help"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-input-number v-model="cfg.fixed_volume" :min="1" :max="10000" :step="1" :precision="0"
                               controls-position="right" style="width: 100%" />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span>下单价格</span>
                <el-tooltip content="对手价：买入用卖一价、卖出用买一价；涨跌停价：用涨跌停价模拟市价单"
                            placement="top" :show-after="200">
                  <el-icon class="field-help"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-select v-model="cfg.price_mode" style="width: 100%">
                <el-option label="对手价" value="counter" />
                <el-option label="最新价" value="last" />
                <el-option label="涨跌停价" value="market" />
              </el-select>
            </el-form-item>

            <el-form-item>
              <template #label>
                <span>未成交撤单（秒）</span>
                <el-tooltip content="委托超过该秒数仍未全部成交就自动撤单；0 = 不撤单" placement="top" :show-after="200">
                  <el-icon class="field-help"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-input-number v-model="cfg.order_timeout" :min="0" :max="3600" :step="1" :precision="0"
                               controls-position="right" style="width: 100%" />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span>信号延迟上限（秒）</span>
                <el-tooltip content="对方成交到被处理的延迟超过该秒数，信号直接丢弃不跟单（开仓、平仓都生效）；0 = 不限制"
                            placement="top" :show-after="200">
                  <el-icon class="field-help"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-input-number v-model="cfg.signal_max_delay" :min="0" :max="3600" :step="1" :precision="0"
                               controls-position="right" style="width: 100%" />
            </el-form-item>

            <el-form-item>
              <template #label>
                <span>品种白名单</span>
                <el-tooltip content="只跟随这些品种，多个用逗号分隔，如 rb, ag, cu；留空 = 全部品种"
                            placement="top" :show-after="200">
                  <el-icon class="field-help"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-input v-model="whitelistText" placeholder="rb, ag, cu" />
            </el-form-item>
          </el-form>
        </section>

        <!-- 步骤 3：启动 -->
        <section class="control-panel start-panel">
          <h3>启动</h3>

          <div class="simulate-row">
            <el-tooltip content="模拟模式：只记录本应跟的单，不会真实下单" placement="top" :show-after="200">
              <el-icon class="simulate-help"><QuestionFilled /></el-icon>
            </el-tooltip>
            <span class="simulate-label">模拟模式</span>
            <el-switch v-model="cfg.simulate" :disabled="running" />
          </div>
          <div v-if="!cfg.simulate" class="danger-tip">
            实盘模式：将使用当前交易账号 <b>{{ userStore.username }}</b> 真实下单
          </div>

          <template v-if="!running">
            <el-button type="success" size="large" style="width: 100%"
                       :disabled="!monitorOn" :loading="busy" @click="handleStart">
              启动跟单
            </el-button>
            <p v-if="!monitorOn" class="hint">请先登录被监控账号。</p>
            <p v-else class="hint">只跟随<b>启动之后</b>产生的新成交，不会补齐已有持仓。</p>
          </template>
          <template v-else>
            <el-button v-if="status?.paused_reason" type="warning" size="large" style="width: 100%; margin-top: 10px"
                       :loading="busy" @click="handleResume">
              我已确认，恢复跟单
            </el-button>
            <el-button type="danger" size="large" style="width: 100%; margin-top: 10px"
                       :loading="busy" @click="handleStop">
              停止跟单
            </el-button>
            <el-button size="small" style="width: 100%; margin-top: 8px" :loading="busy" @click="handleUpdate">
              应用修改后的配置（对之后的信号生效）
            </el-button>
          </template>
        </section>
      </aside>

      <!-- 右侧：状态 / 持仓 / 跟单记录 / 日志 -->
      <div class="content">
        <el-alert v-if="status?.paused_reason" type="error" :closable="false" show-icon class="alert"
                  :title="`跟单已自动暂停：${status.paused_reason}`"
                  description="暂停期间的成交不会补跟。请核对两个账号的持仓后，点击左侧「恢复跟单」。" />
        <el-alert v-else-if="running && status?.config?.simulate" type="info" :closable="false" show-icon class="alert"
                  title="模拟模式运行中：只记录本应下的单，不会真实下单" />

        <!-- 概览 -->
        <div class="stats">
          <div class="stat">
            <div class="stat-label">被监控账号权益</div>
            <div class="stat-value">{{ money(status?.src_balance) }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">我的权益</div>
            <div class="stat-value">{{ money(status?.my_balance) }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">本次跟单次数</div>
            <div class="stat-value">{{ status?.follow_count || 0 }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">运行 / 连接状态</div>
            <div class="stat-value small">
              <span :class="['run-text', runClass]">{{ runText }}</span>
              <span :class="['dot', status?.monitor_connected ? 'ok' : 'bad']"></span>监控
              <span :class="['dot', status?.trade_connected ? 'ok' : 'bad']" style="margin-left: 10px"></span>交易
            </div>
          </div>
        </div>

        <!-- 被监控账号持仓 -->
        <section class="card">
          <div class="card-head">被监控账号当前持仓</div>
          <el-table :data="account?.positions || []" size="small" empty-text="暂无持仓" max-height="200">
            <el-table-column prop="symbol" label="合约" min-width="90" />
            <el-table-column label="方向" width="70">
              <template #default="{ row }">
                <span :class="row.direction === '多' ? 'up' : 'down'">{{ row.direction }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="volume" label="手数" width="70" />
            <el-table-column label="开仓均价" width="100">
              <template #default="{ row }">{{ num(row.price) }}</template>
            </el-table-column>
            <el-table-column label="持仓盈亏" width="110">
              <template #default="{ row }">
                <span :class="row.pnl >= 0 ? 'up' : 'down'">{{ num(row.pnl) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </section>

        <!-- 跟单记录 -->
        <section class="card">
          <div class="card-head">跟单记录</div>
          <el-table :data="records" size="small" empty-text="暂无跟单记录" max-height="320">
            <el-table-column prop="time" label="时间" width="80" />
            <el-table-column prop="symbol" label="合约" width="90" />
            <el-table-column label="对方操作" width="130">
              <template #default="{ row }">{{ row.src_action }} {{ row.src_volume }}手 @{{ row.src_price }}</template>
            </el-table-column>
            <el-table-column label="我的操作" width="150">
              <template #default="{ row }">
                <template v-if="row.action">{{ actionText[row.action] }} {{ row.volume }}手<template v-if="row.price"> @{{ row.price }}</template></template>
                <template v-else>-</template>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="说明" min-width="260" show-overflow-tooltip />
          </el-table>
        </section>

        <!-- 运行日志 -->
        <section class="card">
          <div class="card-head">运行日志</div>
          <div class="logs">
            <div v-if="!logs.length" class="empty">暂无日志</div>
            <div v-for="(l, i) in logs" :key="i" :class="['log-line', l.level]">
              <span class="log-time">{{ l.time }}</span>{{ l.msg }}
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getBrokers } from '@/api'
import {
  monitorLogin, monitorLogout, getMonitorAccount, getMonitorStatus, getMonitorRecords,
  getMonitorCredentials, startCopy, stopCopy, updateCopyConfig, resumeCopy
} from '@/api/monitor'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const actionText = {
  open_long: '买多开仓', open_short: '卖空开仓', close_long: '卖出平多', close_short: '买入平空'
}

// ---- 被监控账号 ----
const brokerGroups = ref([])
// 监控目前只支持中信建投期货和 SimNow 账号（value 与 data/brokers.json 一致），其余期货公司暂不开放
const MONITOR_BROKERS = ['citic', 'simnow', 'simnow_724']
const brokerOptions = computed(() =>
  brokerGroups.value.flatMap(g => g.items).filter(b => MONITOR_BROKERS.includes(b.value))
)
const form = reactive({ broker: '', username: '', password: '' })
const rememberAccount = ref(true)   // 记住账号密码：登录成功后由后端保存（勾选）或清除（未勾选）
const loggingIn = ref(false)
const account = ref(null)
const monitorOn = computed(() => !!status.value?.monitor_connected)

// ---- 跟单配置（默认值与后端 DEFAULT_CONFIG 一致；默认模拟模式）----
const cfg = reactive({
  size_mode: 'multiple', multiplier: 1, fixed_volume: 1, price_mode: 'counter', order_timeout: 5,
  simulate: true, signal_max_delay: 3
})
const whitelistText = ref('')

const buildConfig = () => ({ ...cfg, symbol_whitelist: whitelistText.value })

// ---- 运行状态 ----
const status = ref(null)
const records = ref([])
const logs = ref([])
const busy = ref(false)
const running = computed(() => !!status.value?.running)

const runText = computed(() => {
  if (!running.value) return '未运行'
  if (status.value?.paused_reason) return '已暂停'
  return status.value?.config?.simulate ? '模拟运行中' : '实盘运行中'
})
const runClass = computed(() => {
  if (!running.value) return 'off'
  if (status.value?.paused_reason) return 'paused'
  return status.value?.config?.simulate ? 'sim' : 'live'
})

// 手数预览：按当前配置举例（对方开 1 / 5 / 10 手）
const preview = computed(() => {
  if (cfg.size_mode === 'fixed') return `对方每成交一笔，你固定跟 ${cfg.fixed_volume} 手`
  const f = (n) => Math.floor(n * cfg.multiplier + 1e-9)
  return `预览：对方 1 手 → 你 ${f(1)} 手；5 手 → ${f(5)} 手；10 手 → ${f(10)} 手（向下取整，余量累计到下一笔）`
})

const money = (v) => (v === null || v === undefined ? '-' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 }))
const num = (v) => (v === null || v === undefined ? '-' : Number(v).toFixed(2))

const statusType = (s) => ({
  已成交: 'success', 部分成交: 'warning', 已委托: 'primary', 已撤单: 'info',
  已拒绝: 'danger', 失败: 'danger', 已跳过: 'info', 模拟: ''
}[s] || 'info')

// ---- 轮询 ----
let timer = null
let polling = false
const refresh = async () => {
  if (polling) return
  polling = true
  try {
    const [st, rc] = await Promise.all([getMonitorStatus(), getMonitorRecords()])
    if (st?.success) status.value = st.data
    if (rc?.success) {
      records.value = rc.data.records
      logs.value = rc.data.logs
    }
    if (status.value?.monitor_connected) {
      const acc = await getMonitorAccount()
      account.value = acc?.success ? acc.data : account.value
    } else {
      account.value = null
    }
  } catch (e) {
    // 后端暂时不可达：保留上一次数据，下个周期重试
  } finally {
    polling = false
  }
}

// 页面（重新）打开时，把后端已有的配置同步回表单，避免显示与实际运行不一致
const syncConfigFromStatus = () => {
  const c = status.value?.config
  if (!c) return
  Object.keys(cfg).forEach(k => { if (k in c) cfg[k] = c[k] })
  whitelistText.value = (c.symbol_whitelist || []).join(', ')
}

// 用「记住账号密码」保存的被监控账号预填表单。保存的期货公司已不在监控支持的列表里时不预填该项
const prefillSavedAccount = async () => {
  try {
    const saved = await getMonitorCredentials()
    if (!saved?.saved) return   // 没有保存过：保持默认勾选
    if (brokerOptions.value.some(b => b.value === saved.broker)) form.broker = saved.broker
    form.username = saved.username
    form.password = saved.password || ''
  } catch (e) {
    // 读取失败不影响手动登录
  }
}

onMounted(async () => {
  try {
    const data = await getBrokers()
    brokerGroups.value = data
  } catch (e) {
    ElMessage.error('期货公司列表加载失败')
  }
  await prefillSavedAccount()
  await refresh()
  if (running.value) syncConfigFromStatus()
  timer = setInterval(refresh, 2000)
})
onBeforeUnmount(() => timer && clearInterval(timer))

// ---- 操作 ----
const handleMonitorLogin = async () => {
  if (!form.broker) return ElMessage.warning('请选择期货公司')
  if (!form.username || !form.password) return ElMessage.warning('请输入被监控账号和密码')
  loggingIn.value = true
  try {
    const res = await monitorLogin({ ...form, remember: rememberAccount.value })
    if (res.success) {
      ElMessage.success('被监控账号登录成功')
      if (rememberAccount.value && !res.password_saved) {
        ElMessage.warning('已记住账号，但当前系统不支持安全保存密码，下次需重新输入密码')
      }
      form.password = ''
      await refresh()
    } else {
      ElMessage.error(res.message || '登录失败')
    }
  } catch (e) {
    ElMessage.error('登录请求失败，请检查后端是否运行')
  } finally {
    loggingIn.value = false
  }
}

const handleMonitorLogout = async () => {
  await monitorLogout()
  account.value = null
  await refresh()
}

const handleStart = async () => {
  const live = !cfg.simulate
  const summary = `手数：${{ multiple: '固定倍数', fixed: '固定手数' }[cfg.size_mode]}，`
    + `价格：${{ counter: '对手价', last: '最新价', market: '涨跌停价' }[cfg.price_mode]}`
  try {
    if (live) {
      await ElMessageBox.confirm(
        `即将【实盘】跟单：对方账号 ${account.value?.username} 的新成交，会立即用你的交易账号 ${userStore.username} 真实下单。\n\n${summary}\n\n确认启动？`,
        '实盘跟单确认', { type: 'warning', confirmButtonText: '确认实盘跟单', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' })
    } else {
      await ElMessageBox.confirm(`以【模拟模式】启动：只记录本应下的单，不会真实下单。\n\n${summary}`,
        '启动跟单', { type: 'info', confirmButtonText: '启动', cancelButtonText: '取消' })
    }
  } catch { return }

  busy.value = true
  try {
    const res = await startCopy(buildConfig())
    res.success ? ElMessage.success(res.message) : ElMessage.error(res.message)
    await refresh()
  } catch (e) {
    ElMessage.error('启动请求失败')
  } finally {
    busy.value = false
  }
}

const handleStop = async () => {
  busy.value = true
  try {
    await stopCopy()
    ElMessage.success('跟单已停止')
    await refresh()
  } finally {
    busy.value = false
  }
}

const handleResume = async () => {
  try {
    await ElMessageBox.confirm('请确认已核对两个账号的持仓。暂停期间对方的成交不会补跟。', '恢复跟单',
      { type: 'warning', confirmButtonText: '确认恢复', cancelButtonText: '取消' })
  } catch { return }
  busy.value = true
  try {
    const res = await resumeCopy()
    res.success ? ElMessage.success(res.message) : ElMessage.error(res.message)
    await refresh()
  } finally {
    busy.value = false
  }
}

const handleUpdate = async () => {
  busy.value = true
  try {
    const res = await updateCopyConfig(buildConfig())
    res.success ? ElMessage.success(res.message) : ElMessage.error(res.message)
    await refresh()
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
@import '@/styles/Monitor.css';
</style>

<!-- 下拉面板通过 teleport 挂到 body 下，scoped / :deep 命中不了，需以非 scoped 方式引入 -->
<style>
@import '@/styles/MonitorPopper.css';
</style>
