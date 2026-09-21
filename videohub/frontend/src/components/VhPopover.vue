<script setup>
/**
 * VhPopover · 弹层组件
 *
 * 全站统一浮层：Teleport 到 body、自动翻转避让视口边缘、
 * 支持 click / hover 两种触发、点击外部与 ESC 关闭、
 * 带指向箭头与方向感知的缩放入场动画。
 *
 * 无障碍：触发元素带 aria-haspopup / aria-expanded，
 * 弹层 role=dialog，ESC 关闭后焦点回到触发元素。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"

const props = defineProps({
  /** 方位：top | bottom | left | right，可加 -start / -end 对齐 */
  placement: { type: String, default: "bottom" },
  /** 触发方式：click | hover | manual（manual 需外部用 v-model 控制） */
  trigger: { type: String, default: "click" },
  /** 与触发元素的间距 */
  offset: { type: Number, default: 10 },
  /** 弹层宽度，数字按像素 */
  width: { type: [Number, String], default: null },
  /** 弹层标题（可留空，用 #content 完全自定义） */
  title: { type: String, default: "" },
  /** 是否显示指向箭头 */
  arrow: { type: Boolean, default: true },
  /** 内容区内边距 */
  padding: { type: String, default: "14px 16px" },
  /** 弹层语义角色 */
  role: { type: String, default: "dialog" },
  /** v-model 控制开关（传入即受控） */
  modelValue: { type: Boolean, default: null },
  /** hover 关闭延迟（ms），避免鼠标穿过间隙时闪烁 */
  hoverCloseDelay: { type: Number, default: 160 },
  /** 禁用（悬停 / 点击均不展开） */
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(["update:modelValue", "open", "close"])

const anchorRef = ref(null)
const panelRef = ref(null)
const inner = ref(false)
const side = ref(props.placement.split("-")[0])
const ready = ref(false)
const arrowOffset = ref(0)

const pos = ref({ top: 0, left: 0 })
let hoverTimer = null

const controlled = computed(() => props.modelValue !== null)
const open = computed(() => (controlled.value ? props.modelValue : inner.value))

watch(
  () => props.modelValue,
  (v) => { inner.value = !!v },
)

function getAnchor() {
  const host = anchorRef.value
  if (!host) return null
  const first = host.firstElementChild
  const el = first || host
  if (!el.getClientRects().length) return host.parentElement || host
  return el
}

const clamp = (v, min, max) => Math.min(Math.max(v, min), max)

async function place() {
  ready.value = false
  await nextTick()
  const anchor = getAnchor()
  const panel = panelRef.value
  if (!anchor || !panel) return

  const tr = anchor.getBoundingClientRect()
  const pw = panel.offsetWidth
  const ph = panel.offsetHeight
  const gap = props.offset
  const vw = window.innerWidth
  const vh = window.innerHeight
  const pad = 8

  const [want, align = "center"] = props.placement.split("-")

  // 空间不足时自动翻转
  let s = want
  if (want === "bottom" && tr.bottom + gap + ph > vh - pad && tr.top - gap - ph > pad) s = "top"
  else if (want === "top" && tr.top - gap - ph < pad && tr.bottom + gap + ph < vh - pad) s = "bottom"
  else if (want === "right" && tr.right + gap + pw > vw - pad && tr.left - gap - pw > pad) s = "left"
  else if (want === "left" && tr.left - gap - pw < pad && tr.right + gap + pw < vw - pad) s = "right"
  side.value = s

  let top = 0
  let left = 0

  if (s === "bottom") top = tr.bottom + gap
  else if (s === "top") top = tr.top - gap - ph
  else if (s === "right") left = tr.right + gap
  else left = tr.left - gap - pw

  if (s === "bottom" || s === "top") {
    if (align === "start") left = tr.left
    else if (align === "end") left = tr.right - pw
    else left = tr.left + tr.width / 2 - pw / 2
    left = clamp(left, pad, Math.max(pad, vw - pw - pad))
    arrowOffset.value = clamp(tr.left + tr.width / 2 - left, 14, Math.max(14, pw - 14))
  } else {
    if (align === "start") top = tr.top
    else if (align === "end") top = tr.bottom - ph
    else top = tr.top + tr.height / 2 - ph / 2
    top = clamp(top, pad, Math.max(pad, vh - ph - pad))
    arrowOffset.value = clamp(tr.top + tr.height / 2 - top, 14, Math.max(14, ph - 14))
  }

  pos.value = { top: Math.round(top), left: Math.round(left) }
  requestAnimationFrame(() => { ready.value = true })
}

function setOpen(v) {
  if (props.disabled && v) return
  if (controlled.value) emit("update:modelValue", v)
  else inner.value = v
  v ? emit("open") : emit("close")
}

function toggle() {
  setOpen(!open.value)
}

function onMouseEnter() {
  if (props.trigger !== "hover" || props.disabled) return
  clearTimeout(hoverTimer)
  setOpen(true)
}
function onMouseLeave() {
  if (props.trigger !== "hover") return
  clearTimeout(hoverTimer)
  hoverTimer = setTimeout(() => setOpen(false), props.hoverCloseDelay)
}

function onDocPointer(e) {
  if (!open.value) return
  const anchor = getAnchor()
  if (anchor && anchor.contains(e.target)) return
  if (panelRef.value && panelRef.value.contains(e.target)) return
  setOpen(false)
}

function onKeydown(e) {
  if (!open.value) return
  if (e.key === "Escape") {
    e.stopPropagation()
    setOpen(false)
    const anchor = getAnchor()
    if (anchor && typeof anchor.focus === "function") anchor.focus()
  }
}

function onReposition() {
  if (open.value) place()
}

let bound = false
function bind() {
  if (bound) return
  bound = true
  document.addEventListener("pointerdown", onDocPointer, true)
  document.addEventListener("keydown", onKeydown, true)
  window.addEventListener("scroll", onReposition, true)
  window.addEventListener("resize", onReposition)
}
function unbind() {
  if (!bound) return
  bound = false
  document.removeEventListener("pointerdown", onDocPointer, true)
  document.removeEventListener("keydown", onKeydown, true)
  window.removeEventListener("scroll", onReposition, true)
  window.removeEventListener("resize", onReposition)
}

watch(open, (v) => {
  if (v) { bind(); place() }
  // 关闭时不重置 ready：内联/类样式一旦把 opacity 钉成 0，
  // 会压过 <transition> 的 leave-to 类，导致淡出动画失效（表现为瞬间消失的卡顿）
  else { unbind() }
})

onBeforeUnmount(() => {
  clearTimeout(hoverTimer)
  unbind()
})

const panelStyle = computed(() => ({
  top: `${pos.value.top}px`,
  left: `${pos.value.left}px`,
  width: props.width ? (typeof props.width === "number" ? `${props.width}px` : props.width) : null,
}))

const panelClass = computed(() => [
  `is-${side.value}`,
  `place-${props.placement.split("-")[0]}`,
  { "is-ready": ready.value },
])
</script>

<template>
  <span
    ref="anchorRef"
    class="vh-pop-anchor"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
  >
    <span
      class="vh-pop-trigger"
      :aria-haspopup="role === 'tooltip' ? undefined : 'dialog'"
      :aria-expanded="open"
      @click="trigger === 'click' ? toggle() : null"
    >
      <slot :open="open" :toggle="toggle" />
    </span>
  </span>

  <Teleport to="body">
    <transition :name="`vh-pop-${side}`">
      <div
        v-if="open"
        ref="panelRef"
        class="vh-pop"
        :class="panelClass"
        :style="panelStyle"
        :role="role"
        tabindex="-1"
        @mouseenter="onMouseEnter"
        @mouseleave="onMouseLeave"
      >
        <span v-if="arrow" class="vh-pop-arrow" :style="{ '--a': arrowOffset + 'px' }" aria-hidden="true" />

        <header v-if="title" class="vh-pop-head">
          <span class="vh-pop-title">{{ title }}</span>
          <slot name="extra" />
        </header>

        <div class="vh-pop-body" :style="{ padding }">
          <slot name="content" :close="() => setOpen(false)">
            <slot name="default" />
          </slot>
        </div>

        <footer v-if="$slots.footer" class="vh-pop-foot">
          <slot name="footer" :close="() => setOpen(false)" />
        </footer>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
/* display:contents 让包裹层不产生盒子，不干扰触发元素原有布局 */
.vh-pop-anchor { display: contents; }
.vh-pop-trigger { display: contents; }
</style>

<style>
/* 弹层样式非 scoped：内容被 Teleport 到 body，需全局生效 */
.vh-pop {
  position: fixed;
  z-index: 300;
  min-width: 180px;
  max-width: min(340px, calc(100vw - 24px));
  border-radius: var(--r-md);
  background: var(--popover-bg);
  border: 1px solid var(--glass-line);
  box-shadow: var(--shadow-3);
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.6;
  transition: opacity 0.18s var(--ease-out), transform 0.22s var(--ease-spring);
}
/* 定位完成前先隐藏，避免面板从 (0,0) 闪现；
 * 就绪后不再命中此规则，透明度交还给 enter/leave 过渡类驱动 */
.vh-pop:not(.is-ready) { opacity: 0; }
/* 顶部一道极细高光，轻奢玻璃感 */
.vh-pop::before {
  content: "";
  position: absolute;
  top: 0;
  left: 14%;
  right: 14%;
  height: 1px;
  border-radius: var(--r-pill);
  background: linear-gradient(90deg, transparent, var(--edge-a), var(--edge-b), transparent);
  pointer-events: none;
}

.vh-pop-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 14px 8px;
  border-bottom: 1px solid var(--line);
}
.vh-pop-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-1);
  letter-spacing: 0.01em;
}
.vh-pop-body { font-size: 13px; color: var(--text-2); }
.vh-pop-foot {
  padding: 10px 14px 12px;
  border-top: 1px solid var(--line);
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 箭头：半透菱形，贴边旋转 45°，--a 为沿边偏移 */
.vh-pop-arrow {
  position: absolute;
  width: 10px;
  height: 10px;
  background: var(--popover-solid);
  border: 1px solid var(--glass-line);
  transform: rotate(45deg);
  pointer-events: none;
}
.vh-pop.is-bottom .vh-pop-arrow { top: -6px; left: var(--a); margin-left: -5px; border-right: 0; border-bottom: 0; }
.vh-pop.is-top .vh-pop-arrow { bottom: -6px; left: var(--a); margin-left: -5px; border-left: 0; border-top: 0; }
.vh-pop.is-right .vh-pop-arrow { left: -6px; top: var(--a); margin-top: -5px; border-right: 0; border-top: 0; }
.vh-pop.is-left .vh-pop-arrow { right: -6px; top: var(--a); margin-top: -5px; border-left: 0; border-bottom: 0; }

/* 方向感知入场：从触发点方向弹出 */
.vh-pop-bottom-enter-from,
.vh-pop-bottom-leave-to { opacity: 0; transform: translateY(-6px) scale(0.96); }
.vh-pop-top-enter-from,
.vh-pop-top-leave-to { opacity: 0; transform: translateY(6px) scale(0.96); }
.vh-pop-right-enter-from,
.vh-pop-right-leave-to { opacity: 0; transform: translateX(-6px) scale(0.96); }
.vh-pop-left-enter-from,
.vh-pop-left-leave-to { opacity: 0; transform: translateX(6px) scale(0.96); }

.vh-pop-bottom-enter-active,
.vh-pop-bottom-leave-active,
.vh-pop-top-enter-active,
.vh-pop-top-leave-active,
.vh-pop-right-enter-active,
.vh-pop-right-leave-active,
.vh-pop-left-enter-active,
.vh-pop-left-leave-active {
  transition: opacity 0.18s var(--ease-out), transform 0.24s var(--ease-spring);
}
</style>
