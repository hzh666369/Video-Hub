<script setup>
/**
 * VhEmptyArt · 空状态线稿插画
 *
 * 极简线稿风 + 轻微 3D 悬浮感：蓝紫细线、虚线轨道、弥散基座阴影，
 * 元素带缓慢呼吸浮动，避免空状态视域空洞。
 * variant: tray = 任务托盘 | film = 视频胶片
 */
defineProps({
  variant: { type: String, default: "tray" },
})
</script>

<template>
  <svg class="empty-art" viewBox="0 0 220 150" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs>
      <linearGradient id="ea-grad" x1="70" y1="40" x2="150" y2="120" gradientUnits="userSpaceOnUse">
        <stop stop-color="#1ED760" />
        <stop offset="1" stop-color="#FFA42B" />
      </linearGradient>
      <radialGradient id="ea-shadow" cx="0.5" cy="0.5" r="0.5">
        <stop stop-color="rgba(30, 215, 96, 0.28)" />
        <stop offset="1" stop-color="rgba(30, 215, 96, 0)" />
      </radialGradient>
    </defs>

    <!-- 虚线轨道 -->
    <circle cx="110" cy="70" r="55" stroke="rgba(148, 163, 184, 0.2)" stroke-width="1" stroke-dasharray="3 8" />
    <circle cx="110" cy="70" r="55" stroke="url(#ea-grad)" stroke-width="1.4" stroke-dasharray="14 200" stroke-linecap="round" class="ea-orbit" />

    <!-- 基座弥散阴影 -->
    <ellipse cx="110" cy="128" rx="54" ry="10" fill="url(#ea-shadow)" />

    <g v-if="variant === 'tray'" class="ea-float">
      <!-- 托盘主体 -->
      <path
        d="M76 96 h68 a5 5 0 0 1 5 5 v6 a5 5 0 0 1 -5 5 h-68 a5 5 0 0 1 -5 -5 v-6 a5 5 0 0 1 5 -5 z"
        stroke="url(#ea-grad)" stroke-width="2"
      />
      <!-- 队列条：依次浮起 -->
      <rect x="86" y="76" width="48" height="7" rx="3.5" stroke="rgba(148, 163, 184, 0.55)" stroke-width="1.6" />
      <rect x="92" y="58" width="36" height="7" rx="3.5" stroke="rgba(148, 163, 184, 0.4)" stroke-width="1.6" />
      <!-- 上升箭头 -->
      <path d="M110 62 V28 M100 38 L110 27 L120 38" stroke="url(#ea-grad)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
      <!-- 光点 -->
      <circle cx="152" cy="40" r="2.4" fill="#FFA42B" />
      <circle cx="70" cy="52" r="1.8" fill="#1ED760" />
    </g>

    <g v-else class="ea-float">
      <!-- 播放器屏幕 -->
      <rect x="72" y="44" width="76" height="48" rx="8" stroke="url(#ea-grad)" stroke-width="2" />
      <!-- 播放钮（currentColor 随主题文字色变化） -->
      <circle cx="110" cy="66" r="10" stroke="currentColor" stroke-opacity="0.45" stroke-width="1.6" />
      <path d="M107 61.5 V70.5 L114.5 66 Z" fill="currentColor" fill-opacity="0.6" />
      <!-- 进度条 -->
      <rect x="80" y="83" width="60" height="3.5" rx="1.75" fill="rgba(148, 163, 184, 0.3)" />
      <rect x="80" y="83" width="26" height="3.5" rx="1.75" fill="url(#ea-grad)" />
      <!-- 胶片格 -->
      <rect x="146" y="34" width="24" height="18" rx="3.5" stroke="rgba(148, 163, 184, 0.45)" stroke-width="1.5" />
      <path d="M150 39.5 h4 M156 39.5 h4 M162 39.5 h4 M150 46.5 h4 M156 46.5 h4 M162 46.5 h4" stroke="rgba(148, 163, 184, 0.35)" stroke-width="1.3" stroke-linecap="round" />
      <!-- 光点 -->
      <circle cx="64" cy="38" r="2.4" fill="#1ED760" />
      <circle cx="158" cy="82" r="1.8" fill="#FFA42B" />
    </g>
  </svg>
</template>

<style scoped>
.empty-art {
  display: block;
  width: 200px;
  height: auto;
  margin-bottom: 2px;
}

/* 主体缓慢悬浮 */
.ea-float {
  animation: ea-float 4.5s var(--ease-in-out) infinite;
  transform-origin: 110px 90px;
}
@keyframes ea-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}

/* 轨道上的极光弧缓慢巡游 */
.ea-orbit {
  animation: ea-orbit-spin 7s linear infinite;
  transform-origin: 110px 70px;
}
@keyframes ea-orbit-spin {
  to { transform: rotate(360deg); }
}
</style>
