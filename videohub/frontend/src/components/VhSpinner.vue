<script setup>
/**
 * VhSpinner · 统一加载动画
 *
 * 全站加载态唯一来源，取代各处散落的 <PhSpinner class="spin">。
 * 五种视觉变体，纯 CSS 实现，颜色继承 currentColor，尺寸可任意指定。
 *
 *  - ring   经典圆环缺口旋转（默认，通用按钮 / 内联）
 *  - orbit  中心核 + 两颗卫星球（科幻仪表感，用于解析 / 任务）
 *  - pulse  三层同心波纹扩散（用于后台轮询 / 实时状态）
 *  - bars   等宽柱条跳动（用于数据加载）
 *  - hex    六边环旋转（用于整页 / 舞台级加载）
 */
const props = defineProps({
  /** ring | orbit | pulse | bars | hex */
  variant: { type: String, default: "ring" },
  /** 像素尺寸 */
  size: { type: [Number, String], default: 18 },
  /** 轨道粗细（仅 ring / hex 生效） */
  weight: { type: [Number, String], default: 2 },
  /** 附加文字说明，出现在动画下方或右侧 */
  label: { type: String, default: "" },
  /** 说明文字在右侧（true）还是下方（false） */
  inline: { type: Boolean, default: true },
  /** 块级居中铺满父容器 */
  block: { type: Boolean, default: false },
  /** 无障碍：加载语义描述 */
  alt: { type: String, default: "加载中" },
})

const px = (v) => (typeof v === "number" ? `${v}px` : v)
</script>

<template>
  <div
    class="sp"
    :class="[`sp-${variant}`, { 'sp-block': block, 'sp-inline': inline && label, 'sp-col': !inline && label }]"
    role="status"
    :aria-label="alt"
    :aria-busy="true"
  >
    <!-- ring：圆环 + 缺口 -->
    <span v-if="variant === 'ring'" class="glyph ring" :style="{ width: px(size), height: px(size), borderWidth: px(weight) }" />

    <!-- orbit：中心核 + 双卫星 -->
    <span v-else-if="variant === 'orbit'" class="glyph orbit" :style="{ width: px(size), height: px(size) }">
      <i class="core" />
      <i class="sat s1" />
      <i class="sat s2" />
    </span>

    <!-- pulse：同心波纹 -->
    <span v-else-if="variant === 'pulse'" class="glyph pulse" :style="{ width: px(size), height: px(size) }">
      <i class="w1" /><i class="w2" /><i class="w3" /><i class="core" />
    </span>

    <!-- bars：柱条 -->
    <span v-else-if="variant === 'bars'" class="glyph bars" :style="{ width: px(size), height: px(size) }">
      <i class="b1" /><i class="b2" /><i class="b3" /><i class="b4" /><i class="b5" />
    </span>

    <!-- hex：六边环 -->
    <span v-else class="glyph hex" :style="{ width: px(size), height: px(size), borderWidth: px(weight) }" />

    <span v-if="label" class="sp-label">{{ label }}</span>
    <span class="sr">加载中</span>
  </div>
</template>

<style scoped>
.sp {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  color: currentColor;
  line-height: 0;
}
.sp-block { display: flex; width: 100%; padding: 32px 0; }
.sp-col { flex-direction: column; gap: 12px; }

.glyph { display: block; flex-shrink: 0; position: relative; }
.sp-label {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-3);
  font-family: var(--font-sans);
}

/* 屏幕阅读器专用 */
.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* ---- ring ---- */
.ring {
  border-style: solid;
  border-color: currentColor;
  border-right-color: transparent;
  border-bottom-color: transparent;
  border-radius: 50%;
  opacity: 0.9;
  animation: vh-rotate 0.72s linear infinite;
}

/* ---- orbit ---- */
.orbit { animation: vh-orbit 1.5s linear infinite; }
.orbit .core {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 22%;
  height: 22%;
  margin: -11% 0 0 -11%;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 10px currentColor;
}
.orbit .sat {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 18%;
  height: 18%;
  margin: -9% 0 0 -9%;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.85;
}
.orbit .s1 { transform: rotate(0deg) translateX(160%); }
.orbit .s2 { transform: rotate(180deg) translateX(160%); opacity: 0.4; }

/* ---- pulse ---- */
.pulse { display: grid; place-items: center; }
.pulse i {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid currentColor;
  animation: vh-pulse-ring 1.9s var(--ease-out) infinite;
}
.pulse .w2 { animation-delay: 0.42s; }
.pulse .w3 { animation-delay: 0.84s; }
.pulse .core {
  width: 30%;
  height: 30%;
  inset: auto;
  background: currentColor;
  border: 0;
  animation: vh-breathe 1.9s var(--ease-in-out) infinite;
}

/* ---- bars ---- */
.bars { display: flex; align-items: flex-end; justify-content: space-between; }
.bars i {
  width: 14%;
  height: 100%;
  border-radius: 2px;
  background: currentColor;
  transform-origin: bottom center;
  animation: vh-bars 1s var(--ease-in-out) infinite;
}
.bars .b2 { animation-delay: 0.1s; }
.bars .b3 { animation-delay: 0.2s; }
.bars .b4 { animation-delay: 0.3s; }
.bars .b5 { animation-delay: 0.4s; }

/* ---- hex ---- */
.hex {
  border-style: solid;
  border-color: currentColor transparent transparent;
  border-radius: 22%;
  animation: vh-rotate 1.1s var(--ease-in-out) infinite;
}
.hex::after {
  content: "";
  position: absolute;
  inset: 12%;
  border: 1px solid currentColor;
  border-radius: 22%;
  opacity: 0.35;
  animation: vh-rotate 2.2s linear infinite reverse;
}
</style>
