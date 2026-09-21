<script setup>
/**
 * VhMorphPanel · 容器变形（Compact → Expanded）
 *
 * 不是简单的「显示 / 隐藏更多内容」，而是容器本身在一次过渡里
 * 完成形变：内边距、圆角、底色、描边、光晕、网格底纹、四角标
 * 同时发生变化，内容区再用真实高度补间顶开，整体像一台仪器
 * 从待机形态展开为工作形态。
 *
 *  #compact  插槽：常驻的紧凑面（永远可见）
 *  default   插槽：展开后承载的内容
 */
import { computed, ref, watch } from "vue"

const props = defineProps({
  /** 受控展开状态；传 null 则由内部自管 */
  modelValue: { type: Boolean, default: null },
  defaultOpen: { type: Boolean, default: false },
  /** 展开时长（毫秒） */
  duration: { type: Number, default: 460 },
  /** 紧凑态内边距 */
  compactPadding: { type: String, default: "16px 18px" },
  /** 展开态内边距 */
  expandedPadding: { type: String, default: "26px 28px" },
  /** 紧凑态圆角 */
  compactRadius: { type: String, default: "12px" },
  /** 展开态圆角 */
  expandedRadius: { type: String, default: "20px" },
  /** 展开时是否显示一次性扫描光束 */
  scan: { type: Boolean, default: true },
})

const emit = defineEmits(["update:modelValue", "toggle"])

const inner = ref(props.defaultOpen)
const controlled = computed(() => props.modelValue !== null)
const open = computed(() => (controlled.value ? props.modelValue : inner.value))
const scanning = ref(false)

watch(() => props.modelValue, (v) => { if (v !== null) inner.value = v })
watch(open, (v) => {
  if (!v || !props.scan) return
  scanning.value = false
  requestAnimationFrame(() => {
    scanning.value = true
    setTimeout(() => { scanning.value = false }, props.duration + 520)
  })
})

function toggle() {
  const v = !open.value
  if (!controlled.value) inner.value = v
  emit("update:modelValue", v)
  emit("toggle", v)
}

/* ---- 高度补间 ---- */
function beforeEnter(el) { el.style.height = "0px"; el.style.opacity = "0" }
function enter(el) {
  el.style.transitionDuration = `${props.duration}ms`
  el.style.height = `${el.scrollHeight}px`
  el.style.opacity = "1"
}
function afterEnter(el) { el.style.height = "auto" }
function beforeLeave(el) {
  el.style.transitionDuration = `${props.duration}ms`
  el.style.height = `${el.scrollHeight}px`
  el.style.opacity = "1"
}
function leave(el) {
  void el.offsetHeight
  el.style.height = "0px"
  el.style.opacity = "0"
}
</script>

<template>
  <section
    class="morph"
    :class="{ 'is-open': open, 'is-scanning': scanning }"
    :style="{
      '--m-dur': duration + 'ms',
      '--m-pad-c': compactPadding,
      '--m-pad-e': expandedPadding,
      '--m-rad-c': compactRadius,
      '--m-rad-e': expandedRadius,
    }"
  >
    <!-- 网格底纹：展开时浮现 -->
    <span class="m-grid" aria-hidden="true"></span>
    <!-- 流动描边：展开时巡游 -->
    <span class="m-edge" aria-hidden="true"></span>
    <!-- 一次性扫描光束 -->
    <span v-if="scanning" class="m-beam" aria-hidden="true"></span>
    <!-- 四角定位标：紧凑态收拢在中心，展开态向四角张开 -->
    <span class="m-corner tl" aria-hidden="true"></span>
    <span class="m-corner tr" aria-hidden="true"></span>
    <span class="m-corner bl" aria-hidden="true"></span>
    <span class="m-corner br" aria-hidden="true"></span>

    <!-- 紧凑面 -->
    <div class="m-face">
      <slot name="compact" :open="open" :toggle="toggle" />
    </div>

    <!-- 展开体 -->
    <transition
      name="morph"
      @before-enter="beforeEnter"
      @enter="enter"
      @after-enter="afterEnter"
      @before-leave="beforeLeave"
      @leave="leave"
    >
      <div v-if="open" class="m-body">
        <div class="m-body-inner">
          <slot :open="open" :toggle="toggle" />
        </div>
      </div>
    </transition>
  </section>
</template>

<style scoped>
.morph {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--line);

  /* 变形属性：全部走过渡 */
  padding: var(--m-pad-c);
  border-radius: var(--m-rad-c);
  box-shadow: var(--shadow-1);
  transition:
    padding var(--m-dur) var(--ease-out),
    border-radius var(--m-dur) var(--ease-out),
    background var(--m-dur) var(--ease-out),
    border-color var(--m-dur) var(--ease-out),
    box-shadow var(--m-dur) var(--ease-out),
    transform var(--m-dur) var(--ease-out);
}
.morph.is-open {
  padding: var(--m-pad-e);
  border-radius: var(--m-rad-e);
  border-color: rgba(30, 215, 96, 0.4);
  background: linear-gradient(180deg, var(--surface-3), var(--surface) 46%);
  box-shadow: var(--shadow-2), 0 0 0 1px rgba(30, 215, 96, 0.1);
}

/* 网格底纹 */
.m-grid {
  position: absolute;
  inset: 0;
  z-index: -1;
  border-radius: inherit;
  background-image:
    linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: var(--grid-size) var(--grid-size);
  mask-image: radial-gradient(110% 80% at 50% 0%, #000 15%, transparent 76%);
  -webkit-mask-image: radial-gradient(110% 80% at 50% 0%, #000 15%, transparent 76%);
  opacity: 0;
  transition: opacity var(--m-dur) var(--ease-out);
  pointer-events: none;
}
.morph.is-open .m-grid { opacity: 1; animation: vh-grid-drift 24s linear infinite; }

/* 流动描边 */
.m-edge {
  position: absolute;
  inset: -1px;
  z-index: -1;
  border-radius: inherit;
  padding: 1px;
  background: conic-gradient(
    from var(--edge-angle, 0deg),
    transparent 0deg,
    var(--edge-a) 38deg,
    var(--edge-b) 66deg,
    transparent 124deg,
    transparent 360deg
  );
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask-composite: exclude;
  opacity: 0;
  transition: opacity var(--dur-3) ease;
  pointer-events: none;
}
.morph.is-open .m-edge {
  opacity: 1;
  animation: vh-edge-spin 5s linear infinite;
}

/* 扫描光束 */
.m-beam {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 120px;
  z-index: 1;
  background: linear-gradient(180deg, transparent, rgba(60, 228, 119, 0.09), transparent);
  filter: blur(1px);
  animation: vh-scan-y 0.9s var(--ease-in-out) 1 both;
  pointer-events: none;
}

/* 四角定位标：紧凑态向中心收拢并隐藏，展开态张开 */
.m-corner {
  position: absolute;
  width: 9px;
  height: 9px;
  border: 1px solid var(--accent);
  opacity: 0;
  transition: opacity var(--dur-3) ease, transform var(--m-dur) var(--ease-spring);
  pointer-events: none;
}
.m-corner.tl { top: 10px; left: 10px; border-right: 0; border-bottom: 0; transform: translate(10px, 10px); }
.m-corner.tr { top: 10px; right: 10px; border-left: 0; border-bottom: 0; transform: translate(-10px, 10px); }
.m-corner.bl { bottom: 10px; left: 10px; border-right: 0; border-top: 0; transform: translate(10px, -10px); }
.m-corner.br { bottom: 10px; right: 10px; border-left: 0; border-top: 0; transform: translate(-10px, -10px); }
.morph.is-open .m-corner { opacity: 0.42; transform: translate(0, 0); }

/* 紧凑面 */
.m-face { position: relative; z-index: 2; }

/* 展开体 */
.m-body {
  position: relative;
  z-index: 2;
  overflow: hidden;
  transition-property: height, opacity;
  transition-timing-function: var(--ease-out), ease;
  transition-duration: var(--m-dur), calc(var(--m-dur) * 0.55);
}
.m-body-inner { animation: morph-content-in calc(var(--m-dur) * 1.05) var(--ease-out) both; }
@keyframes morph-content-in {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
