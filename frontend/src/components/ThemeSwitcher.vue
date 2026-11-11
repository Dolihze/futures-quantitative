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
@import '@/styles/ThemeSwitcher.css';
</style>
