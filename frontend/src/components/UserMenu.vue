<template>
  <div class="user-menu">
    <!-- 一级菜单：点击头像展开 -->
    <el-popover
      v-model:visible="menuVisible"
      trigger="click"
      placement="bottom-end"
      :width="160"
      :show-arrow="false"
      :offset="8"
      :persistent="false"
      popper-class="user-menu-popper"
      @hide="onMenuHide"
    >
      <template #reference>
        <button class="user-menu-trigger" type="button" title="用户菜单">
          <div class="user-avatar">{{ userStore.username?.[0]?.toUpperCase() || 'U' }}</div>
          <span class="user-menu-name">{{ userStore.username || '未登录' }}</span>
          <svg class="user-menu-caret" :class="{ 'is-open': menuVisible }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
      </template>

      <div class="user-menu-list" role="menu">
        <!-- 二级菜单：切换主题。点击后在本行下方向下展开 -->
        <div
          class="user-menu-parent"
          :class="{ 'is-open': themeMenuVisible }"
          role="menuitem"
          aria-haspopup="true"
          :aria-expanded="themeMenuVisible"
          @click="toggleThemeMenu"
        >
          <span class="user-menu-parent-label">切换主题</span>
          <svg class="user-menu-parent-arrow" :class="{ 'is-open': themeMenuVisible }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>

        <div v-show="themeMenuVisible" class="user-menu-submenu" role="menu">
          <div
            v-for="t in THEMES"
            :key="t.value"
            class="user-menu-submenu-item"
            :class="{ 'is-active-theme': t.value === themeStore.theme }"
            role="menuitemradio"
            :aria-checked="t.value === themeStore.theme"
            @click="selectTheme(t.value)"
          >
            <span class="theme-swatch" :style="{ background: t.color }"></span>
            {{ t.label }}
            <span v-if="t.value === themeStore.theme" class="theme-check">✓</span>
          </div>
        </div>

        <div class="user-menu-divider"></div>

        <div
          class="user-menu-item user-menu-logout"
          role="menuitem"
          @click="handleLogoutClick"
        >
          <svg class="user-menu-item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          退出登录
        </div>
      </div>
    </el-popover>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { logout } from '@/api'
import { useUserStore } from '@/stores/user'
import { THEMES, useThemeStore } from '@/stores/theme'

const router = useRouter()
const userStore = useUserStore()
const themeStore = useThemeStore()

const menuVisible = ref(false)

// ---------- 二级菜单：切换主题（点击在下方展开 / 收起） ----------
const themeMenuVisible = ref(false)

const toggleThemeMenu = () => {
  themeMenuVisible.value = !themeMenuVisible.value
}

const closeMenu = () => {
  themeMenuVisible.value = false
  menuVisible.value = false
}

// 一级菜单关闭后收起二级菜单，下次打开时恢复初始状态
const onMenuHide = () => {
  themeMenuVisible.value = false
}

const selectTheme = (value) => {
  themeStore.setTheme(value)
  closeMenu()
}

// ---------- 退出登录 ----------
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

const handleLogoutClick = () => {
  closeMenu()
  handleLogout()
}
</script>

<style scoped>
@import '@/styles/UserMenu.css';
</style>

<style>
@import '@/styles/UserMenuPopper.css';
</style>
