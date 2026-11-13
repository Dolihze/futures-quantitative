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

          <!-- 登录后：行高、行距与登录前的表单一致，面板高度不随登录状态变化 -->
          <div v-else class="account-info">
            <div class="kv"><span>账号</span><b>{{ account?.username }}</b></div>
            <div class="kv"><span>权益</span><b>{{ money(account?.account?.balance) }}</b></div>
            <div class="kv"><span>可用</span><b>{{ money(account?.account?.available) }}</b></div>
            <div class="kv"><span>持仓</span><b>{{ account?.positions?.length || 0 }} 个</b></div>
            <el-button size="small" style="width: 100%" :disabled="running"
                       @click="handleMonitorLogout">
              断开监控账号
            </el-button>
          </div>
        </section>

        <!-- 步骤 2：跟单配置 -->
        <section class="control-panel copy-config-panel">
          <h3>跟单配置</h3>
          <el-form label-position="top" size="small" @submit.prevent>
            <el-form-item label="手数模式" class="inline-field">
              <el-select v-model="cfg.size_mode" :disabled="running">
                <el-option label="固定倍数" value="multiple" />
                <el-option label="固定手数" value="fixed" />
              </el-select>
            </el-form-item>

            <el-form-item v-if="cfg.size_mode !== 'fixed'" label="倍数" class="inline-field">
              <el-input-number v-model="cfg.multiplier" :min="0.01" :max="100" :step="0.1" :precision="2"
                               controls-position="right" align="left" />
            </el-form-item>
            <el-form-item v-else label="每笔固定手数" class="inline-field">
              <el-input-number v-model="cfg.fixed_volume" :min="1" :max="10000" :step="1" :precision="0"
                               controls-position="right" align="left" />
            </el-form-item>

            <el-form-item label="开仓偏移（跳）" class="inline-field">
              <el-input-number v-model="cfg.price_offset_ticks" :min="0" :max="100" :step="1" :precision="0"
                               controls-position="right" align="left" />
            </el-form-item>

            <el-form-item label="开仓时限（秒）" class="inline-field">
              <el-input-number v-model="cfg.follow_timeout" :min="30" :max="300" :step="10" :precision="0"
                               controls-position="right" align="left" />
            </el-form-item>

            <el-form-item label="品种白名单">
              <el-select v-model="whitelist" multiple filterable allow-create default-first-option
                         placeholder="不选 = 全部品种" style="width: 100%"
                         popper-class="monitor-broker-popper">
                <el-option v-for="p in FUTURES_PRODUCTS" :key="p.value" :value="p.value"
                           :label="`${p.label}（${p.value}）`" />
              </el-select>
            </el-form-item>
          </el-form>
        </section>

        <!-- 步骤 3：启动 -->
        <section class="control-panel start-panel">
          <h3>启动</h3>

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
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getBrokers } from '@/api'
import {
  monitorLogin, monitorLogout, getMonitorAccount, getMonitorStatus, getMonitorRecords,
  getMonitorCredentials, startCopy, stopCopy, updateCopyConfig, saveCopyConfig, resumeCopy
} from '@/api/monitor'
import { useUserStore } from '@/stores/user'
import { FUTURES_PRODUCTS } from '@/constants/futuresProducts'

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

// ---- 跟单配置（默认值与后端 DEFAULT_CONFIG 一致）----
const cfg = reactive({
  size_mode: 'multiple', multiplier: 1, fixed_volume: 1, price_offset_ticks: 2, follow_timeout: 60
})
const whitelist = ref([])   // 品种白名单（品种代码数组），空 = 全部品种

const buildConfig = () => ({ ...cfg, symbol_whitelist: whitelist.value })

// ---- 运行状态 ----
const status = ref(null)
const records = ref([])
const logs = ref([])
const busy = ref(false)
const running = computed(() => !!status.value?.running)

const runText = computed(() => {
  if (!running.value) return '未运行'
  if (status.value?.paused_reason) return '已暂停'
  return '运行中'
})
const runClass = computed(() => {
  if (!running.value) return 'off'
  if (status.value?.paused_reason) return 'paused'
  return 'live'
})

const money = (v) => (v === null || v === undefined ? '-' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 }))
const num = (v) => (v === null || v === undefined ? '-' : Number(v).toFixed(2))

const statusType = (s) => ({
  已成交: 'success', 部分成交: 'warning', 已委托: 'primary', 已撤单: 'info',
  已拒绝: 'danger', 失败: 'danger', 已跳过: 'info'
}[s] || 'info')

// ---- 轮询 ----
let timer = null
let polling = false
const refresh = async () => {
  if (polling) return
  polling = true
  try {
    const [st, rc] = await Promise.all([getMonitorStatus(), getMonitorRecords()])
    if (st?.success) {
      status.value = st.data
      if (!configSynced) {      // 首次打开时后端还没起来：拿到状态后再补做配置同步
        syncConfigFromStatus()
        await nextTick()
        configSynced = true
      }
    }
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

// 页面（重新）打开时，把后端已有的配置同步回表单：运行中 = 实际生效的配置；
// 未运行 = 上次保存在本地的配置（后端启动时已读入），保持和上次关闭软件时一样
let configSynced = false     // 同步完成前不触发自动保存，避免用默认值覆盖已保存的配置
const syncConfigFromStatus = () => {
  const c = status.value?.config
  if (!c) return false
  Object.keys(cfg).forEach(k => { if (k in c) cfg[k] = c[k] })
  whitelist.value = [...(c.symbol_whitelist || [])]
  return true
}

// 表单一改就自动保存到本地（防抖）。运行中的修改仍需点「应用修改后的配置」才对信号生效，
// 但保存的是表单当前值，下次打开软件时与关闭时一致
let saveTimer = null
const persistConfig = () => {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    try { await saveCopyConfig(buildConfig()) } catch (e) { /* 保存失败不打扰操作，下次修改会重试 */ }
  }, 500)
}
watch([cfg, whitelist], () => { if (configSynced) persistConfig() }, { deep: true })

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
  await refresh()           // 首次拿到状态时会同步配置并打开自动保存（见 refresh）
  timer = setInterval(refresh, 2000)
})
onBeforeUnmount(() => {
  timer && clearInterval(timer)
  // 离开页面时立即保存尚未落盘的修改
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveCopyConfig(buildConfig()).catch(() => {})
  }
})

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
      // 勾选了「记住」且密码确实保存成功：保留表单里的密码，退出监控账号后不用重新输入；
      // 没勾选（或密码没能保存）：不把密码留在页面内存里
      if (!rememberAccount.value || !res.password_saved) form.password = ''
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
  const summary = `手数：${{ multiple: '固定倍数', fixed: '固定手数' }[cfg.size_mode]}，`
    + `开仓：反向限价（对方成交价${cfg.price_offset_ticks}跳外），平仓：反向市价`
  try {
    await ElMessageBox.confirm(
      `即将【反向】跟单：对方账号 ${account.value?.username} 的新成交，会立即用你的交易账号 ${userStore.username} 做相反方向的真实下单（对方做多你做空，对方做空你做多）。\n\n${summary}\n\n确认启动？`,
      '跟单确认', { type: 'warning', confirmButtonText: '确认跟单', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' })
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
