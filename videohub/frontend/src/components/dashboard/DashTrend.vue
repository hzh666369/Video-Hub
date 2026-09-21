<script setup>
/**
 * DashTrend · 看板趋势图（主题自适应版）
 *
 * 语义色锁（v5 Operations Center）：解析量 = aqua 主线 + 渐变面积 + 辉光（核心价值指标）；
 *          访问量 = azure 蓝细线 + 渐变面积（流量类指标，与参考稿的「蓝 / 青」双线一致）。
 * 双线都向底部渐隐，视觉上解析量始终压在访问量之上。
 * 图例由宿主面板自绘（本组件不注册 LegendComponent），避免与面板标题重复。
 *
 * 横轴刻度：宿主会传 7 / 30 / 90 天三种切片，间隔按长度自适应，
 * 让三种档位都稳定显示约 6 个日期标签。
 *
 * 主题：canvas 读不到 CSS 变量，所以每次构建 option 时用 getComputedStyle
 * 从宿主元素上把 --bd-* 解析成真实色值；并 watch 主题 store，切换后重绘。
 *
 * ECharts 按需引入控制体积；prefers-reduced-motion 时关闭入场动画。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import * as echarts from "echarts/core"
import { LineChart } from "echarts/charts"
import { GridComponent, TooltipComponent } from "echarts/components"
import { CanvasRenderer } from "echarts/renderers"
import { useThemeStore } from "../../stores/theme"

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const FALLBACK_MONO =
  'ui-monospace, "SF Mono", "Cascadia Mono", "JetBrains Mono", Consolas, monospace'

const REDUCED =
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches

const props = defineProps({
  days: { type: Array, default: () => [] },
  visits: { type: Array, default: () => [] },
  parses: { type: Array, default: () => [] },
})

const themeStore = useThemeStore()

const host = ref(null)
let chart = null
let ro = null

/** 把宿主元素上继承来的 --bd-* 解析成真实色值（canvas 无法直接用 var） */
function palette() {
  const fallback = {
    aqua: "#45e0c0",
    azure: "#4d8dff",
    axis: "rgba(148,163,184,0.16)",
    split: "rgba(148,163,184,0.07)",
    label: "#64748b",
    tipBg: "rgba(8,13,26,0.94)",
    tipLine: "rgba(148,163,184,0.2)",
    tipText: "#eef2f9",
    cross: "rgba(148,163,184,0.4)",
    area0: "rgba(69,224,192,0.26)",
    area1: "rgba(69,224,192,0.08)",
    area2: "rgba(69,224,192,0)",
    glow: "rgba(69,224,192,0.5)",
    aArea0: "rgba(77,141,255,0.3)",
    aArea1: "rgba(77,141,255,0.09)",
    aArea2: "rgba(77,141,255,0)",
    aGlow: "rgba(77,141,255,0.42)",
  }
  if (!host.value) return fallback
  const cs = getComputedStyle(host.value)
  if (!cs) return fallback
  const v = (name, fb) => {
    const raw = cs.getPropertyValue(name)
    return raw && raw.trim() ? raw.trim() : fb
  }
  return {
    aqua: v("--bd-aqua", fallback.aqua),
    azure: v("--bd-azure", fallback.azure),
    axis: v("--bd-chart-axis", fallback.axis),
    split: v("--bd-chart-split", fallback.split),
    label: v("--bd-chart-label", fallback.label),
    tipBg: v("--bd-tip-bg", fallback.tipBg),
    tipLine: v("--bd-tip-line", fallback.tipLine),
    tipText: v("--bd-t1", fallback.tipText),
    cross: v("--bd-chart-cross", fallback.cross),
    area0: v("--bd-area-0", fallback.area0),
    area1: v("--bd-area-1", fallback.area1),
    area2: v("--bd-area-2", fallback.area2),
    glow: v("--bd-line-glow", fallback.glow),
    aArea0: v("--bd-azure-area-0", fallback.aArea0),
    aArea1: v("--bd-azure-area-1", fallback.aArea1),
    aArea2: v("--bd-azure-area-2", fallback.aArea2),
    aGlow: v("--bd-azure-glow", fallback.aGlow),
  }
}

function buildOption() {
  const p = palette()
  /* v6.1 小数据打磨：7D（点少）时常显数据点，30/90 天密集档保持无点；
   * 双线加粗一档，小数值曲线更有视觉重量 */
  const few = props.days.length > 0 && props.days.length <= 16
  return {
    backgroundColor: "transparent",
    animation: !REDUCED,
    animationDuration: 600,
    tooltip: {
      trigger: "axis",
      backgroundColor: p.tipBg,
      borderColor: p.tipLine,
      borderWidth: 1,
      padding: [9, 13],
      extraCssText: "border-radius:10px;box-shadow:0 12px 30px -14px rgba(0,0,0,.55);",
      textStyle: { color: p.tipText, fontSize: 11, fontFamily: FALLBACK_MONO },
      /* 参考稿样式：日期为标题行，两条系列带彩点缩进排列 */
      formatter(params) {
        if (!Array.isArray(params) || !params.length) return ""
        const rows = params
          .map(
            (it) =>
              `<div style="display:flex;align-items:center;gap:7px;margin-top:5px;">` +
              `<span style="width:6px;height:6px;border-radius:50%;background:${it.color};"></span>` +
              `<span style="color:#94a3b8;">${it.seriesName}</span>` +
              `<span style="margin-left:auto;padding-left:16px;font-weight:700;">${it.value}</span></div>`,
          )
          .join("")
        return `<div style="font-weight:700;margin-bottom:2px;">${params[0].axisValue}</div>${rows}`
      },
      axisPointer: {
        type: "line",
        lineStyle: { color: p.cross, width: 1, type: [4, 4] },
      },
    },
    grid: { left: 40, right: 18, top: 18, bottom: 26 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: props.days,
      axisLine: { lineStyle: { color: p.axis } },
      axisLabel: {
        color: p.label,
        fontSize: 10,
        fontFamily: FALLBACK_MONO,
        /* 三种档位（7/30/90）都稳定出约 6 个标签 */
        interval: Math.max(0, Math.ceil(props.days.length / 6) - 1),
        margin: 11,
      },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      splitLine: { lineStyle: { color: p.split } },
      axisLabel: { color: p.label, fontSize: 10, fontFamily: FALLBACK_MONO },
    },
    series: [
      {
        name: "访问量",
        type: "line",
        smooth: true,
        showSymbol: few,
        symbolSize: 6,
        data: props.visits,
        lineStyle: {
          width: 2.4,
          color: p.azure,
          shadowColor: p.aGlow,
          shadowBlur: 10,
          shadowOffsetY: 2,
        },
        itemStyle: { color: p.azure },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: p.aArea0 },
            { offset: 0.55, color: p.aArea1 },
            { offset: 1, color: p.aArea2 },
          ]),
        },
      },
      {
        name: "解析量",
        type: "line",
        smooth: true,
        showSymbol: few,
        symbolSize: 7,
        data: props.parses,
        lineStyle: {
          width: 2.6,
          color: p.aqua,
          shadowColor: p.glow,
          shadowBlur: 13,
          shadowOffsetY: 2,
        },
        itemStyle: { color: p.aqua },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: p.area0 },
            { offset: 0.55, color: p.area1 },
            { offset: 1, color: p.area2 },
          ]),
        },
      },
    ],
  }
}

function render() {
  if (chart) chart.setOption(buildOption(), { notMerge: true })
}

/** 容器尺寸为 0（如处于隐藏态）时跳过，避免 ECharts 记录错误的画布尺寸 */
function resize() {
  if (!chart || !host.value) return
  const { width, height } = host.value.getBoundingClientRect()
  if (width > 0 && height > 0) chart.resize()
}

onMounted(() => {
  chart = echarts.init(host.value)
  render()
  window.addEventListener("resize", resize)
  /* 全屏投屏 / 栅格断点变化都会改变容器尺寸，交给 ResizeObserver 兜底 */
  if ("ResizeObserver" in window) {
    ro = new ResizeObserver(resize)
    ro.observe(host.value)
  }
})

watch(() => [props.days, props.visits, props.parses], render)

/* 明暗主题切换 → 重新读取色板并重绘（nextTick 保证 data-theme 已落到 DOM） */
watch(
  () => themeStore.theme,
  () => nextTick(render),
)

onBeforeUnmount(() => {
  window.removeEventListener("resize", resize)
  if (ro) { ro.disconnect(); ro = null }
  if (chart) { chart.dispose(); chart = null }
})
</script>

<template>
  <div ref="host" class="dash-trend"></div>
</template>

<style scoped>
.dash-trend {
  /* 相对定位 + z-index：压在上层，避免被父级点阵底纹盖住 */
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  min-height: 96px;
}
</style>
