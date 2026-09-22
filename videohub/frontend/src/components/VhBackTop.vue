<script setup>
/**
 * VhBackTop · 回到顶部悬浮按钮
 *
 * 滚动超过一屏后从右下角弹性浮出，点击平滑回顶。
 * hover 时变为主色圆钮并亮起旋转光环，与品牌播放键同一形状语言。
 */
import { onBeforeUnmount, onMounted, ref } from "vue"
import { PhCaretUp as CaretUp } from "@phosphor-icons/vue"

const show = ref(false)

function onScroll() {
  show.value = window.scrollY > 480
}

function toTop() {
  window.scrollTo({ top: 0, behavior: "smooth" })
}

onMounted(() => {
  window.addEventListener("scroll", onScroll, { passive: true })
  onScroll()
})
onBeforeUnmount(() => window.removeEventListener("scroll", onScroll))
</script>

<template>
  <transition name="btt">
    <button v-if="show" class="btt" aria-label="回到顶部" title="回到顶部" @click="toTop">
      <CaretUp size="16" weight="bold" />
      <span class="btt-ring" aria-hidden="true"></span>
    </button>
  </transition>
</template>

<style scoped>
.btt {
  position: fixed;
  right: 26px;
  bottom: 30px;
  z-index: 90;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  background: var(--surface-3);
  color: var(--text-1);
  cursor: pointer;
  box-shadow: var(--shadow-3);
  transition: background 0.2s ease, color 0.2s ease, transform 0.25s var(--ease-spring),
    border-color 0.2s ease;
}
.btt:hover {
  background: var(--accent-strong);
  color: #000;
  border-color: transparent;
  transform: translateY(-3px);
}
.btt:active { transform: translateY(0) scale(0.94); }

/* hover 光环：绿色细环缓慢巡游 */
.btt-ring {
  position: absolute;
  inset: -5px;
  border-radius: 50%;
  border: 1px solid rgba(30, 215, 96, 0.4);
  opacity: 0;
  transition: opacity 0.25s ease;
  pointer-events: none;
}
.btt:hover .btt-ring {
  opacity: 1;
  animation: vh-rotate 3.2s linear infinite;
}

.btt-enter-active { transition: opacity 0.25s ease, transform 0.35s var(--ease-spring); }
.btt-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.btt-enter-from,
.btt-leave-to { opacity: 0; transform: translateY(16px) scale(0.85); }

@media (max-width: 720px) {
  .btt { right: 16px; bottom: 20px; width: 40px; height: 40px; }
}
</style>
