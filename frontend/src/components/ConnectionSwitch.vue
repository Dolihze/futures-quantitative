<template>
  <div class="connection-status">
    <div class="status-indicator" :class="{ connected: modelValue }"></div>
    <span class="status-text" :class="{ connected: modelValue }">
      {{ modelValue ? connectedText : disconnectedText }}
    </span>
    <el-switch
      :model-value="modelValue"
      :loading="loading"
      :disabled="loading"
      size="small"
      class="connection-switch"
      @update:model-value="emit('update:modelValue', $event)"
      @change="emit('change', $event)"
    />
  </div>
</template>

<script setup>
/**
 * 连接状态 + 连接开关：一个状态指示点、一段状态文字和一个开关。
 *
 * 只负责展示和抛出用户的操作，不含任何连接逻辑——真正的连接 / 断开（请求后端、轮询等）由使用方处理：
 *   <ConnectionSwitch v-model="connected" :loading="connecting" @change="onToggle" />
 * 连接是异步的，使用方在 @change 里发请求，成功 / 失败后自己改 v-model 和 loading。
 */
defineProps({
  // 是否已连接（v-model）
  modelValue: { type: Boolean, default: false },
  // 连接中：开关显示 Element Plus 自带的转圈并禁用，防止重复点击
  loading: { type: Boolean, default: false },
  connectedText: { type: String, default: '量化账号已连接' },
  disconnectedText: { type: String, default: '未连接量化账号' }
})

const emit = defineEmits(['update:modelValue', 'change'])
</script>

<style scoped>
@import '@/styles/ConnectionSwitch.css';
</style>
