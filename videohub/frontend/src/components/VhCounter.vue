<script setup>
/**
 * VhCounter · 数字滚动读数
 *
 * 进入视口后从 0 递增到目标值（缓出曲线），数值变化时做补间过渡。
 * 用于统计条，制造仪表盘式的数据呼吸感。
 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue"

const props = defineProps({
  value: { type: Number, default: 0 },
  /** 动画时长（毫秒） */
  duration: { type: Number, default: 1100 },
  /** 小数位 */
  decimals: { type: Number, default: 0 },
  /** 千分位分隔 */
  group: { type: Boolean, default: true },
  /** 前缀 / 后缀 */
  prefix: { type: String, default: "" },
  suffix: { type: String, default: "" },
})

const host = ref(null)
const shown = ref(0)
let raf = null
let io = null
let started = false

const REDUCED =
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches

function format(n) {
  const fixed = n.toFixed(props.decimals)
  if (!props.group) return fixed
  const [i, d] = fixed.split(".")
  const g = i.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
  return d ? `${g}.${d}` : g
}

function animate(from, to) {
  cancelAnimationFrame(raf)
  if (REDUCED || props.duration <= 0) { shown.value = to; return }
  const t0 = performance.now()
  const step = (now) => {
    const p = Math.min(1, (now - t0) / props.duration)
    // 缓出：起步快、收尾稳
    const eased = 1 - Math.pow(1 - p, 3)
    shown.value = from + (to - from) * eased
    if (p < 1) raf = requestAnimationFrame(step)
    else shown.value = to
  }
  raf = requestAnimationFrame(step)
}

function start() {
  if (started) return
  started = true
  animate(0, props.value)
}

onMounted(() => {
  if (REDUCED || !("IntersectionObserver" in window)) { shown.value = props.value; started = true; return }
  io = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        start()
        io && io.disconnect()
      }
    },
    { threshold: 0.35 },
  )
  if (host.value) io.observe(host.value)
  else start()
})

watch(
  () => props.value,
  (v, old) => {
    if (!started) return
    animate(typeof old === "number" ? shown.value : 0, v)
  },
)

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  if (io) io.disconnect()
})
</script>

<template>
  <span ref="host" class="cnt vh-readout">{{ prefix }}{{ format(shown) }}{{ suffix }}</span>
</template>

<style scoped>
.cnt {
  display: inline-block;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.015em;
}
</style>
