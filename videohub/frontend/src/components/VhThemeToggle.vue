<script setup>
/**
 * VhThemeToggle · 主题开关
 *
 * 暗色 / 浅色双主题切换的胶囊开关：两端日 / 月图标，滑块带极光渐变，
 * 状态持久化由 stores/theme.js 负责。全站可复用（导航栏 / 登录页）。
 */
import { computed } from "vue"
import { PhSun as Sun, PhMoonStars as MoonStars } from "@phosphor-icons/vue"
import { useThemeStore } from "../stores/theme"

const theme = useThemeStore()
const isLight = computed(() => theme.isLight)
</script>

<template>
  <button
    type="button"
    class="theme-toggle"
    role="switch"
    :aria-checked="isLight"
    :aria-label="isLight ? '切换到暗色主题' : '切换到浅色主题'"
    :title="isLight ? '切换到暗色主题' : '切换到浅色主题'"
    @click="theme.toggle()"
  >
    <span class="tt-icon tt-sun" :class="{ on: isLight }">
      <Sun size="13" weight="fill" />
    </span>
    <span class="tt-icon tt-moon" :class="{ on: !isLight }">
      <MoonStars size="13" weight="fill" />
    </span>
    <span class="tt-knob" :class="{ light: isLight }" aria-hidden="true"></span>
  </button>
</template>

<style scoped>
.theme-toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  width: 58px;
  height: 30px;
  padding: 0 6px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--tint);
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.25s ease;
}
.theme-toggle:hover {
  border-color: rgba(60, 228, 119, 0.45);
  box-shadow: 0 0 16px -6px rgba(30, 215, 96, 0.45);
}
.theme-toggle:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* 两端日 / 月图标：选中侧高亮，另一侧退到辅助色 */
.tt-icon {
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  color: var(--text-3);
  transition: color 0.3s ease, transform 0.4s var(--ease-spring);
}
.tt-icon.on { color: var(--accent); }
.tt-sun.on { transform: rotate(30deg) scale(1.1); }
.tt-moon.on { transform: rotate(-20deg) scale(1.1); }

/* 滑块：品牌绿圆钮，浅色时滑向日侧 */
.tt-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 22px;
  height: 22px;
  border-radius: var(--r-pill);
  background: var(--grad-brand);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
  transition: transform 0.35s var(--ease-spring);
}
.tt-knob.light { transform: translateX(28px); }
</style>
