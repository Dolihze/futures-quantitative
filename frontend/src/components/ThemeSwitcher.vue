<template>
  <el-dropdown trigger="click" @command="themeStore.setTheme">
    <button class="theme-switcher" type="button" title="切换主题">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="13.5" cy="6.5" r="1.5" />
        <circle cx="17.5" cy="10.5" r="1.5" />
        <circle cx="8.5" cy="7.5" r="1.5" />
        <circle cx="6.5" cy="12.5" r="1.5" />
        <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z" />
      </svg>
      <span>{{ current.label }}</span>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="t in THEMES"
          :key="t.value"
          :command="t.value"
          :class="{ 'is-active-theme': t.value === themeStore.theme }"
        >
          <span class="theme-swatch" :style="{ background: t.color }"></span>
          {{ t.label }}
          <span v-if="t.value === themeStore.theme" class="theme-check">✓</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import { computed } from 'vue'
import { THEMES, useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
const current = computed(() => THEMES.find((t) => t.value === themeStore.theme) || THEMES[0])
</script>

<style scoped>
.theme-switcher {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(var(--primary-rgb), 0.1);
  border: 1px solid rgba(var(--primary-rgb), 0.3);
  border-radius: 6px;
  color: var(--primary);
  font-size: 12px;
  cursor: pointer;
  outline: none;
  transition: all 0.2s;
}

.theme-switcher:hover {
  background: rgba(var(--primary-rgb), 0.2);
  border-color: rgba(var(--primary-rgb), 0.5);
}

.theme-switcher svg {
  width: 14px;
  height: 14px;
}

.theme-swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 8px;
  border-radius: 50%;
  border: 1px solid rgba(148, 163, 184, 0.6);
}

.theme-check {
  margin-left: 10px;
  color: var(--primary);
}

.is-active-theme {
  color: var(--primary);
}
</style>
