<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import {
  PhLinkSimple as LinkSimple,
  PhCrownSimple as CrownSimple,
  PhWarningCircle as WarningCircle,
  PhArrowRight as ArrowRight,
  PhArrowDown as ArrowDown,
  PhX as X,
  PhQuestion as Question,
  PhInfo as Info,
  PhSparkle as Sparkle,
  PhLightning as Lightning,
  PhFilmStrip as FilmStrip,
  PhCubeTransparent as CubeTransparent,
  PhPlugsConnected as PlugsConnected,
  PhAtom as Atom,
  PhPlay as Play,
  PhCheck as Check,
  PhClipboardText as ClipboardText,
  PhArrowSquareOut as ArrowSquareOut,
} from "@phosphor-icons/vue"
import api from "../api/client"
import { useAuthStore } from "../stores/auth"
import VhSpinner from "../components/VhSpinner.vue"
import VhExpandCard from "../components/VhExpandCard.vue"
import VhParticleField from "../components/VhParticleField.vue"
import VhCounter from "../components/VhCounter.vue"
import { initParseVfx } from "./parseVfx"

const router = useRouter()
const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.is_admin === true)

/* 页面根节点：解析页专属动效（parseVfx）的作用域 */
const homeEl = ref(null)
let vfx = null

/* ---------------- 解析状态 ---------------- */
const url = ref("")
const routes = ref([])
const routeName = ref("")
const defaultRouteName = ref("")
const error = ref("")
const busy = ref(false)
const routesLoading = ref(true)
const routesError = ref("")
const inputEl = ref(null)
const consoleEl = ref(null)
const routeEls = ref([])

/* ---------------- 概览数据（真实读取） ---------------- */
const stats = ref({ records: 0, visitsToday: 0, visitsTotal: 0 })

/* ---------------- 后端在线状态灯 ----------------
 * 探测 /api/health：在线 → 绿灯「数据就绪」；后端不在线或数据库异常 → 红灯「数据异常」。
 * 进入页面查一次，之后每 30s 轮询，保证指示灯反映当前状态而非打开页那一刻。 */
const serviceState = ref("pending") // pending 同步中 | ok 数据就绪 | down 数据异常
let healthTimer = null

async function checkHealth() {
  try {
    await api.get("/health")
    serviceState.value = "ok"
  } catch {
    serviceState.value = "down"
  }
}

/* 官网地址：点击卡片新窗口直达，方便用户去官网找视频链接
 * brand：平台品牌色，驱动 3D 卡的装饰圆球 / 胶囊染色的 per-card CSS 变量
 * scope：平台招牌内容标签 —— 五卡各写各的垂直品类，互不重复；
 * desc：与 scope 互补的一行真实信息（卡内不与 scope 重复用词）
 * domain：底部迷你地址栏（等宽字），比「官网直达」更具信任感 */
const PLATFORM_CARDS = [
  { key: "bilibili", label: "哔哩哔哩", scope: "番剧 · 国创", desc: "纪录片与知识区正片", url: "https://www.bilibili.com/", brand: "#FB7299", domain: "bilibili.com" },
  { key: "tencent", label: "腾讯视频", scope: "大剧 · 体育", desc: "热门综艺与经典国漫", url: "https://v.qq.com/", brand: "#17C3CE", domain: "v.qq.com" },
  { key: "youku", label: "优酷", scope: "港剧 · 经典", desc: "独家港剧场与怀旧老片", url: "https://www.youku.com/", brand: "#0C7FF0", domain: "youku.com" },
  { key: "iqiyi", label: "爱奇艺", scope: "迷雾剧场", desc: "头部剧集与热血动漫", url: "https://www.iqiyi.com/", brand: "#00BE06", domain: "iqiyi.com" },
  { key: "mgtv", label: "芒果TV", scope: "王牌综艺", desc: "青春剧集与卫视独播", url: "https://www.mgtv.com/", brand: "#FF8A00", domain: "mgtv.com" },
]

/* 品牌彩色官方风格图标：默认 70% 透明度，悬浮恢复原生色彩 */
const BRAND_ICONS = {
  bilibili: `<svg viewBox="0 0 24 24" role="img" aria-label="哔哩哔哩"><rect width="24" height="24" rx="6" fill="#FB7299"/><path d="M7.4 4.2 10 7.2M16.6 4.2 14 7.2" stroke="#FFFFFF" stroke-width="1.9" stroke-linecap="round"/><rect x="4.4" y="7.2" width="15.2" height="12" rx="3.1" fill="none" stroke="#FFFFFF" stroke-width="1.9"/><circle cx="9.2" cy="13.2" r="1.5" fill="#FFFFFF"/><circle cx="14.8" cy="13.2" r="1.5" fill="#FFFFFF"/></svg>`,
  tencent: `<svg viewBox="0 0 24 24" role="img" aria-label="腾讯视频"><defs><linearGradient id="pf-tencent-g" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse"><stop stop-color="#17C3CE"/><stop offset="1" stop-color="#2E7CE8"/></linearGradient></defs><circle cx="12" cy="12" r="11" fill="url(#pf-tencent-g)"/><path d="M9.9 8.1v7.8l6.5-3.9z" fill="#FFFFFF"/></svg>`,
  youku: `<svg viewBox="0 0 24 24" role="img" aria-label="优酷"><circle cx="12" cy="12" r="11" fill="#0C7FF0"/><circle cx="12" cy="12" r="4.7" fill="none" stroke="#FFFFFF" stroke-width="2.7"/><circle cx="12" cy="12" r="1.2" fill="#FFFFFF"/></svg>`,
  iqiyi: `<svg viewBox="0 0 24 24" role="img" aria-label="爱奇艺"><circle cx="12" cy="12" r="11" fill="#00BE06"/><path d="M10 8.3v7.4l6.1-3.7z" fill="#FFFFFF"/></svg>`,
  mgtv: `<svg viewBox="0 0 24 24" role="img" aria-label="芒果TV"><defs><linearGradient id="pf-mgtv-g" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse"><stop stop-color="#FFC125"/><stop offset="1" stop-color="#FF8A00"/></linearGradient></defs><circle cx="12" cy="12" r="11" fill="url(#pf-mgtv-g)"/><path d="M7 16V9.2l5 4.4 5-4.4V16" stroke="#FFFFFF" stroke-width="2.1" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
}

const FAQ = [
  {
    q: "VIP 长视频为什么是内嵌播放？",
    a: "VIP 线路走第三方解析服务，页面通过 iframe 内嵌播放。部分线路设置了 X-Frame-Options 不允许内嵌，此时页面会给出「新窗口打开播放」的入口。",
    icon: CrownSimple,
  },
  {
    q: "解析失败或黑屏怎么办？",
    a: "第三方线路的稳定性会随时变化。回到解析页换一条线路重新解析即可，无需重新粘贴链接；常用线路可以在播放页直接切换。",
    icon: PlugsConnected,
  },
  {
    q: "短视频解析去哪了？",
    a: "短视频直链与主页批量解析已下线，当前仅支持 VIP 长视频线路解析；历史解析记录仍可在视频库中查看。",
    icon: Info,
  },
]

/* 每条 FAQ 独立展开状态 */
const faqOpen = ref(FAQ.map(() => false))

/* 「支持哪些链接」导引：不再弹两条示例，直接滚动到下方「覆盖 5 个主流平台」区块 */
const platformsEl = ref(null)
function goPlatforms() {
  platformsEl.value && platformsEl.value.scrollIntoView({ behavior: "smooth", block: "start" })
}

/* ---------------- 派生 ---------------- */
/* 粘贴链接 → 选线路 → 解析播放，三步即可，无需预先识别 */
const canSubmit = computed(() => !!url.value.trim() && !!routeName.value && !busy.value)

/* 三步各自的完成态：用于左侧导轨与编号徽标 */
const stepState = computed(() => {
  const s1 = !!url.value.trim()
  const s2 = !!routeName.value
  return [
    { done: s1, current: !s1 },
    { done: s2, current: s1 && !s2 },
    { done: false, current: s1 && s2 },
  ]
})
/* 剪贴板读取在 http 非安全上下文不可用，此时不展示「粘贴」按钮 */
const canPaste = computed(
  () => typeof navigator !== "undefined" && !!navigator.clipboard && !!window.isSecureContext,
)

/* ---------------- 剪贴板自动识别 ----------------
 * 切回解析页（标签页重新可见 / 窗口重新聚焦）时读取剪贴板：
 * 仅当内容是五大支持平台的长视频链接时自动填入，其余内容不打扰；
 * 剪贴板更新为新链接后再次切回，会覆盖旧链接 —— 始终保持最新复制的链接。 */
const SUPPORTED_PLATFORM_RE =
  /(bilibili\.com|b23\.tv|v\.qq\.com|qq\.com\/x|youku\.com|iqiyi\.com|i-qiyi\.com|mgtv\.com)/i

const autoToast = ref(false)
const autoToastLabel = ref("视频")
let toastTimer = null

function isSupportedLink(text) {
  const t = (text || "").trim()
  if (!t || t.length > 2048) return false
  return /^https?:\/\//i.test(t) && SUPPORTED_PLATFORM_RE.test(t)
}

/* 从链接中识别来源平台，用于提示文案（如「B站链接」） */
function platformLabelOf(text) {
  const rules = [
    [/(bilibili\.com|b23\.tv)/i, "B站"],
    [/(v\.qq\.com|qq\.com\/x)/i, "腾讯视频"],
    [/youku\.com/i, "优酷"],
    [/(iqiyi\.com|i-qiyi\.com)/i, "爱奇艺"],
    [/mgtv\.com/i, "芒果TV"],
  ]
  for (const [re, label] of rules) if (re.test(text)) return label
  return "视频"
}

/* 顶部浮动 Toast：4.5s 自动消隐，也可手动关闭 */
function showAutoToast(text) {
  autoToastLabel.value = platformLabelOf(text)
  autoToast.value = true
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (autoToast.value = false), 4500)
}

/* 与 pasteLink 的差异：只接受支持平台的链接，且输入框已有内容时也允许覆盖（保持最新） */
async function autoDetectClipboard() {
  if (!canPaste.value || busy.value) return
  try {
    const text = await navigator.clipboard.readText()
    if (isSupportedLink(text) && text.trim() !== url.value.trim()) {
      url.value = text.trim()
      error.value = ""
      showAutoToast(text)
    }
  } catch {
    /* 未授权或读取失败：静默跳过，不打断用户 */
  }
}

function onPageVisible() {
  if (document.visibilityState === "visible") autoDetectClipboard()
}

/* ---------------- 行为 ---------------- */
/* Hero 的「开始解析」：滚动到控制台并聚焦输入框 */
function focusInput() {
  consoleEl.value && consoleEl.value.scrollIntoView({ behavior: "smooth", block: "center" })
  inputEl.value && inputEl.value.focus({ preventScroll: true })
}

function onInput() {
  if (error.value) error.value = ""
}

function clearAll() {
  url.value = ""
  error.value = ""
  inputEl.value && inputEl.value.focus()
}

/* 从剪贴板粘贴链接；失败时静默回退到手动聚焦 */
async function pasteLink() {
  try {
    const text = await navigator.clipboard.readText()
    if (text && text.trim()) {
      url.value = text.trim()
      error.value = ""
    }
  } catch {
    /* 无权限或非安全上下文：交由用户手动 Ctrl+V */
  } finally {
    inputEl.value && inputEl.value.focus()
  }
}

/* 线路 chip 支持左右/上下方向键切换（radiogroup 漫游焦点） */
function pickRoute(i) {
  const list = routes.value
  if (!list.length) return
  const idx = (i + list.length) % list.length
  routeName.value = list[idx].name
  const el = routeEls.value[idx]
  el && el.focus()
}

async function loadRoutes() {
  routesLoading.value = true
  routesError.value = ""
  try {
    const { data } = await api.get("/parse/vip-routes")
    const list = data.routes || []
    routes.value = list
    defaultRouteName.value = data.default_route || (list[0] && list[0].name) || ""
    /* 默认选中管理员配置的默认线路 */
    if (!routeName.value || !list.some((r) => r.name === routeName.value))
      routeName.value = defaultRouteName.value
    if (!list.length) routesError.value = "尚无可用解析线路，请管理员在设置中添加"
  } catch {
    routesError.value = "线路加载失败，请刷新页面重试"
  } finally {
    routesLoading.value = false
  }
}

async function submit() {
  if (!canSubmit.value) return
  busy.value = true
  error.value = ""
  try {
    const { data } = await api.post("/parse/vip", {
      url: url.value.trim(),
      route_name: routeName.value || null,
    })
    router.push(`/player/${data.record.id}`)
  } catch (e) {
    error.value = e.friendly
  } finally {
    busy.value = false
  }
}

async function loadStats() {
  try {
    const [rec, visits] = await Promise.all([
      api.get("/records", { params: { page: 1, page_size: 1 } }),
      // 打开页面即计一次访问；接口只把数字回馈给管理员（非管理员返回 null）
      api.post("/visits"),
    ])
    stats.value = {
      records: rec.data.total || 0,
      visitsToday: visits.data.today || 0,
      visitsTotal: visits.data.total || 0,
    }
  } catch {
    /* 概览数据失败不阻塞主流程 */
  }
}

onMounted(() => {
  loadRoutes()
  loadStats()
  /* 后端状态灯：立即探测一次，之后 30s 轮询保活 */
  checkHealth()
  healthTimer = setInterval(checkHealth, 30000)
  /* 解析控制台以下区块的滚动入场动效（详见 parseVfx.js） */
  vfx = initParseVfx(homeEl.value)
  /* 剪贴板自动识别：首次进入先探测一次，之后监听切回页面 */
  autoDetectClipboard()
  document.addEventListener("visibilitychange", onPageVisible)
  window.addEventListener("focus", autoDetectClipboard)
})

onUnmounted(() => {
  vfx && vfx.destroy()
  vfx = null
  document.removeEventListener("visibilitychange", onPageVisible)
  window.removeEventListener("focus", autoDetectClipboard)
  clearTimeout(toastTimer)
  clearInterval(healthTimer)
})

/* 线路加载完成会改变控制台高度，下方区块的触发点随之移动，重新校准 */
watch(routesLoading, async (v) => {
  if (!v) {
    await nextTick()
    vfx && vfx.refresh()
  }
})

/* FAQ 展开收起改变文档高度，滚动触发点需要重新校准 */
watch(
  faqOpen,
  () => {
    vfx && vfx.refresh()
  },
  { deep: true },
)
</script>

<template>
  <div ref="homeEl" class="vh-page home">
    <VhParticleField variant="page" :density="0.7" />

    <!-- ================= Hero ================= -->
    <header class="hero">
      <span class="vh-eyebrow vh-fade-in-down">
        <Sparkle size="12" weight="fill" />
        Parse Engine v2
      </span>

      <h1 class="hero-title vh-fade-in-up" style="animation-delay: 0.06s">
        粘贴一条链接<br />
        <span class="vh-grad-text">全平台视频即点即播</span>
      </h1>

      <p class="hero-sub vh-fade-in-up" style="animation-delay: 0.12s">
        VIP 长视频线路解析：粘贴、选线路、点解析，结果统一沉淀进你的视频库。
      </p>

      <div class="hero-actions vh-fade-in-up" style="animation-delay: 0.18s">
        <button class="vh-btn vh-btn-primary hero-go" @click="focusInput">
          <Lightning size="16" weight="fill" />
          开始解析
          <ArrowRight size="15" weight="bold" />
        </button>

        <!-- 导引按钮：点击滚动到「覆盖 5 个主流平台」区块 -->
        <button type="button" class="vh-btn vh-btn-ghost" aria-label="查看支持的平台" @click="goPlatforms">
          <Question size="15" weight="regular" />
          支持哪些链接
          <ArrowDown size="14" weight="bold" />
        </button>
      </div>

      <!-- 静默数据行：真实读数，只留一行等宽小字 -->
      <p class="hero-stats num vh-fade-in-up" style="animation-delay: 0.24s">
        <span class="hs-item">
          我的视频库 <b><VhCounter :value="stats.records" /></b> 条
        </span>
        <template v-if="isAdmin">
          <i class="hs-dot" aria-hidden="true"></i>
          <span class="hs-item">今日访问 <b>{{ stats.visitsToday }}</b></span>
          <i class="hs-dot" aria-hidden="true"></i>
          <span class="hs-item">历史访问 <b>{{ stats.visitsTotal }}</b></span>
        </template>
        <i class="hs-dot" aria-hidden="true"></i>
        <span class="hs-live" :class="serviceState">
          <i class="hs-live-dot" aria-hidden="true"></i>
          {{ serviceState === "ok" ? "数据就绪" : serviceState === "down" ? "数据异常" : "同步中" }}
        </span>
      </p>
    </header>

    <!-- ================= 解析控制台：粘贴 → 选线路 → 解析播放 ================= -->
    <section ref="consoleEl" class="console-wrap vh-fade-in-up" :class="{ 'is-busy': busy }">
      <!-- 控制台抬头 -->
      <div class="con-top">
        <span class="con-eyebrow">
          <Atom size="11" weight="fill" />
          Parse Console
        </span>

        <!-- 剪贴板自动识别提示：嵌在控制台抬头中段 -->
        <transition name="toast">
          <div v-if="autoToast" class="clip-toast" role="status" aria-live="polite">
            <Sparkle size="14" weight="fill" />
            <span class="toast-text">
              已自动识别剪贴板中的 <b>{{ autoToastLabel }}</b> 链接并填入
            </span>
            <button class="toast-x" aria-label="关闭提示" @click="autoToast = false">
              <X size="12" weight="bold" />
            </button>
          </div>
        </transition>

        <span class="con-meta num">
          {{ routes.length ? `${routes.length} 条线路在线` : "线路读取中" }}
        </span>
      </div>

      <div class="con-steps">
        <!-- 01 粘贴链接 -->
        <div class="step" :class="stepState[0]">
          <span class="step-badge num" aria-hidden="true">
            <Check v-if="stepState[0].done" size="14" weight="bold" />
            <template v-else>01</template>
          </span>

          <div class="step-main">
            <div class="step-head">
              <span class="step-title">粘贴链接</span>
              <span class="step-tip">复制腾讯 / 优酷 / 爱奇艺 / 芒果 / B站链接，切回本页自动填入</span>
            </div>

            <div class="con-input">
              <LinkSimple class="con-icon" size="20" weight="regular" aria-hidden="true" />
              <textarea
                ref="inputEl"
                v-model="url"
                class="vh-textarea con-ta"
                data-tour="parse-input"
                rows="2"
                placeholder="粘贴长视频链接，Ctrl + Enter 可直接解析"
                spellcheck="false"
                aria-label="待解析链接"
                @input="onInput"
                @keydown.ctrl.enter.prevent="submit"
                @keydown.meta.enter.prevent="submit"
              ></textarea>
              <button v-if="url" class="con-clear" aria-label="清空输入" @click="clearAll">
                <X size="13" weight="bold" />
              </button>
              <button v-else-if="canPaste" class="con-paste" @click="pasteLink">
                <ClipboardText size="13" weight="regular" />
                粘贴
              </button>
            </div>
          </div>
        </div>

        <!-- 02 选择线路 -->
        <div class="step" :class="stepState[1]">
          <span class="step-badge num" aria-hidden="true">
            <Check v-if="stepState[1].done" size="14" weight="bold" />
            <template v-else>02</template>
          </span>

          <div class="step-main">
            <div class="step-head">
              <span class="step-title">选择线路</span>
              <span class="step-tip">
                <template v-if="defaultRouteName">
                  共 {{ routes.length }} 条 · 默认「{{ defaultRouteName }}」由管理员设置
                </template>
                <template v-else>读取线路配置中…</template>
              </span>
            </div>

            <div v-if="routesLoading" class="routes" aria-hidden="true">
              <span v-for="n in 6" :key="n" class="vh-skeleton route-skel"></span>
            </div>

            <div v-else-if="routes.length" class="routes" role="radiogroup" aria-label="解析线路">
              <button
                v-for="(r, i) in routes"
                :key="r.name"
                :ref="(el) => (routeEls[i] = el)"
                type="button"
                class="route"
                :class="{ active: routeName === r.name }"
                :style="{ animationDelay: 0.03 * i + 's' }"
                role="radio"
                :aria-checked="routeName === r.name"
                :tabindex="routeName === r.name ? 0 : -1"
                @click="routeName = r.name"
                @keydown.left.prevent="pickRoute(i - 1)"
                @keydown.right.prevent="pickRoute(i + 1)"
                @keydown.up.prevent="pickRoute(i - 1)"
                @keydown.down.prevent="pickRoute(i + 1)"
              >
                <span class="route-dot" aria-hidden="true"></span>
                <span class="route-name">{{ r.name }}</span>
                <span v-if="r.name === defaultRouteName" class="route-flag">默认</span>
              </button>
            </div>

            <p v-else class="routes-empty">
              <WarningCircle size="14" weight="fill" />
              {{ routesError || "暂无可用线路，请管理员在「设置」中添加" }}
            </p>
          </div>
        </div>

        <!-- 03 解析并播放 -->
        <div class="step" :class="stepState[2]">
          <span class="step-badge num" aria-hidden="true">03</span>

          <div class="step-main">
            <div class="step-action">
              <span class="act-left">
                <span class="step-title">解析并播放</span>
                <span class="step-tip">内嵌播放，部分线路需新窗口打开</span>
              </span>

              <button
                class="vh-btn vh-btn-primary go"
                :disabled="!canSubmit"
                @click="submit"
              >
                <VhSpinner v-if="busy" variant="orbit" :size="15" />
                <Play v-else size="15" weight="fill" />
                <span>{{ busy ? "解析中" : "解析并播放" }}</span>
                <ArrowRight v-if="!busy" size="16" weight="bold" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <transition name="slide">
        <p v-if="error" class="error" role="alert">
          <WarningCircle size="16" weight="fill" />
          {{ error }}
        </p>
      </transition>
    </section>

    <!-- ================= 特征条：三个卖点一行讲完，不再铺卡片 ================= -->
    <p class="feature-strip vh-fade-in-up" style="animation-delay: 0.3s">
      <span class="fs-item"><CubeTransparent size="14" weight="regular" />多线路自由切换</span>
      <i class="fs-dot" aria-hidden="true"></i>
      <span class="fs-item"><CrownSimple size="14" weight="regular" />VIP 长视频解析</span>
      <i class="fs-dot" aria-hidden="true"></i>
      <span class="fs-item"><FilmStrip size="14" weight="regular" />记录云端沉淀回溯</span>
    </p>

    <!-- ================= 支持平台 ================= -->
    <section ref="platformsEl" class="section platforms-section">
      <div class="sec-head">
        <div class="sec-head-main">
          <span class="sec-eyebrow"><PlugsConnected size="12" weight="fill" />COVERAGE</span>
          <h2 class="sec-title">覆盖 5 个主流平台</h2>
        </div>
        <p class="sec-desc">长视频线路解析通道，点击卡片直达平台官网找视频链接</p>
      </div>

      <div class="platforms">
        <a
          v-for="p in PLATFORM_CARDS"
          :key="p.key"
          class="pf"
          :href="p.url"
          target="_blank"
          rel="noopener noreferrer"
          :title="`前往${p.label}官网`"
          :aria-label="`前往${p.label}官网（新窗口打开）`"
        >
          <div class="pf-inner" :style="{ '--brand': p.brand }">
            <span class="pf-orbits" aria-hidden="true">
              <i class="pf-orb o1"></i>
              <i class="pf-orb o2"></i>
              <i class="pf-orb o3"></i>
            </span>
            <span class="pf-icon" v-html="BRAND_ICONS[p.key]"></span>
            <span class="pf-name">{{ p.label }}</span>
            <span class="pf-scope">{{ p.scope }}</span>
            <span class="pf-desc">{{ p.desc }}</span>
            <span class="pf-go" aria-hidden="true">
              {{ p.domain }}
              <ArrowSquareOut size="12" weight="bold" />
            </span>
          </div>
        </a>
      </div>
    </section>

    <!-- ================= 常见问题（Expandable Card） ================= -->
    <section class="section">
      <div class="sec-head">
        <div class="sec-head-main">
          <span class="sec-eyebrow"><Question size="12" weight="fill" />FAQ</span>
          <h2 class="sec-title">常见问题</h2>
        </div>
        <p class="sec-desc">关于线路与失效处理的说明</p>
      </div>

      <div class="faq">
        <VhExpandCard
          v-for="(f, i) in FAQ"
          :key="f.q"
          v-model="faqOpen[i]"
          :default-open="false"
          padding="0 18px 18px"
        >
          <template #head="{ open }">
            <span class="fq-icon" :class="{ on: open }"><component :is="f.icon" size="17" weight="regular" /></span>
            <span class="fq-q">{{ f.q }}</span>
          </template>

          <p class="fq-a">{{ f.a }}</p>
        </VhExpandCard>
      </div>

      <p class="faq-foot">
        <FilmStrip size="14" weight="regular" />
        还有疑问？解析结果页的每一处操作都带说明，可随时回看。
      </p>
    </section>
  </div>
</template>

<script>
export default { name: "ParseHome" }
</script>

<style scoped>
.home {
  position: relative;
  max-width: 1080px;
}

/* ---- 暗色主题可读性提亮（仅解析页作用域，不影响其他页面） ----
 * 全站 token 走 Spotify 式近黑沉浸；解析页内容密度高、辅助文字多，
 * 在页面根上覆盖一档更亮的变量：银/灰文字加亮、表面抬升、发丝线加浓。
 * 仅暗色主题生效（浅色主题由 html[data-theme="light"] 提供自己的值）。 */
html:not([data-theme="light"]) .home {
  --bg-raise: #1d1d1d;              /* 过渡层 181818 → 1d1d1d */
  --surface: #1c1c1c;               /* 卡面 181818 → 1c1c1c */
  --surface-2: #232323;             /* 输入/交互面 1f1f1f → 232323 */
  --surface-3: #2a2a2a;             /* 选中/抬升面 252525 → 2a2a2a */
  --line: rgba(255, 255, 255, 0.1);         /* 发丝线 .07 → .10 */
  --line-strong: rgba(255, 255, 255, 0.17); /* 强描边 .12 → .17 */
  --line-hover: rgba(255, 255, 255, 0.26);  /* 悬浮描边 .2 → .26 */
  --text-2: #c9c9c9;                /* 正文银灰 b3b3b3 → c9c9c9 */
  --text-3: #989898;                /* 辅助中灰 7c7c7c → 989898 */
}
/* 氛围层压在内容之下 */
.home > * { position: relative; z-index: 1; }

/* ================= Hero ================= */
.hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 18px 0 26px;
}
/* 排版即主张：超大 display 字号与 12px 眉标拉开 5 倍戏剧对比 */
.hero-title {
  margin: 22px 0 16px;
  font-size: clamp(34px, 5.6vw, 58px);
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1.14;
  color: var(--text-1);
}
.hero-sub {
  margin: 0 0 26px;
  max-width: 56ch;
  color: var(--text-2);
  font-size: 15px;
  line-height: 1.75;
}
.hero-actions { display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; }
.hero-go { height: 44px; padding: 0 22px; font-size: 15px; box-shadow: 0 2px 12px rgba(22, 156, 70, 0.3); }

/* 静默数据行：等宽小字 + 分隔点，数据退到视线边缘 */
.hero-stats {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin: 28px 0 0;
  color: var(--text-3);
  font-size: 12px;
  letter-spacing: 0.02em;
}
.hs-item b { color: var(--text-2); font-weight: 600; }
.hs-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--line-strong);
}
/* 后端状态灯：灰点同步中 / 绿点数据就绪 / 红点数据异常 */
.hs-live { display: inline-flex; align-items: center; gap: 6px; transition: color var(--dur-2) ease; }
.hs-live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--line-strong);
  transition: background var(--dur-2) ease, box-shadow var(--dur-2) ease;
}
.hs-live.ok { color: var(--accent); }
.hs-live.ok .hs-live-dot { background: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.hs-live.down { color: var(--danger); }
.hs-live.down .hs-live-dot { background: var(--danger); box-shadow: 0 0 0 3px var(--danger-soft); }

/* ================= 控制台 =================
 * 全页唯一主角：一套聚焦系统（顶部发丝光 + 聚焦辉光），
 * 不再叠加巡游光圈 / 扫描光束 / 链路指示灯。 */
.console-wrap {
  position: relative;
  width: min(820px, 100%);
  margin: 0 auto;
  padding: 24px 26px 20px;
  border-radius: var(--r-lg);
  background: linear-gradient(180deg, var(--surface-3), var(--surface) 56%);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-3);
  transition: box-shadow var(--dur-3) var(--ease-out), border-color var(--dur-2) ease;
}
/* 顶部发丝光：面板上沿一道极细的绿意渐变，唯一的常驻装饰 */
.console-wrap::before {
  content: "";
  position: absolute;
  top: 0;
  left: 14%;
  right: 14%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(30, 215, 96, 0.6), rgba(255, 181, 88, 0.32), transparent);
  opacity: 0.7;
  pointer-events: none;
}
.console-wrap:focus-within {
  border-color: rgba(30, 215, 96, 0.28);
  box-shadow: var(--shadow-3), 0 0 64px -20px rgba(30, 215, 96, 0.4);
}
.console-wrap.is-busy {
  border-color: rgba(30, 215, 96, 0.4);
  box-shadow: var(--shadow-3), 0 0 72px -16px rgba(30, 215, 96, 0.5);
}

/* ---- 控制台抬头 ---- */
.con-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 20px;
}
.con-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 11px 0 9px;
  border-radius: var(--r-pill);
  background: var(--tint);
  border: 1px solid var(--line);
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
}
.con-meta { font-size: 11.5px; color: var(--text-3); letter-spacing: 0.04em; }

/* ---- 步骤导轨：编号徽标 + 步间连接段 ---- */
.con-steps { position: relative; padding-left: 46px; }
.step { position: relative; }
.step + .step { margin-top: 22px; }
/* 步与步之间的连接段：本步完成即点亮 */
.step:not(:last-child)::before {
  content: "";
  position: absolute;
  left: -30px;
  top: 34px;
  width: 1px;
  height: calc(100% - 17px);
  background: var(--line);
  transition: background var(--dur-3) ease;
}
.step.done:not(:last-child)::before {
  background: linear-gradient(180deg, rgba(30, 215, 96, 0.55), rgba(30, 215, 96, 0.18));
}
.step-badge {
  position: absolute;
  left: -46px;
  top: -3px;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--line-strong);
  color: var(--text-3);
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  transition: color var(--dur-2) ease, background var(--dur-2) ease, border-color var(--dur-2) ease,
    box-shadow var(--dur-2) ease;
}
/* 已完成：绿意点亮，打勾落章 */
.step.done .step-badge {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: rgba(30, 215, 96, 0.5);
}
/* 进行中：琥珀描边，视线锚点（静态，不再循环呼吸） */
.step.current .step-badge {
  color: var(--gold-bright);
  background: var(--gold-soft);
  border-color: rgba(255, 164, 43, 0.5);
}
.step-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 11px;
}
.step-title { font-size: 13.5px; font-weight: 600; color: var(--text-1); }
.step-tip { margin-left: auto; font-size: 12px; color: var(--text-3); }

.step-main { flex: 1; min-width: 0; }

.con-input { position: relative; min-width: 0; border-radius: var(--r-md); }
.con-icon {
  position: absolute;
  top: 15px;
  left: 15px;
  color: var(--text-3);
  pointer-events: none;
  transition: color var(--dur-1) ease;
}
.con-input:focus-within .con-icon { color: var(--accent); }
.con-ta {
  min-height: 84px;
  padding: 13px 40px 13px 44px;
  font-size: 15px;
  line-height: 1.6;
  border-radius: var(--r-md);
}
.con-clear {
  position: absolute;
  top: 10px;
  right: 10px;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--surface-2);
  color: var(--text-3);
  cursor: pointer;
  transition: color var(--dur-1) ease, background var(--dur-1) ease;
}
.con-clear:hover { color: var(--text-1); background: var(--surface-3); }

/* 一键粘贴：输入为空时在右下角待命 */
.con-paste {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 10px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--text-3);
  font-size: 12px;
  cursor: pointer;
  transition: color var(--dur-1) ease, border-color var(--dur-1) ease, background var(--dur-1) ease;
}
.con-paste:hover {
  color: var(--accent);
  border-color: rgba(30, 215, 96, 0.45);
  background: var(--surface-3);
}

/* 剪贴板自动识别提示：嵌在控制台抬头中段，与左标题/右线路数共处一行。
 * 配色用琥珀金而非主题绿：全站绿色是大底色，金色只标注关键状态，
 * 高对比才不会被主题淹没。 */
.clip-toast {
  flex: 1 1 auto;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: var(--r-pill);
  background: linear-gradient(180deg, rgba(255, 181, 88, 0.18), rgba(255, 164, 43, 0.1));
  border: 1px solid rgba(255, 181, 88, 0.6);
  box-shadow: 0 0 20px -6px rgba(255, 164, 43, 0.55);
  color: var(--gold-bright);
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.01em;
  white-space: nowrap;
  animation: toast-in 0.34s var(--ease-out);
}
@keyframes toast-in {
  from { opacity: 0; transform: translateY(-7px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.clip-toast > svg { flex-shrink: 0; color: var(--gold-bright); }
.toast-text { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.toast-text b { color: var(--gold-bright); font-weight: 700; }
.toast-x {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  margin-left: 2px;
  flex-shrink: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 181, 88, 0.75);
  cursor: pointer;
  transition: color var(--dur-1) ease, background var(--dur-1) ease;
}
.toast-x:hover { color: var(--gold-bright); background: rgba(255, 181, 88, 0.15); }
.toast-x:focus-visible {
  outline: none;
  color: var(--gold-bright);
  box-shadow: 0 0 0 2px rgba(255, 181, 88, 0.45);
}

/* Toast 出入场：轻微下滑淡入，退场更快 */
.toast-enter-active { transition: opacity 0.3s var(--ease-out), transform 0.3s var(--ease-out); }
.toast-leave-active { transition: opacity 0.22s ease, transform 0.22s ease; }
.toast-enter-from { opacity: 0; transform: translateY(-7px) scale(0.96); }
.toast-leave-to { opacity: 0; transform: translateY(-4px); }

/* ---- 线路选择：胶囊 chip 组 ---- */
.routes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 108px;
  overflow-y: auto;
  padding: 2px;
}
.route {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 13px;
  border-radius: var(--r-pill);
  background: var(--bg-raise);
  border: 1px solid var(--line);
  color: var(--text-3);
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color var(--dur-1) ease, background var(--dur-1) ease, color var(--dur-1) ease;
  animation: vh-fade-in-up 0.42s var(--ease-out) both;
}
.route:hover { color: var(--text-1); border-color: var(--line-strong); }
.route:focus-visible {
  outline: none;
  color: var(--text-1);
  border-color: rgba(30, 215, 96, 0.5);
  box-shadow: 0 0 0 3px rgba(30, 215, 96, 0.25);
}
.route.active {
  color: var(--accent);
  border-color: rgba(30, 215, 96, 0.5);
  background: var(--accent-soft);
}
.route-dot {
  width: 6px;
  height: 6px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--line-strong);
  transition: background var(--dur-2) ease, box-shadow var(--dur-2) ease;
}
.route.active .route-dot {
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.route-name { font-weight: 500; }
.route-flag {
  padding: 0 6px;
  border-radius: var(--r-pill);
  background: var(--tint);
  border: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
}
.route.active .route-flag { color: var(--gold-bright); border-color: rgba(255, 181, 88, 0.4); }

/* 线路骨架屏 */
.route-skel { display: inline-block; width: 92px; height: 33px; border-radius: var(--r-pill); }

.routes-empty {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 9px 12px;
  border-radius: var(--r-sm);
  background: var(--warn-soft);
  border: 1px solid rgba(255, 164, 43, 0.4);
  color: var(--warn);
  font-size: 13px;
}
.routes-empty :deep(svg) { flex-shrink: 0; }

/* 提交行 */
.step-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 14px;
}
.act-left { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.act-left .step-tip { margin-left: 0; }
.go {
  min-width: 172px;
  height: 44px;
  font-size: 15px;
  gap: 8px;
  box-shadow: 0 2px 10px rgba(30, 215, 96, 0.28);
}
.go:not(:disabled):hover { box-shadow: 0 4px 18px -4px rgba(30, 215, 96, 0.5); }

.error {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 16px 0 0;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: var(--danger-soft);
  border: 1px solid rgba(243, 114, 127, 0.45);
  color: var(--danger);
  font-size: 13px;
}
.error :deep(svg) { flex-shrink: 0; }

/* 展开区内部条目的出入场 */
.slide-enter-active,
.slide-leave-active {
  transition: opacity 0.26s var(--ease-out), transform 0.26s var(--ease-out),
    margin 0.26s var(--ease-out), padding 0.26s var(--ease-out);
}
.slide-enter-from,
.slide-leave-to { opacity: 0; transform: translateY(-6px); }

/* ================= 特征条 =================
 * 三个卖点一行讲完：等宽分隔点 + 小图标，替代原先两组大卡片 */
.feature-strip {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 14px;
  margin: 26px auto 0;
  color: var(--text-3);
  font-size: 13px;
}
.fs-item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.fs-item :deep(svg) { color: var(--text-3); transition: color var(--dur-2) ease; }
.fs-item:hover :deep(svg) { color: var(--accent); }
.fs-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--line-strong);
}

/* ================= 通用区块头：编辑部式左右布局 ================= */
.section { margin-top: 72px; }
/* 「支持哪些链接」的滚动锚点：留出吸顶导航的高度，标题不被盖住 */
.platforms-section { scroll-margin-top: calc(var(--nav-h) + 16px); }
.sec-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px 32px;
  margin-bottom: 24px;
}
.sec-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: var(--accent);
  opacity: 0.85;
}
.sec-title {
  margin: 8px 0 0;
  font-size: 27px;
  font-weight: 700;
  letter-spacing: -0.025em;
  color: var(--text-1);
  line-height: 1.25;
}
.sec-desc {
  margin: 0 0 4px;
  max-width: 44ch;
  color: var(--text-3);
  font-size: 13.5px;
  line-height: 1.7;
  text-align: right;
}

/* ================= 平台（3D 卡片） =================
 * 手法来自 jztheme 3D card：外层 .pf 提供透视（perspective），
 * 内层 .pf-inner 保持 preserve-3d 并在 hover 时 rotate3d 倾斜；
 * 品牌圆球 / 图标文案 / 底部胶囊各自 translateZ 分层悬浮，
 * 鼠标来回划过时圆球逐层弹出（staggered transition-delay）。
 * 3D 悬浮效果全部收在 hover + fine pointer + motion-ok 媒询内：
 * 触屏 / reduced-motion 下退化为静态卡（描边与底色反馈保留）。 */
.platforms {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.pf {
  display: block;
  perspective: 900px;
  text-decoration: none;
  color: inherit;
}
.pf-inner {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  height: 100%;
  padding: 28px 14px 16px;
  border-radius: var(--r-md);
  background: var(--surface);
  border: 1px solid var(--line);
  transform-style: preserve-3d;
  transition: transform 0.55s ease-in-out, box-shadow 0.55s ease-in-out,
    border-color 0.3s ease, background 0.3s ease;
  box-shadow: var(--shadow-1);
}
/* 玻璃高光：右上角一道斜向光带（参考 3D 卡的 glass 层） */
.pf-inner::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(215deg, rgba(255, 255, 255, 0.09), transparent 46%);
  border-top: 1px solid rgba(255, 255, 255, 0.07);
  pointer-events: none;
}
html[data-theme="light"] .pf-inner::before {
  background: linear-gradient(215deg, rgba(255, 255, 255, 0.6), transparent 46%);
  border-top-color: rgba(255, 255, 255, 0.55);
}
.pf:hover .pf-inner { border-color: var(--line-hover); background: var(--surface-2); }
.pf:focus-visible { outline: none; }
.pf:focus-visible .pf-inner {
  border-color: rgba(30, 215, 96, 0.5);
  box-shadow: 0 0 0 3px rgba(30, 215, 96, 0.22);
}

/* 品牌色装饰圆球：右上角三层叠放，各自 translateZ 悬浮，hover 逐层向外弹 */
.pf-orbits {
  position: absolute;
  inset: 0;
  transform-style: preserve-3d;
  pointer-events: none;
}
.pf-orb {
  position: absolute;
  border-radius: 50%;
  background: var(--brand, #1ed760);
  border: 1px solid var(--line-strong);
  transition: transform 0.55s ease-in-out;
}
.pf-orb.o1 {
  width: 56px;
  height: 56px;
  top: 8px;
  right: 8px;
  opacity: 0.15;
  transform: translate3d(0, 0, 8px);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
}
.pf-orb.o2 {
  width: 38px;
  height: 38px;
  top: 15px;
  right: 15px;
  opacity: 0.2;
  transform: translate3d(0, 0, 18px);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  transition-delay: 0.12s;
}
.pf-orb.o3 {
  width: 22px;
  height: 22px;
  top: 22px;
  right: 22px;
  opacity: 0.3;
  transform: translate3d(0, 0, 28px);
  transition-delay: 0.24s;
}

/* 内容分层：图标与文案浮在卡面之上，营造视差 */
.pf-icon { width: 46px; height: 46px; margin-bottom: 12px; transform: translateZ(16px); }
.pf-icon :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
  opacity: 0.7;
  transition: opacity var(--dur-2) ease;
}
.pf:hover .pf-icon :deep(svg) { opacity: 1; }

.pf-name { display: block; font-size: 15px; font-weight: 600; color: var(--text-1); transform: translateZ(16px); }
/* 类型胶囊：品牌色染底描边，给每张卡一点专属色彩 */
.pf-scope {
  display: inline-block;
  margin-top: 7px;
  padding: 2.5px 10px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line);
  background: var(--tint);
  color: var(--text-2);
  font-size: 11px;
  font-weight: 500;
  transform: translateZ(16px);
}
/* 品牌色染底（浏览器不支持 color-mix 时退回上面的中性染底） */
@supports (background: color-mix(in srgb, red 10%, transparent)) {
  .pf-scope {
    border-color: color-mix(in srgb, var(--brand, #1ed760) 36%, transparent);
    background: color-mix(in srgb, var(--brand, #1ed760) 10%, transparent);
  }
}
.pf-desc {
  display: block;
  margin-top: 8px;
  color: var(--text-3);
  font-size: 11.5px;
  line-height: 1.55;
  transform: translateZ(16px);
}

/* 底部域名胶囊：等宽字迷你地址栏，hover 时向视点弹出 */
.pf-go {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: auto;
  padding: 5px 12px;
  border-radius: var(--r-pill);
  background: var(--tint);
  border: 1px solid var(--line);
  color: var(--text-3);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  transform: translateZ(12px);
  transition: color var(--dur-2) ease, border-color var(--dur-2) ease,
    transform 0.55s ease-in-out;
}

/* ---- 3D 悬浮编排：仅精确指针 + 未开启减少动态 ---- */
@media (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference) {
  .pf:hover .pf-inner {
    transform: rotate3d(1, 1, 0, 20deg);
    box-shadow: var(--shadow-3);
  }
  .pf:hover .pf-orb.o1 { transform: translate3d(0, 0, 30px); }
  .pf:hover .pf-orb.o2 { transform: translate3d(0, 0, 52px); }
  .pf:hover .pf-orb.o3 { transform: translate3d(0, 0, 74px); }
  .pf:hover .pf-go {
    color: var(--accent);
    border-color: rgba(30, 215, 96, 0.45);
    transform: translate3d(0, 0, 40px);
  }
}

/* ================= FAQ ================= */
.faq { display: flex; flex-direction: column; gap: 10px; }
.faq :deep(.vhx) {
  transition: border-color var(--dur-2) ease, background var(--dur-2) ease,
    box-shadow var(--dur-3) var(--ease-out);
}
.faq :deep(.vhx-head) { padding: 16px 18px; gap: 13px; }
.fq-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--bg-raise);
  border: 1px solid var(--line);
  color: var(--text-3);
  transition: color 0.3s ease, background 0.3s ease, border-color 0.3s ease;
}
.fq-icon.on {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: rgba(30, 215, 96, 0.4);
}
.fq-q { flex: 1; font-size: 14.5px; font-weight: 600; color: var(--text-1); }
.fq-a {
  margin: 0;
  padding: 12px 14px;
  border-radius: var(--r-sm);
  background: var(--bg-raise);
  border: 1px solid var(--line);
  color: var(--text-2);
  font-size: 13.5px;
  line-height: 1.85;
}
.faq-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 20px 0 0;
  color: var(--text-3);
  font-size: 13px;
}
.faq-foot :deep(svg) { color: var(--gold); }

/* ================= 响应式 ================= */
@media (max-width: 980px) {
  .platforms { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 720px) {
  .home { padding-left: 16px; padding-right: 16px; }
  .hero { padding-top: 4px; padding-bottom: 20px; }

  .console-wrap { padding: 18px 16px 14px; }
  .clip-toast { order: 3; flex-basis: 100%; font-size: 12px; }
  .con-steps { padding-left: 34px; }
  .step-badge { left: -34px; width: 26px; height: 26px; font-size: 10.5px; top: -1px; }
  .step:not(:last-child)::before { left: -21px; top: 28px; height: calc(100% - 9px); }
  .con-meta { font-size: 11px; }
  .step-tip { margin-left: 0; width: 100%; }
  .con-ta { padding-left: 16px; padding-right: 40px; }
  .con-icon { display: none; }
  .routes { max-height: 132px; }
  .step-action .go { width: 100%; }

  /* 区块头在窄屏退化为单列左对齐 */
  .sec-head { flex-direction: column; align-items: flex-start; }
  .sec-desc { text-align: left; margin-bottom: 0; }
  .platforms { grid-template-columns: repeat(2, 1fr); }
  .section { margin-top: 52px; }
  .feature-strip { gap: 10px; }
}
</style>
