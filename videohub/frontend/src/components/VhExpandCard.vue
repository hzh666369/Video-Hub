<script setup>
/**
 * VhExpandCard · 展开动画卡片（Expandable Card）
 *
 * 与简单的 max-height 过渡不同：这里用 JS 测量真实内容高度，
 * 在 0 ↔ scrollHeight 之间做精确补间，任意内容长度都不会出现
 * 「展开到一半卡住」或「收起时先跳一下」的突兀感。
 *
 * 卡片本体同步发生形态变化：边框点亮、左侧能量条生长、
 * 头部图标上色、角标张开，让「展开」成为一次完整的容器变形。
 */
import { computed, ref, watch } from "vue"
import { PhCaretDown as CaretDown } from "@phosphor-icons/vue"

const props = defineProps({
  /** 受控开关；传 null 则由组件内部自管 */
  modelValue: { type: Boolean, default: null },
  defaultOpen: { type: Boolean, default: false },
  /** 禁用展开 */
  disabled: { type: Boolean, default: false },
  /** 色调：default | gold | danger */
  tone: { type: String, default: "default" },
  /** 隐藏右侧折叠指示箭头（当头部自带指示器时使用） */
  hideCaret: { type: Boolean, default: false },
  /**
   * 内容区内边距。
   * 必须作用在内层 .vhx-body-inner 上：全局是 border-box，
   * 若把 padding 放在被测高 / 被过渡的 .vhx-body 自身，height:0 时 padding 撑着盒子收不到 0，
   * 折叠末端会残留 padding 高度、卸载瞬间被一次性抽走。
   */
  padding: { type: String, default: "0 18px 18px" },
  /** 展开时长（毫秒） */
  duration: { type: Number, default: 400 },
})

const emit = defineEmits(["update:modelValue", "toggle"])

const inner = ref(props.defaultOpen)
const controlled = computed(() => props.modelValue !== null)
const open = computed(() => (controlled.value ? props.modelValue : inner.value))

watch(() => props.modelValue, (v) => { if (v !== null) inner.value = v })

function toggle() {
  if (props.disabled) return
  const v = !open.value
  if (!controlled.value) inner.value = v
  emit("update:modelValue", v)
  emit("toggle", v)
}

/* ---- 高度补间 ----
 * 时长统一由 CSS 的 var(--xr-dur) 驱动（在 .vhx 上下发，.vhx-body 继承），
 * 这里**不要**再写 el.style.transitionDuration：
 * 单值会按规范循环补齐到 `transition-property: height, opacity` 的两项上，
 * 把 opacity 单独配置的 60% 时长一并覆盖成同一时长。
 */
function beforeEnter(el) {
  el.style.height = "0px"
  el.style.opacity = "0"
}
function enter(el) {
  // 读 scrollHeight 会顺带触发一次强制回流。enter 路径上 Vue 不做 forceReflow，
  // 正是这次同步布局读取让 0 → H 成立为一次真实过渡；勿改成缓存值或异步值。
  el.style.height = `${el.scrollHeight}px`
  el.style.opacity = "1"
}
function afterEnter(el) {
  el.style.height = "auto"
}
function beforeLeave(el) {
  el.style.height = `${el.scrollHeight}px`
  el.style.opacity = "1"
}
function leave(el) {
  // Vue 在 onLeave 内部（加完 leave-from 之后、调用本钩子之前）已 forceReflow 过，无需再手动触发。
  el.style.height = "0px"
  el.style.opacity = "0"
}
</script>

<template>
  <section
    class="vhx"
    :class="[`vhx-${tone}`, { 'is-open': open, 'is-disabled': disabled }]"
    :style="{ '--xr-dur': duration + 'ms' }"
  >
    <!-- 左侧能量条：展开时生长 -->
    <span class="vhx-spine" aria-hidden="true"></span>
    <!-- 四角定位标：展开时张开 -->
    <span class="vhx-corner tl" aria-hidden="true"></span>
    <span class="vhx-corner tr" aria-hidden="true"></span>
    <span class="vhx-corner bl" aria-hidden="true"></span>
    <span class="vhx-corner br" aria-hidden="true"></span>

    <component
      :is="disabled ? 'div' : 'button'"
      :type="disabled ? undefined : 'button'"
      class="vhx-head"
      :aria-expanded="open"
      :aria-disabled="disabled || undefined"
      @click="toggle"
    >
      <slot name="head" :open="open" :toggle="toggle" />
      <span v-if="!hideCaret" class="vhx-caret" aria-hidden="true">
        <CaretDown size="15" weight="bold" />
      </span>
    </component>

    <transition
      name="vhx"
      @before-enter="beforeEnter"
      @enter="enter"
      @after-enter="afterEnter"
      @before-leave="beforeLeave"
      @leave="leave"
    >
      <!-- padding 落在内层：被测高的 .vhx-body 自身 padding 必须为 0，height 才能真正收到 0 -->
      <div v-if="open" class="vhx-body">
        <div class="vhx-body-inner" :style="{ padding }">
          <slot :open="open" :close="() => toggle()" />
        </div>
      </div>
    </transition>
  </section>
</template>

<style scoped>
.vhx {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
  transition:
    border-color var(--dur-2) ease,
    background var(--dur-2) ease,
    box-shadow var(--dur-3) var(--ease-out),
    transform var(--dur-3) var(--ease-out);
}
.vhx:hover {
  border-color: var(--line-strong);
  transform: translateY(-1px);
}
.vhx.is-open {
  border-color: rgba(30, 215, 96, 0.42);
  background: linear-gradient(180deg, var(--surface-3), var(--surface) 62%);
  box-shadow: var(--shadow-2), 0 0 0 1px rgba(30, 215, 96, 0.08);
}
.vhx.is-disabled { opacity: 0.6; }

.vhx-gold.is-open {
  border-color: rgba(255, 164, 43, 0.45);
  box-shadow: var(--shadow-2), 0 0 0 1px rgba(255, 164, 43, 0.1);
}
.vhx-danger.is-open {
  border-color: rgba(243, 114, 127, 0.45);
  box-shadow: var(--shadow-2), 0 0 0 1px rgba(243, 114, 127, 0.1);
}

/* 左侧能量条 */
.vhx-spine {
  position: absolute;
  top: 14px;
  left: 0;
  width: 2px;
  height: 0;
  border-radius: var(--r-pill);
  background: linear-gradient(180deg, var(--accent), var(--gold));
  opacity: 0;
  transition: height var(--xr-dur) var(--ease-out), opacity var(--dur-2) ease;
}
.vhx.is-open .vhx-spine { height: calc(100% - 28px); opacity: 0.85; }

/* 四角定位标 */
.vhx-corner {
  position: absolute;
  width: 7px;
  height: 7px;
  border: 1px solid var(--accent);
  opacity: 0;
  transition: opacity var(--dur-3) ease, transform var(--xr-dur) var(--ease-spring);
}
.vhx-corner.tl { top: 7px; left: 7px; border-right: 0; border-bottom: 0; transform: translate(4px, 4px); }
.vhx-corner.tr { top: 7px; right: 7px; border-left: 0; border-bottom: 0; transform: translate(-4px, 4px); }
.vhx-corner.bl { bottom: 7px; left: 7px; border-right: 0; border-top: 0; transform: translate(4px, -4px); }
.vhx-corner.br { bottom: 7px; right: 7px; border-left: 0; border-top: 0; transform: translate(-4px, -4px); }
.vhx.is-open .vhx-corner { opacity: 0.4; transform: translate(0, 0); }

/* 头部 */
.vhx-head {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 15px 18px;
  background: none;
  border: 0;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--dur-1) ease;
}
.vhx-head:hover { background: var(--tint-faint); }
.vhx.is-disabled .vhx-head { cursor: default; }

.vhx-caret {
  margin-left: auto;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: var(--r-sm);
  color: var(--text-3);
  background: var(--bg-raise);
  border: 1px solid var(--line);
  transition: transform var(--xr-dur) var(--ease-spring), color var(--dur-2) ease, border-color var(--dur-2) ease;
}
.vhx.is-open .vhx-caret {
  transform: rotate(180deg);
  color: var(--accent);
  border-color: rgba(30, 215, 96, 0.4);
  background: var(--accent-soft);
}
.vhx-head:hover .vhx-caret { color: var(--text-2); }

/* 展开体：高度由 JS 驱动，opacity 同步淡入 */
.vhx-body {
  overflow: hidden;
  transition-property: height, opacity;
  transition-timing-function: var(--ease-out), ease;
  transition-duration: var(--xr-dur), calc(var(--xr-dur) * 0.6);
}
.vhx-body-inner { animation: vhx-content-in calc(var(--xr-dur) * 1.1) var(--ease-out) both; }
@keyframes vhx-content-in {
  from { opacity: 0; transform: translateY(-6px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
