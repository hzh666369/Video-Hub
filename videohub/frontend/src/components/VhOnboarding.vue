<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import {
  PhArrowLeft as ArrowLeft,
  PhArrowRight as ArrowRight,
  PhX as X,
} from "@phosphor-icons/vue"

/**
 * 聚光灯式新手引导：
 * - steps: [{ title, body, selector?, route?, link? }]
 *   selector 缺失或元素不可见时卡片居中展示；
 *   route 声明步骤目标所在页面，不在该页面时先跳转过去再高亮
 * - v-model 控制开关；结束时 emit("finish")，由父组件决定是否标记完成
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  steps: { type: Array, required: true },
})
const emit = defineEmits(["update:modelValue", "finish"])

const router = useRouter()

const index = ref(0)
const target = ref(null) // { top, left, width, height }
const cardRef = ref(null)
const cardStyle = ref({})

const step = computed(() => props.steps[index.value] || null)
const total = computed(() => props.steps.length)
const isFirst = computed(() => index.value === 0)
const isLast = computed(() => index.value === total.value - 1)

let ro = null

function place() {
  const s = step.value
  if (!s || !s.selector) { target.value = null; return positionCard(null) }
  const el = document.querySelector(s.selector)
  if (!el) { target.value = null; return positionCard(null) }
  const r = el.getBoundingClientRect()
  if (!r.width && !r.height) { target.value = null; return positionCard(null) }
  const pad = 8
  target.value = {
    top: r.top - pad,
    left: r.left - pad,
    width: r.width + pad * 2,
    height: r.height + pad * 2,
  }
  positionCard(target.value)
}

function positionCard(t) {
  nextTick(() => {
    const card = cardRef.value
    const cw = card ? card.offsetWidth : 300
    const ch = card ? card.offsetHeight : 190
    const vw = window.innerWidth
    const vh = window.innerHeight
    if (!t) {
      cardStyle.value = { top: "50%", left: "50%", transform: "translate(-50%, -50%)" }
      return
    }
    const left = Math.min(Math.max(t.left + t.width / 2 - cw / 2, 16), vw - cw - 16)
    // 优先放目标下方，放不下则放上方
    let top = t.top + t.height + 14
    if (top + ch > vh - 16) top = t.top - ch - 14
    if (top < 16) top = Math.max(16, Math.min(vh - ch - 16, t.top + t.height / 2 - ch / 2))
    cardStyle.value = { top: `${top}px`, left: `${left}px`, transform: "none" }
  })
}

function recompute() {
  place()
}

// 跨页跳转时页面带 out-in 过渡，元素挂载后位置仍在缓动，等它稳定下来再测量
async function waitStable(selector, timeout = 2000) {
  const start = Date.now()
  let last = null
  while (Date.now() - start < timeout) {
    const el = document.querySelector(selector)
    const r = el ? el.getBoundingClientRect() : null
    if (
      r && last &&
      Math.abs(r.top - last.top) < 1 &&
      Math.abs(r.left - last.left) < 1 &&
      Math.abs(r.width - last.width) < 1
    ) return
    last = r
    await new Promise((resolve) => setTimeout(resolve, 80))
  }
}

// 进入某一步：必要时先跳到步骤声明的页面，元素就位后重新测量高亮
async function prepareStep() {
  const s = step.value
  if (!s) return
  if (s.route && router.currentRoute.value.path !== s.route) {
    await router.push(s.route).catch(() => {})
  }
  if (!s.selector) return
  recompute() // 元素已在当前页面时立即高亮
  await waitStable(s.selector)
  // 等待期间用户可能已切到其他步骤或关掉引导，过期任务不回写
  if (step.value === s && props.modelValue) recompute()
}

function enterStep() {
  nextTick(() => {
    recompute()
    prepareStep()
  })
}

watch(() => props.modelValue, (open) => {
  if (open) {
    index.value = 0
    enterStep()
  }
})

watch(index, enterStep)

function go(delta) {
  if (isLast.value && delta > 0) { close(); return }
  index.value = Math.min(Math.max(index.value + delta, 0), total.value - 1)
}

function close() {
  emit("update:modelValue", false)
  emit("finish")
}

function onKey(e) {
  if (!props.modelValue) return
  if (e.key === "Escape") close()
  else if (e.key === "ArrowRight") go(1)
  else if (e.key === "ArrowLeft") go(-1)
}

onMounted(() => {
  window.addEventListener("resize", recompute)
  window.addEventListener("scroll", recompute, true)
  document.addEventListener("keydown", onKey)
  ro = new ResizeObserver(recompute)
  if (cardRef.value) ro.observe(cardRef.value)
})

onBeforeUnmount(() => {
  window.removeEventListener("resize", recompute)
  window.removeEventListener("scroll", recompute, true)
  document.removeEventListener("keydown", onKey)
  ro?.disconnect()
})
</script>

<template>
  <teleport to="body">
    <transition name="tour-fade">
      <div v-if="modelValue && step" class="tour" role="dialog" aria-label="新手引导">
        <!-- 聚光灯挖孔：巨型 box-shadow 把四周压暗 -->
        <div
          v-if="target"
          class="tour-hole"
          :style="{
            top: target.top + 'px',
            left: target.left + 'px',
            width: target.width + 'px',
            height: target.height + 'px',
          }"
        ></div>

        <section ref="cardRef" class="tour-card" :style="cardStyle">
          <header class="tour-head">
            <span class="tour-step">{{ index + 1 }} / {{ total }}</span>
            <button class="tour-skip" aria-label="跳过引导" @click="close">
              跳过
              <X size="12" weight="bold" />
            </button>
          </header>
          <h3 class="tour-title">{{ step.title }}</h3>
          <p class="tour-body">{{ step.body }}</p>
          <router-link v-if="step.link" :to="step.link" class="tour-link" @click="close">
            查看完整免责声明 →
          </router-link>
          <footer class="tour-foot">
            <div class="tour-dots" aria-hidden="true">
              <span
                v-for="(_, i) in steps"
                :key="i"
                class="dot"
                :class="{ on: i === index }"
              ></span>
            </div>
            <div class="tour-btns">
              <button v-if="!isFirst" class="tour-btn ghost" @click="go(-1)">
                <ArrowLeft size="13" weight="bold" />
                上一步
              </button>
              <button class="tour-btn primary" @click="go(1)">
                {{ isLast ? "完成" : "下一步" }}
                <ArrowRight v-if="!isLast" size="13" weight="bold" />
              </button>
            </div>
          </footer>
        </section>
      </div>
    </transition>
  </teleport>
</template>

<style scoped>
.tour {
  position: fixed;
  inset: 0;
  z-index: 120;
}

.tour-hole {
  position: fixed;
  border-radius: 14px;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.65), 0 0 0 2px rgba(255, 255, 255, 0.7);
  transition: top 0.3s var(--ease-out), left 0.3s var(--ease-out),
    width 0.3s var(--ease-out), height 0.3s var(--ease-out);
  pointer-events: none;
}

.tour-card {
  position: fixed;
  width: min(320px, calc(100vw - 32px));
  padding: 16px 18px 14px;
  border-radius: 16px;
  background: var(--glass-bg);
  backdrop-filter: blur(16px) saturate(1.3);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  border: 1px solid var(--glass-line);
  box-shadow: var(--shadow-3);
  transition: top 0.3s var(--ease-out), left 0.3s var(--ease-out);
}

.tour-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.tour-step {
  padding: 2px 10px;
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11.5px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.tour-skip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-3);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.16s ease, background 0.16s ease;
}
.tour-skip:hover { color: var(--text-1); background: var(--surface); }

.tour-title {
  margin: 0 0 8px;
  font-size: 16.5px;
  font-weight: 700;
  color: var(--text-1);
}
.tour-body {
  margin: 0;
  color: var(--text-2);
  font-size: 13.5px;
  line-height: 1.65;
}
.tour-link {
  display: inline-block;
  margin-top: 8px;
  color: var(--accent);
  font-size: 12.5px;
  text-decoration: none;
}
.tour-link:hover { text-decoration: underline; }

.tour-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
}
.tour-dots { display: flex; gap: 6px; }
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--line-strong);
  transition: background 0.2s ease, transform 0.2s ease;
}
.dot.on { background: var(--accent); transform: scale(1.25); }

.tour-btns { display: flex; gap: 8px; }
.tour-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 16px;
  border-radius: var(--r-pill);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.03em;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease, transform 0.12s ease;
}
.tour-btn:active { transform: scale(0.97); }
.tour-btn.ghost {
  border: 1px solid var(--line-strong);
  background: transparent;
  color: var(--text-2);
}
.tour-btn.ghost:hover { border-color: var(--text-1); color: var(--text-1); }
.tour-btn.primary {
  border: 1px solid transparent;
  background: var(--accent-strong);
  color: #000;
}
.tour-btn.primary:hover { background: var(--accent-hover); }

.tour-fade-enter-active,
.tour-fade-leave-active { transition: opacity 0.22s ease; }
.tour-fade-enter-from,
.tour-fade-leave-to { opacity: 0; }
</style>
