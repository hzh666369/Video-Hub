<script setup>
/**
 * DashFeed · 实时动态 · 数据流面板（LIVE + 自动滚动开关）
 *
 * 三条交互规则：
 *  1. 默认自动轮播：每 INTERVAL 前进一行；滚过一整份时先归位再前进，
 *     因为副本内容完全相同，回绕时视觉无跳动（无缝循环）。
 *  2. 滚轮 / 触摸 / 键盘随时可接管：一旦接管就停表，静置 RESUME_MS 后自动恢复。
 *  3. 标题栏「自动滚动」开关可显式暂停，暂停期间任何数据刷新都不重启轮播。
 *
 * 无缝回绕的实现要点（踩过的坑）：
 *  · 必须渲染多份副本，且**一份的长度 ≥ 视口高度**，否则回绕时会露出空白；
 *    副本数按 ceil(视口高 / 一份高) + 1 动态算。
 *  · 归位判断只能比 `scrollTop >= 一份的高度`，**不能**按「接近底部」判断 ——
 *    视口高小于一份长时，接近底部的阈值会立刻命中，导致持续跳顶。
 *  · 行高必须与 CSS 里 .feed .it 的 height 严格一致，滚动步长按它算。
 *
 * 行结构（对齐参考稿）：时间轴点 · 时间 · 事件图标 · 事件类型 · 用户 · 来源 · 状态徽章。
 * 状态徽章按动作映射：解析=成功（绿）/ 注册=注册（蓝）/ 登录=登录（蓝）/ 访问=访问（黄）。
 * 日志只记录已发生的事件，因此没有「进行中 / 失败」态 —— 不虚构状态。
 *
 * v8 HUD 视觉层（同 DashPlatforms 设计语言）：行间极细分割线、事件图标受光内环、
 * 时间戳染电光蓝、LIVE 呼吸灯扩散环（reduced-motion 静止）。交互与滚动逻辑不变。
 *
 * 无障碍：副本行对辅助技术隐藏（同一份内容只播报一次）；滚动区可聚焦，
 * 键盘滚动的接管行为与鼠标滚轮一致。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { PhCheckCircle, PhGlobe, PhKey, PhPulse, PhUserPlus } from "@phosphor-icons/vue"

/* 必须与 <style> 里 .feed .it 的 height 保持一致 */
const FEED_ROW = 48
/* 自动轮播步进间隔 */
const INTERVAL = 3600
/* 滚轮接管后多久恢复轮播 */
const RESUME_MS = 8000

/* 动作 → 行内展示（事件名 / 徽章文案 / 图标 / 色调）。静态常量，不依赖接口返回。 */
const EVENTS = {
  parse: { name: "解析完成", badge: "成功", icon: PhCheckCircle, tone: "aqua" },
  register: { name: "新用户注册", badge: "注册", icon: PhUserPlus, tone: "azure" },
  login: { name: "用户登录", badge: "登录", icon: PhKey, tone: "azure" },
  visit: { name: "页面访问", badge: "访问", icon: PhGlobe, tone: "amber" },
}

/* 平台 key → 展示名。键来自后端 platform.py::detect，源码内静态常量。 */
const PLATFORM_NAMES = {
  bilibili: "哔哩哔哩", tencent: "腾讯视频", youku: "优酷", iqiyi: "爱奇艺",
  mgtv: "芒果TV", douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书",
  unknown: "未知来源", other: "其他",
}

const props = defineProps({
  /** 动态条目：{ id, action, username, detail, created_at } */
  items: { type: Array, default: () => [] },
})

const scrollEl = ref(null)
const copies = ref(2)
const paused = ref(false)

const REDUCED =
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches

/** 一份列表的总高，也是回绕点 */
const loopH = computed(() => props.items.length * FEED_ROW)

/** 渲染多份副本用于无缝回绕；第 2 份起对辅助技术隐藏 */
const rows = computed(() => {
  const base = props.items
  if (!base.length) return []
  const out = []
  for (let c = 0; c < copies.value; c++) {
    for (let i = 0; i < base.length; i++) {
      out.push({ item: base[i], key: `${c}:${base[i].id ?? i}`, dup: c > 0 })
    }
  }
  return out
})

/** 来源列：解析 → 平台名；页面访问 → 页面名；登录/注册无来源 */
function sourceOf(item) {
  const detail = (item.detail || "").trim()
  if (!detail) return "-"
  if (item.action === "parse") {
    const key = detail.split(" | ")[0].trim()
    return PLATFORM_NAMES[key] || key || "-"
  }
  return detail
}

let autoTimer = null
let resumeTimer = null
let ro = null
let rt = null

/** 按视口高度算需要几份副本（一份必须盖满视口，回绕才不露白） */
function measure() {
  const el = scrollEl.value
  const setH = loopH.value
  if (!el || !setH) return
  copies.value = Math.max(2, Math.ceil((el.clientHeight || 0) / setH) + 1)
}

function step() {
  const el = scrollEl.value
  if (!el || paused.value || !loopH.value) return
  /* 已滚过一整份时先归位（内容完全相同，视觉无变化），保证无限循环 */
  if (el.scrollTop >= loopH.value) el.scrollTop -= loopH.value
  el.scrollTo({
    top: el.scrollTop + FEED_ROW,
    behavior: REDUCED ? "auto" : "smooth",
  })
}

function stopTimer() {
  if (autoTimer) {
    clearInterval(autoTimer)
    autoTimer = null
  }
}

function startTimer() {
  stopTimer()
  const el = scrollEl.value
  if (!el || paused.value) return
  /* 内容不足一行时没有可轮播的空间，直接不启动 */
  if (el.scrollHeight - el.clientHeight < FEED_ROW) return
  autoTimer = setInterval(step, INTERVAL)
}

/** 滚轮 / 触摸 / 键盘接管：停表 → 静置 RESUME_MS 后自动恢复 */
function handOver() {
  if (paused.value) return
  if (resumeTimer) clearTimeout(resumeTimer)
  stopTimer()
  resumeTimer = setTimeout(startTimer, RESUME_MS)
}

function toggle() {
  paused.value = !paused.value
  if (paused.value) {
    stopTimer()
    if (resumeTimer) {
      clearTimeout(resumeTimer)
      resumeTimer = null
    }
  } else {
    startTimer()
  }
}

/** 标签页切到后台时停表：既省电，也避免回来后一次性跳一大截 */
function onVisibility() {
  if (document.hidden) {
    stopTimer()
    if (resumeTimer) {
      clearTimeout(resumeTimer)
      resumeTimer = null
    }
  } else if (!paused.value) {
    startTimer()
  }
}

/** 尺寸变化 → 副本数可能不再够用，重算并保住当前滚动位置 */
function onResize() {
  clearTimeout(rt)
  rt = setTimeout(async () => {
    const el = scrollEl.value
    const keep = el && loopH.value ? el.scrollTop % loopH.value : 0
    measure()
    await nextTick()
    if (el) el.scrollTop = keep
    startTimer()
  }, 140)
}

/* 轮询刷新（60s）会换掉整个数组：保位置 + 重启轮播 */
watch(
  () => props.items,
  async () => {
    const el = scrollEl.value
    const keep = el && loopH.value ? el.scrollTop % loopH.value : 0
    measure()
    await nextTick()
    if (el) el.scrollTop = keep
    if (!paused.value) startTimer()
  },
)

onMounted(async () => {
  await nextTick()   // 先保证首屏 DOM 渲染完成，measure 才拿得到真实容器高
  measure()
  startTimer()
  window.addEventListener("resize", onResize)
  document.addEventListener("visibilitychange", onVisibility)
  if ("ResizeObserver" in window && scrollEl.value) {
    ro = new ResizeObserver(onResize)
    ro.observe(scrollEl.value)
  }
})

onBeforeUnmount(() => {
  stopTimer()
  if (resumeTimer) {
    clearTimeout(resumeTimer)
    resumeTimer = null
  }
  clearTimeout(rt)
  if (ro) {
    ro.disconnect()
    ro = null
  }
  window.removeEventListener("resize", onResize)
  document.removeEventListener("visibilitychange", onVisibility)
})

function fmtTime(iso) {
  return iso ? iso.slice(11, 16) : ""
}
</script>

<template>
  <div class="glassbox panel feed-panel">
    <div class="in">
      <div class="p-head">
        <h2 class="p-title">
          <i class="p-ic aqua" aria-hidden="true"><PhPulse :size="14" weight="bold" /></i>
          实时动态
          <span class="live-pill"><i aria-hidden="true"></i>LIVE</span>
        </h2>
        <span class="sw-row">
          自动滚动
          <button
            class="sw"
            :class="{ on: !paused }"
            type="button"
            role="switch"
            :aria-checked="!paused"
            aria-label="自动滚动"
            @click="toggle"
          >
            <i aria-hidden="true"></i>
          </button>
        </span>
      </div>

      <div
        ref="scrollEl"
        class="feed-scroll"
        tabindex="0"
        role="region"
        aria-label="实时动态列表"
        @wheel.passive="handOver"
        @touchstart.passive="handOver"
        @keydown="handOver"
      >
        <div class="feed">
          <p v-if="!rows.length" class="empty">暂无动态</p>
          <div
            v-for="r in rows"
            :key="r.key"
            class="it"
            :class="`a-${r.item.action}`"
            :aria-hidden="r.dup ? 'true' : null"
          >
            <span class="t">{{ fmtTime(r.item.created_at) }}</span>
            <template v-if="EVENTS[r.item.action]">
              <i class="ev-ic" aria-hidden="true">
                <component :is="EVENTS[r.item.action].icon" :size="11" weight="bold" />
              </i>
              <span class="ev-name">{{ EVENTS[r.item.action].name }}</span>
              <span class="nm">{{ r.item.username }}</span>
              <span class="src">{{ sourceOf(r.item) }}</span>
              <span class="spacer" aria-hidden="true"></span>
              <span
                class="badge"
                :class="EVENTS[r.item.action].tone === 'aqua' ? 'ok' : EVENTS[r.item.action].tone === 'amber' ? 'warn' : 'info'"
              >
                {{ EVENTS[r.item.action].badge }}
              </span>
            </template>
            <template v-else>
              <i class="ev-ic" aria-hidden="true"><PhGlobe :size="11" weight="bold" /></i>
              <span class="ev-name">{{ r.item.action }}</span>
              <span class="nm">{{ r.item.username }}</span>
              <span class="src">{{ sourceOf(r.item) }}</span>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 玻璃卡片 / 面板骨架 / 标题栏 / 徽章 / 开关等原语在 src/styles/dashboard.css（全局、.board 作用域） */
.feed-panel {
  --pad-panel: 13px 14px 10px;
  min-height: 0;
}

/* ---- 滚动容器 ---- */
.feed-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--bd-ln-hi) transparent;
  /* 底部渐隐，暗示「下面还有」 */
  mask-image: linear-gradient(180deg, #000 0, #000 90%, transparent 100%);
  -webkit-mask-image: linear-gradient(180deg, #000 0, #000 90%, transparent 100%);
}
.feed-scroll::-webkit-scrollbar {
  width: 5px;
}
.feed-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.feed-scroll::-webkit-scrollbar-thumb {
  background: var(--bd-ln-hi);
  border-radius: 3px;
}
.feed-scroll::-webkit-scrollbar-thumb:hover {
  background: var(--bd-azure);
}

/* ---- 时间轴 ---- */
.feed {
  position: relative;
  padding-left: 16px;
}
.feed::before {
  content: "";
  position: absolute;
  left: 3px;
  top: 0;
  bottom: 0;
  width: 1px;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--bd-azure) 70%, transparent),
    color-mix(in srgb, var(--bd-azure) 28%, transparent) 55%,
    color-mix(in srgb, var(--bd-azure) 12%, transparent)
  );
}

/* 行高必须与 JS 的 FEED_ROW 一致（滚动步长按行高计算） */
.feed .it {
  position: relative;
  height: 48px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 9px 0 6px;
  border-radius: 8px;
  font-size: 11.5px;
  transition: background 0.16s ease;
}
.feed .it:hover {
  background: var(--bd-hover);
}
/* v8 列表语言：行间极细分割线（副本内容与首份一致，回绕处同样成立） */
.feed .it + .it {
  border-top: 1px solid color-mix(in srgb, var(--bd-ln) 45%, transparent);
}
/* 轴上的状态灯：按事件类型分色 —— 解析绿 / 登录·注册蓝 / 访问黄 */
.feed .it::before {
  content: "";
  position: absolute;
  left: -16px;
  top: 50%;
  transform: translateY(-50%);
  width: 7px;
  height: 7px;
  box-sizing: border-box;
  border-radius: 50%;
  background: var(--bd-solid);
  border: 1.5px solid var(--bd-t3);
}
.feed .it.a-parse::before {
  border-color: var(--bd-aqua);
  background: var(--bd-aqua);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--bd-aqua) 16%, transparent), 0 0 8px var(--bd-aqua);
}
.feed .it.a-login::before,
.feed .it.a-register::before {
  border-color: var(--bd-azure);
  background: var(--bd-azure);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--bd-azure) 15%, transparent), 0 0 8px var(--bd-azure);
}
.feed .it.a-visit::before {
  border-color: var(--bd-amber);
  background: var(--bd-amber);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--bd-amber) 14%, transparent), 0 0 8px var(--bd-amber);
}

.feed .t {
  flex-shrink: 0;
  width: 36px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  /* v8：时间戳染电光蓝，与座舱信号色一致 */
  color: color-mix(in srgb, var(--bd-azure) 62%, var(--bd-t3));
  font-variant-numeric: tabular-nums;
}
.ev-ic {
  display: inline-grid;
  place-items: center;
  width: 19px;
  height: 19px;
  flex-shrink: 0;
  border-radius: 6px;
  background: var(--bd-fill-soft);
  color: var(--bd-t2);
  /* v8：事件图标芯片加全周受光内环（同 p-ic 玻璃芯片语言） */
  box-shadow: inset 0 0 0 1px var(--bd-ln);
}
.feed .it.a-parse .ev-ic {
  background: color-mix(in srgb, var(--bd-aqua) 14%, transparent);
  color: var(--bd-aqua);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--bd-aqua) 34%, transparent);
}
.feed .it.a-login .ev-ic,
.feed .it.a-register .ev-ic {
  background: color-mix(in srgb, var(--bd-azure) 14%, transparent);
  color: var(--bd-azure);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--bd-azure) 34%, transparent);
}
.feed .it.a-visit .ev-ic {
  background: color-mix(in srgb, var(--bd-amber) 14%, transparent);
  color: var(--bd-amber);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--bd-amber) 34%, transparent);
}
.ev-name {
  flex-shrink: 0;
  width: 62px;
  color: var(--bd-t1);
  font-weight: 550;
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.feed .nm {
  flex-shrink: 0;
  width: 64px;
  color: var(--bd-t2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
}
.feed .src {
  flex-shrink: 0;
  width: 84px;
  color: var(--bd-t3);
  font-size: 10.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
}
/* 徽章贴右：来源列与徽章之间用弹性 spacer 撑开 */
.feed .spacer {
  flex: 1;
  min-width: 0;
}

/* v8：LIVE 呼吸灯加外圈扩散环（同 KPI 指示灯 / 系统状态呼吸灯语言） */
.live-pill i {
  position: relative;
}
@media (prefers-reduced-motion: no-preference) {
  .live-pill i::after {
    content: "";
    position: absolute;
    inset: -4px;
    border-radius: 50%;
    border: 1px solid color-mix(in srgb, var(--bd-ok) 65%, transparent);
    animation: fd-ring 2.2s ease-out infinite;
  }
}
@keyframes fd-ring {
  0% { transform: scale(0.55); opacity: 0.95; }
  70%, 100% { transform: scale(1.55); opacity: 0; }
}
</style>
