<script setup>
/**
 * VhAurora · 科幻氛围背景层
 *
 * 纯装饰、不吃指针事件、不进无障碍树。由四层叠加构成：
 *  1. 透视网格空间（缓慢漂移，制造纵深）
 *  2. 三颗呼吸光球（电光蓝 / 极光紫 / 青蓝，错位浮动）
 *  3. 一道自上而下的扫描光带（可选）
 *  4. 暗角，把注意力收回内容
 *
 * 全部走电光蓝 + 极光紫色板，蓝紫霓虹但不刺眼。
 */
defineProps({
  /** page=整页固定底 | hero=局部区块底 | subtle=极简 */
  variant: { type: String, default: "page" },
  /** 是否显示扫描光带 */
  scan: { type: Boolean, default: true },
  /** 是否显示网格 */
  grid: { type: Boolean, default: true },
  /** 整体强度 0.4 ~ 1.4 */
  intensity: { type: Number, default: 1 },
})
</script>

<template>
  <div
    class="aurora"
    :class="[`au-${variant}`, { 'no-scan': !scan, 'no-grid': !grid }]"
    :style="{ '--au-i': intensity }"
    aria-hidden="true"
  >
    <span class="au-grid"></span>
    <span class="au-orb o1"></span>
    <span class="au-orb o2"></span>
    <span class="au-orb o3"></span>
    <span class="au-scan"></span>
    <span class="au-vignette"></span>
  </div>
</template>

<style scoped>
.aurora {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}
.aurora.au-page { position: fixed; }

/* ---- 网格空间 ---- */
.au-grid {
  position: absolute;
  inset: -20% -10% 0;
  background-image:
    linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: var(--grid-size) var(--grid-size);
  opacity: calc(0.9 * var(--au-i));
  mask-image: radial-gradient(90% 62% at 50% 8%, #000 10%, transparent 78%);
  -webkit-mask-image: radial-gradient(90% 62% at 50% 8%, #000 10%, transparent 78%);
  animation: vh-grid-drift 30s linear infinite;
}
.no-grid .au-grid { display: none; }

/* ---- 呼吸光球 ---- */
.au-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  animation: vh-float 11s var(--ease-in-out) infinite;
  will-change: transform;
}
.o1 {
  width: 420px; height: 420px;
  top: -140px; left: 8%;
  background: var(--halo-accent);
  opacity: calc(0.85 * var(--au-i));
}
.o2 {
  width: 340px; height: 340px;
  top: 22%; right: -90px;
  background: var(--halo-violet);
  opacity: calc(0.6 * var(--au-i));
  animation-delay: -4.2s;
  animation-duration: 14s;
}
.o3 {
  width: 300px; height: 300px;
  bottom: -110px; left: 42%;
  background: var(--halo-accent);
  opacity: calc(0.45 * var(--au-i));
  animation-delay: -7.5s;
  animation-duration: 17s;
}

/* ---- 扫描光带 ---- */
.au-scan {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 180px;
  background: linear-gradient(180deg, transparent, rgba(60, 228, 119, 0.055), transparent);
  animation: vh-scan-y 9s var(--ease-in-out) infinite;
  opacity: var(--au-i);
}
.no-scan .au-scan { display: none; }

/* ---- 暗角（dark=深色压角 / light=冷灰压角，收回注意力） ---- */
.au-vignette {
  position: absolute;
  inset: 0;
  background: radial-gradient(120% 80% at 50% 20%, transparent 40%, var(--vignette) 100%);
}
.au-hero .au-vignette { background: linear-gradient(180deg, transparent 55%, var(--vignette-strong) 100%); }
</style>
