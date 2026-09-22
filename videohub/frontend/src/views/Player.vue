<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import {
  PhArrowLeft as ArrowLeft,
  PhPlayCircle as PlayCircle,
  PhCopySimple as CopySimple,
  PhDownloadSimple as DownloadSimple,
  PhSubtitles as CaptionsSubtitles,
  PhCheck as Check,
  PhImages as Images,
  PhWarningCircle as WarningCircle,
  PhArrowSquareOut as LinkOut,
  PhPlugsConnected as PlugsConnected,
} from "@phosphor-icons/vue"
import Artplayer from "artplayer"
import api from "../api/client"
import { toast } from "../stores/toast"
import VhSpinner from "../components/VhSpinner.vue"
import VhPopover from "../components/VhPopover.vue"

const route = useRoute()
const id = Number(route.params.id)
const rec = ref(null)
const tab = ref("text")
const pageError = ref("")
const embed = ref(null) // {embed_url, route_name, embeddable?}
const copied = ref(false)
/* VIP 线路切换：当前线路高亮，点击即换线重载 iframe，不用回解析页 */
const routes = ref([])
const defaultRoute = ref("")
const currentRoute = ref("")
const switching = ref(false)
let art = null
let copiedTimer = null

const isVip = computed(() => rec.value?.source_type === "vip")
const needParse = computed(() => rec.value?.parse_status === "link_only")
const hasCaptions = computed(() => !!rec.value?.captions)

const PLATFORM_LABELS = {
  douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书", bilibili: "B站",
  tencent: "腾讯视频", youku: "优酷", iqiyi: "爱奇艺", mgtv: "芒果TV",
}
const SOURCE_LABELS = { single: "单视频", homepage: "主页批量", vip: "VIP" }
const TABS = [
  { key: "text", label: "纯文本" },
  { key: "srt", label: "SRT 字幕" },
  { key: "fmt", label: "格式化文案" },
]

const captionText = computed(() => {
  if (!rec.value?.captions) return ""
  if (tab.value === "text") return rec.value.captions.text_content
  if (tab.value === "srt") return rec.value.captions.srt_content
  return rec.value.captions.formatted_text
})

async function load() {
  try {
    const { data } = await api.get(`/records/${id}`)
    rec.value = data
    if (isVip.value) {
      const { data: e } = await api.get(`/records/${id}/embed`)
      embed.value = e
      currentRoute.value = e.route_name || ""
      // 内嵌可行性后台探测，不阻塞 iframe 先行加载；探测到不可内嵌才换兜底 UI
      checkEmbeddable()
      api.get("/parse/vip-routes")
        .then(({ data: d }) => {
          routes.value = d.routes || []
          defaultRoute.value = d.default_route || ""
        })
        .catch(() => { /* 线路条加载失败不影响播放 */ })
    } else if (!needParse.value) {
      await nextTick()
      initPlayer()
    }
  } catch (e) { pageError.value = e.friendly || "记录加载失败" }
}

function checkEmbeddable() {
  api.get(`/records/${id}/embed-check`, { params: currentRoute.value ? { route: currentRoute.value } : {} })
    .then(({ data }) => {
      // 迟到的探测结果只作用于同一线路，避免覆盖切换后的状态
      if (embed.value && data.route_name === embed.value.route_name && data.embeddable !== null)
        embed.value = { ...embed.value, embeddable: data.embeddable }
    })
    .catch(() => { /* 探测失败按可内嵌处理 */ })
}

async function switchRoute(name) {
  if (switching.value || name === currentRoute.value) return
  switching.value = true
  try {
    const { data } = await api.get(`/records/${id}/embed`, { params: { route: name } })
    embed.value = data
    currentRoute.value = data.route_name || name
    checkEmbeddable()
  } catch (e) {
    toast.error(e.friendly || "线路切换失败，请重试")
  } finally {
    switching.value = false
  }
}

function initPlayer() {
  if (art) { art.destroy(); art = null }
  art = new Artplayer({
    container: "#player",
    url: `/api/stream/${id}`,
    playbackRate: true,
    fullscreen: true,
    pip: true,
    setting: true,
  })
  art.on("video:error", () => { pageError.value = "视频加载失败，直链可能已过期" })
}

function download(name, text) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" })
  const a = document.createElement("a")
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

async function copy() {
  try {
    await navigator.clipboard.writeText(captionText.value)
    copied.value = true
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copied.value = false }, 1600)
  } catch {
    toast.error("复制失败，浏览器未授权剪贴板，请手动选择文本复制")
  }
}

onMounted(load)
onBeforeUnmount(() => {
  if (art) art.destroy()
  clearTimeout(copiedTimer)
})
</script>

<template>
  <div class="vh-page player-page">
    <router-link to="/library" class="back vh-fade-in-down">
      <ArrowLeft size="15" weight="bold" />
      返回视频库
    </router-link>

    <transition name="alert">
      <p v-if="pageError" class="error" role="alert">
        <WarningCircle size="16" weight="fill" />
        {{ pageError }}
      </p>
    </transition>

    <div v-if="rec" class="layout">
      <!-- 主列：播放舞台 -->
      <div class="main-col">
        <div class="stage-wrap vh-fade-in-up" style="animation-delay: 0.05s">
          <template v-if="isVip">
            <div v-if="embed && embed.embeddable !== false" class="stage">
              <span class="eq-chip" aria-hidden="true"><i></i><i></i><i></i><i></i><span>VIP LINE · PLAYING</span></span>
              <iframe :key="embed.route_name || 'embed'" :src="embed.embed_url" allowfullscreen referrerpolicy="no-referrer" title="VIP 视频播放器"></iframe>
            </div>
            <div v-else class="stage stage-fallback">
              <PlayCircle size="44" weight="light" class="fallback-icon" />
              <p>该线路不允许内嵌播放</p>
              <a :href="embed?.embed_url" target="_blank" rel="noopener noreferrer">
                <button class="vh-btn vh-btn-primary">
                  <LinkOut size="15" weight="bold" />
                  新窗口打开播放
                </button>
              </a>
            </div>
          </template>

          <template v-else>
            <div v-if="needParse" class="stage stage-fallback">
              <PlayCircle size="44" weight="light" class="fallback-icon" />
              <p>该条目为历史「仅链接」记录，短视频解析已下线，无法播放</p>
            </div>
            <div v-else class="stage">
              <span class="eq-chip" aria-hidden="true"><i></i><i></i><i></i><i></i><span>NOW PLAYING</span></span>
              <div id="player"></div>
            </div>
          </template>
        </div>

        <!-- VIP 线路切换条：卡顿换线不用回解析页 -->
        <section v-if="isVip && routes.length" class="route-bar">
          <span class="route-bar-label">
            <PlugsConnected size="14" weight="regular" />
            解析线路
          </span>
          <div class="route-chips" role="radiogroup" aria-label="解析线路">
            <button
              v-for="r in routes"
              :key="r.name"
              type="button"
              class="route"
              :class="{ active: r.name === currentRoute, busy: switching }"
              role="radio"
              :aria-checked="r.name === currentRoute"
              :disabled="switching"
              @click="switchRoute(r.name)"
            >
              <span class="route-dot" aria-hidden="true"></span>
              <span class="route-name">{{ r.name }}</span>
              <span v-if="r.name === defaultRoute" class="route-flag">默认</span>
            </button>
          </div>
          <span v-if="switching" class="route-switching">切换中…</span>
        </section>

        <!-- 标题与元信息 -->
        <div class="info-block vh-fade-in-up" style="animation-delay: 0.12s">
          <h1 class="title">{{ rec.title || "未获取视频标题" }}</h1>
          <div class="meta">
            <span v-if="PLATFORM_LABELS[rec.platform]" class="vh-chip">{{ PLATFORM_LABELS[rec.platform] }}</span>
            <span
              v-if="SOURCE_LABELS[rec.source_type]"
              class="vh-chip"
              :class="{ 'vh-chip-gold': rec.source_type === 'vip' }"
            >{{ SOURCE_LABELS[rec.source_type] }}</span>
            <a v-if="rec.source_url" class="source-link" :href="rec.source_url" target="_blank" rel="noopener noreferrer">
              来源链接
              <LinkOut size="12" weight="bold" />
            </a>
          </div>
        </div>

        <!-- 图集 -->
        <section v-if="rec.image_atlas && rec.image_atlas.length" class="atlas-section vh-fade-in-up" style="animation-delay: 0.18s">
          <h2 class="section-title">
            <Images size="17" weight="regular" />
            图集
            <span class="atlas-count num">{{ rec.image_atlas.length }}</span>
          </h2>
          <div class="atlas">
            <a
              v-for="(src, i) in rec.image_atlas"
              :key="i"
              :href="src"
              target="_blank"
              rel="noopener noreferrer"
              :style="{ animationDelay: Math.min(i, 9) * 0.045 + 's' }"
            >
              <img :src="src" loading="lazy" :alt="`图集第 ${i + 1} 张`" />
            </a>
          </div>
        </section>
      </div>

      <!-- 侧栏：文案 -->
      <aside v-if="!isVip" class="side-col vh-fade-in-up" style="animation-delay: 0.15s">
        <div class="caption-card">
          <header class="caption-head">
            <h2 class="section-title">
              <CaptionsSubtitles size="17" weight="regular" />
              视频文案
            </h2>
            <nav class="tabs" aria-label="文案格式">
              <button
                v-for="t in TABS"
                :key="t.key"
                type="button"
                class="tab"
                :class="{ active: tab === t.key }"
                @click="tab = t.key"
              >
                {{ t.label }}
              </button>
            </nav>
          </header>

          <template v-if="hasCaptions">
            <pre class="caption">{{ captionText }}</pre>
            <div class="caption-actions">
              <button class="vh-btn vh-btn-soft vh-btn-sm" @click="copy">
                <Check v-if="copied" size="14" weight="bold" />
                <CopySimple v-else size="14" weight="regular" />
                {{ copied ? "已复制" : "复制" }}
              </button>
              <button
                class="vh-btn vh-btn-ghost vh-btn-sm"
                @click="download(`${rec.title || id}${tab === 'srt' ? '.srt' : '.txt'}`, captionText)"
              >
                <DownloadSimple size="14" weight="regular" />
                下载
              </button>
            </div>
          </template>

          <template v-else>
            <div class="caption-empty">
              <CaptionsSubtitles size="32" weight="light" class="empty-icon" />
              <p>未提取该视频的文案（文案提取已随解析服务下线）</p>
            </div>
          </template>
        </div>
      </aside>
    </div>

    <!-- 加载态 -->
    <div v-if="!rec && !pageError" class="loading-state">
      <VhSpinner variant="orbit" :size="30" label="正在拉取解析结果…" :inline="false" />
    </div>
  </div>
</template>

<style scoped>
.player-page { max-width: 1400px; }

.back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 16px;
  padding: 6px 12px 6px 8px;
  border-radius: var(--r-pill);
  color: var(--text-2);
  font-size: 13px;
  font-weight: 500;
  transition: color 0.16s ease, background 0.16s ease;
}
.back:hover {
  color: var(--accent);
  text-decoration: none;
  background: var(--surface-2);
}

.error {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 16px;
  padding: 10px 14px;
  border-radius: var(--r-sm);
  background: var(--danger-soft);
  border: 1px solid rgba(243, 114, 127, 0.45);
  color: var(--danger);
  font-size: 13px;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 24px;
  align-items: start;
}

/* 播放舞台 */
.stage-wrap { min-width: 0; }
.stage {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #000000;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  overflow: hidden;
  box-shadow: var(--shadow-3);
}
/* 舞台外的一圈极弱白光晕，缓慢呼吸，把播放器「托」起来 */
.stage-wrap { position: relative; }
.stage-wrap::after {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: var(--r-lg);
  pointer-events: none;
  background: radial-gradient(120% 90% at 50% 0%, rgba(255, 255, 255, 0.04), transparent 62%);
  animation: stage-halo 7s ease-in-out infinite;
}
@keyframes stage-halo {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}
/* 播放舞台左上角的均衡器角标（纯装饰） */
.eq-chip {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 11px;
  border-radius: var(--r-pill);
  background: rgba(0, 0, 0, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  color: rgba(255, 255, 255, 0.85);
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.1em;
  pointer-events: none;
}
.eq-chip i {
  width: 2.5px;
  height: 10px;
  border-radius: 2px;
  background: var(--accent);
  transform-origin: bottom center;
  animation: vh-bars 0.9s var(--ease-in-out) infinite;
}
.eq-chip i:nth-child(1) { animation-delay: 0s; }
.eq-chip i:nth-child(2) { animation-delay: 0.12s; }
.eq-chip i:nth-child(3) { animation-delay: 0.24s; }
.eq-chip i:nth-child(4) { animation-delay: 0.36s; }
.stage iframe { width: 100%; height: 100%; border: 0; display: block; }

/* VIP 线路切换条（样式与解析页线路 chips 保持一致） */
.route-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
}
.route-bar-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-3);
  font-size: 12.5px;
}
.route-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.route {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 12px;
  border-radius: var(--r-pill);
  background: var(--bg-raise);
  border: 1px solid var(--line);
  color: var(--text-3);
  font-size: 12.5px;
  line-height: 1.4;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color var(--dur-1) ease, background var(--dur-1) ease, color var(--dur-1) ease;
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
.route.busy { opacity: 0.55; pointer-events: none; }
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
.route-switching {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--accent);
  animation: vh-bars 0.9s var(--ease-in-out) infinite;
}
.stage :deep(#player) { width: 100%; height: 100%; }
.stage-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--text-3);
  background:
    radial-gradient(400px 200px at 50% 30%, rgba(30, 215, 96, 0.05), transparent 60%),
    #000000;
}
.fallback-icon { opacity: 0.5; }
.stage-fallback p { margin: 0; font-size: 14px; }

/* 信息区 */
.info-block { margin-top: 20px; }
.title {
  margin: 0 0 12px;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.4;
  color: var(--text-1);
}
.meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.source-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-3);
  transition: color 0.16s ease;
}
.source-link:hover { color: var(--accent); }
.row { display: flex; align-items: center; gap: 10px; margin-top: 16px; flex-wrap: wrap; }

/* 说明触发点 */
.tip-btn {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--text-3);
  cursor: help;
  transition: color var(--dur-1) ease, border-color var(--dur-1) ease, background var(--dur-1) ease;
}
.tip-btn:hover { color: var(--accent); border-color: rgba(30, 215, 96, 0.5); background: var(--surface-3); }
.tip-link {
  border: 0;
  background: none;
  padding: 0;
  color: var(--text-3);
  font: 400 12.5px/1.5 var(--font-sans);
  text-decoration: underline dotted;
  text-underline-offset: 3px;
  cursor: help;
  transition: color var(--dur-1) ease;
}
.tip-link:hover { color: var(--accent); }
.tip-row { display: flex; align-items: center; gap: 7px; }
.tip-row + .tip-row { margin-top: 6px; }
.tip-row :deep(svg) { flex-shrink: 0; color: var(--accent); }

/* 图集 */
.atlas-section { margin-top: 32px; }
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
}
.section-title :deep(svg) { color: var(--text-3); }
.atlas-count {
  display: inline-grid;
  place-items: center;
  min-width: 22px;
  height: 22px;
  padding: 0 7px;
  border-radius: var(--r-pill);
  background: var(--surface);
  border: 1px solid var(--line);
  color: var(--text-3);
  font-size: 11.5px;
  font-weight: 600;
}
.atlas {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 10px;
  margin-top: 14px;
}
.atlas a { animation: vh-fade-in-up 0.45s var(--ease-out) both; }
.atlas img {
  width: 100%;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  display: block;
  transition: border-color 0.18s ease, transform 0.25s var(--ease-out), box-shadow 0.25s ease;
}
.atlas a:hover img {
  border-color: var(--accent);
  transform: translateY(-3px);
  box-shadow: var(--shadow-2);
}

/* 文案侧栏 */
.caption-card {
  position: sticky;
  top: calc(var(--nav-h) + 20px);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: var(--shadow-1);
}
.caption-head { display: flex; flex-direction: column; gap: 14px; }
.tabs {
  display: flex;
  gap: 2px;
  background: var(--bg-raise);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 3px;
}
.tab {
  flex: 1;
  height: 30px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-2);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
}
.tab:hover { color: var(--text-1); }
.tab.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
  box-shadow: var(--inset-hl);
}

.caption {
  margin: 0;
  padding: 16px;
  max-height: 480px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--bg-raise);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  color: var(--text-2);
  font: 400 13px/1.8 var(--font-sans);
  scrollbar-width: thin;
  scrollbar-color: var(--surface-3) transparent;
}
.caption::-webkit-scrollbar { width: 6px; }
.caption::-webkit-scrollbar-thumb { background: var(--surface-3); border-radius: var(--r-pill); }
.caption-actions { display: flex; gap: 8px; }

.caption-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 48px 16px;
  color: var(--text-3);
  font-size: 13.5px;
  text-align: center;
}
.caption-empty .empty-icon { opacity: 0.5; }
.caption-empty p { margin: 0; }

/* 加载态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 120px 24px;
  color: var(--text-3);
}
.loading-state :deep(.sp) { color: var(--accent); }
.loading-state p { margin: 0; font-size: 14px; }

/* 错误提示过渡 */
.alert-enter-active,
.alert-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease, margin 0.25s ease;
}
.alert-enter-from,
.alert-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ---- 移动端：单列 ---- */
@media (max-width: 1024px) {
  .layout { grid-template-columns: 1fr; }
  .caption-card { position: static; }
}
</style>
