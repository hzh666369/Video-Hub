<script setup>
import { computed, ref } from "vue"

/**
 * 可交互眼球：跟随鼠标转动瞳孔，或在 force 方向下强制注视。
 * bare 模式 = 纯瞳孔点（无白色眼球底），用于橙色/黄色角色。
 */
const props = defineProps({
  size: { type: Number, default: 48 },
  pupilSize: { type: Number, default: 16 },
  maxDistance: { type: Number, default: 10 },
  eyeColor: { type: String, default: "white" },
  pupilColor: { type: String, default: "black" },
  blinking: { type: Boolean, default: false },
  forceX: { type: Number, default: undefined },
  forceY: { type: Number, default: undefined },
  bare: { type: Boolean, default: false },
  mouseX: { type: Number, default: 0 },
  mouseY: { type: Number, default: 0 },
})

const eyeRef = ref(null)

const pupilPos = computed(() => {
  if (props.forceX !== undefined && props.forceY !== undefined) {
    return { x: props.forceX, y: props.forceY }
  }
  const el = eyeRef.value
  if (!el) return { x: 0, y: 0 }
  const r = el.getBoundingClientRect()
  const cx = r.left + r.width / 2
  const cy = r.top + r.height / 2
  const dx = props.mouseX - cx
  const dy = props.mouseY - cy
  const d = Math.min(Math.hypot(dx, dy), props.maxDistance)
  const a = Math.atan2(dy, dx)
  return { x: Math.cos(a) * d, y: Math.sin(a) * d }
})
</script>

<template>
  <!-- 纯瞳孔模式 -->
  <div
    v-if="bare && !blinking"
    class="pupil"
    :style="{
      width: size + 'px',
      height: size + 'px',
      backgroundColor: pupilColor,
      transform: `translate(${pupilPos.x}px, ${pupilPos.y}px)`,
    }"
  />
  <!-- 眼球模式 -->
  <div
    v-else-if="!blinking"
    ref="eyeRef"
    class="eyeball"
    :style="{
      width: size + 'px',
      height: size + 'px',
      backgroundColor: eyeColor,
    }"
  >
    <div
      class="pupil"
      :style="{
        width: pupilSize + 'px',
        height: pupilSize + 'px',
        backgroundColor: pupilColor,
        transform: `translate(${pupilPos.x}px, ${pupilPos.y}px)`,
      }"
    />
  </div>
  <!-- 眨眼：压成一条线 -->
  <div
    v-else
    class="eyeball blink-line"
    :style="{ backgroundColor: eyeColor }"
  />
</template>

<style scoped>
.eyeball {
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: height 0.15s ease;
  flex-shrink: 0;
}
.eyeball.blink-line {
  width: 100%;
  height: 2px;
}
.pupil {
  border-radius: 50%;
  transition: transform 0.1s ease-out;
  flex-shrink: 0;
}
</style>
