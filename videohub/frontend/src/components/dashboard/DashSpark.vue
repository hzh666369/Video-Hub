<script setup>
/**
 * DashSpark · 读数下方的迷你趋势线
 *
 * 纯 SVG，无图表库依赖。视口 300×30（等比映射到容器宽度，≈1:1），
 * 曲线为 Catmull-Rom 转三次贝塞尔，末端留一个描边圆点作为「当前值」锚点。
 * 仅作形态度量，不承载精确读数（精确值在上方的大号数字里）。
 *
 * 高度由父级变量 --spark-h 控制（仪表读数带里压到 20px，卡片场景保持 30px），
 * 曲线用 preserveAspectRatio="none" 拉伸，所以改高度不需要动几何计算。
 *
 * 颜色：color 传的是 **CSS 变量表达式**（如 "var(--bd-azure)"），因此必须走
 * style 而非 SVG 呈现属性 —— 浏览器不支持在 fill/stroke 属性里解析 var()。
 * 这样明暗主题切换时无需重渲染，曲线颜色自动跟随。
 */
import { computed, useId } from "vue"

const props = defineProps({
  /** 数值序列，至少 2 个点才渲染 */
  values: { type: Array, default: () => [] },
  /** 主色，CSS 变量表达式（如 "var(--bd-aqua)"）或任意合法色值 */
  color: { type: String, default: "var(--bd-aqua, #45e0c0)" },
})

const W = 300
const H = 30
const PAD = 3

/* 同页可能出现多条 spark，渐变 id 必须唯一，否则后面的会覆盖前面的填充 */
const uid = `vh-spark-${useId().replace(/[^a-zA-Z0-9]/g, "")}`

const geo = computed(() => {
  const v = props.values
  if (!Array.isArray(v) || v.length < 2) return { line: "", area: "", last: null }

  const max = (Math.max(...v) || 1) * 1.15
  const n = v.length
  const pts = v.map((val, i) => [
    PAD + (i * (W - PAD * 2)) / (n - 1),
    H - PAD - (val / max) * (H - PAD * 2),
  ])

  let d = `M ${pts[0][0].toFixed(2)} ${pts[0][1].toFixed(2)}`
  for (let i = 0; i < n - 1; i++) {
    const p0 = pts[i - 1] || pts[i]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[i + 2] || p2
    const c1x = p1[0] + (p2[0] - p0[0]) / 6
    const c1y = p1[1] + (p2[1] - p0[1]) / 6
    const c2x = p2[0] - (p3[0] - p1[0]) / 6
    const c2y = p2[1] - (p3[1] - p1[1]) / 6
    d += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`
  }

  return {
    line: d,
    area: `${d} L ${pts[n - 1][0].toFixed(2)} ${H} L ${pts[0][0].toFixed(2)} ${H} Z`,
    last: pts[n - 1],
  }
})
</script>

<template>
  <svg
    class="spark"
    :viewBox="`0 0 ${W} ${H}`"
    preserveAspectRatio="none"
    aria-hidden="true"
    focusable="false"
  >
    <defs>
      <linearGradient :id="uid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" :style="{ stopColor: color }" stop-opacity="0.4" />
        <stop offset="100%" :style="{ stopColor: color }" stop-opacity="0" />
      </linearGradient>
    </defs>
    <template v-if="geo.line">
      <path :d="geo.area" :fill="`url(#${uid})`" />
      <path
        :d="geo.line"
        fill="none"
        :style="{ stroke: color }"
        stroke-width="1.6"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
      />
      <circle
        :cx="geo.last[0]"
        :cy="geo.last[1]"
        r="2.6"
        :style="{ fill: 'var(--bd-solid, #06080c)', stroke: color }"
        stroke-width="1.6"
        vector-effect="non-scaling-stroke"
      />
    </template>
  </svg>
</template>

<style scoped>
.spark {
  display: block;
  width: 100%;
  /* 高度交由父级决定：--spark-h 由仪表读数带 / 卡片容器设置 */
  height: var(--spark-h, 30px);
  overflow: visible;
}
</style>
