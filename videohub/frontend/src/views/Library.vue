<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import {
  PhMagnifyingGlass as MagnifyingGlass,
  PhPlayCircle as PlayCircle,
  PhTrash as Trash,
  PhClock as Clock,
  PhCaretLeft as CaretLeft,
  PhCaretRight as CaretRight,
  PhDotsThree as DotsThree,
  PhSlidersHorizontal as SlidersHorizontal,
  PhLink as Link,
  PhCopySimple as CopySimple,
  PhSparkle as Sparkle,
  PhChartBar as ChartBar,
  PhArrowRight as ArrowRight,
  PhX as X,
  PhCheck as Check,
  PhPencilSimple as PencilSimple,
  PhSquaresFour as SquaresFour,
} from "@phosphor-icons/vue"
import api from "../api/client"
import { toast } from "../stores/toast"
import VhPopover from "../components/VhPopover.vue"
import VhSpinner from "../components/VhSpinner.vue"
import VhExpandCard from "../components/VhExpandCard.vue"
import VhMorphPanel from "../components/VhMorphPanel.vue"
import VhCounter from "../components/VhCounter.vue"
import VhEmptyArt from "../components/VhEmptyArt.vue"

const router = useRouter()
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const platform = ref("")
const sourceType = ref("")
const q = ref("")
const loading = ref(false)
const filtersOpen = ref(false)
const distOpen = ref(false)
const copiedId = ref(null)
let copiedTimer = null

// 标题重命名：行内编辑状态
const renamingId = ref(null)
const renameValue = ref("")
const renameError = ref("")
const renameBusy = ref(false)

// 批量管理：多选删除状态（选择跨页累计，切换筛选时清空）
const selectMode = ref(false)
const selected = ref([])
const batchBusy = ref(false)

const allPageSelected = computed(
  () => items.value.length > 0 && items.value.every((it) => selected.value.includes(it.id)),
)

const PLATFORMS = ["douyin", "kuaishou", "xiaohongshu", "bilibili", "tencent", "youku", "iqiyi", "mgtv", "unknown"]
const PLATFORM_LABELS = {
  douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书", bilibili: "B站",
  tencent: "腾讯视频", youku: "优酷", iqiyi: "爱奇艺", mgtv: "芒果TV", unknown: "未知来源",
}
const SOURCE_LABELS = { single: "单视频", homepage: "主页批量", vip: "VIP" }

const totalPages = () => Math.max(1, Math.ceil(total.value / pageSize))

/* 本页平台分布：把当前页数据变成一眼可读的占比条 */
const distribution = computed(() => {
  const map = new Map()
  for (const it of items.value) {
    const k = it.platform || "unknown"
    map.set(k, (map.get(k) || 0) + 1)
  }
  const rows = [...map.entries()]
    .map(([key, count]) => ({ key, label: PLATFORM_LABELS[key] || key, count }))
    .sort((a, b) => b.count - a.count)
  const max = rows.length ? rows[0].count : 1
  return rows.map((r) => ({ ...r, pct: Math.round((r.count / max) * 100) }))
})

const activeFilterCount = computed(
  () => [platform.value, sourceType.value].filter(Boolean).length,
)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get("/records", {
      params: {
        platform: platform.value || undefined,
        source_type: sourceType.value || undefined,
        q: q.value || undefined,
        page: page.value,
        page_size: pageSize,
      },
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function coverUrl(item) {
  return item.cover_url ? `/api/stream/${item.id}/cover` : null
}

function platformLabel(p) {
  return PLATFORM_LABELS[p] || p
}

function formatDate(item) {
  if (!item.created_at) return ""
  try {
    const d = new Date(item.created_at)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
  } catch { return "" }
}

function open(item) {
  router.push(`/player/${item.id}`)
}

async function remove(item) {
  if (!confirm(`确认删除「${item.title || "未获取视频标题"}」？`)) return
  try {
    await api.delete(`/records/${item.id}`)
    await load()
    toast.success("记录已删除")
  } catch (e) {
    toast.error(e.friendly || "删除失败，请稍后重试")
  }
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) selected.value = []
}

function togglePick(item) {
  const i = selected.value.indexOf(item.id)
  if (i >= 0) selected.value.splice(i, 1)
  else selected.value.push(item.id)
}

function toggleSelectPage() {
  if (allPageSelected.value) {
    selected.value = selected.value.filter((id) => !items.value.some((it) => it.id === id))
  } else {
    for (const it of items.value) {
      if (!selected.value.includes(it.id)) selected.value.push(it.id)
    }
  }
}

async function batchRemove() {
  const n = selected.value.length
  if (!n || batchBusy.value) return
  if (!confirm(`确认删除选中的 ${n} 条记录？删除后不可恢复。`)) return
  batchBusy.value = true
  try {
    await api.post("/records/batch-delete", { ids: selected.value })
    selectMode.value = false
    selected.value = []
    await load()
    // 当前页被删空则回退一页，watch(page) 会自动重新加载
    if (!items.value.length && page.value > 1) page.value--
    toast.success(`已删除 ${n} 条记录`)
  } catch (e) {
    toast.error(e.friendly || "批量删除失败，请稍后重试")
  } finally {
    batchBusy.value = false
  }
}

async function copyLink(item) {
  if (!item.source_url) return
  try {
    await navigator.clipboard.writeText(item.source_url)
    copiedId.value = item.id
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copiedId.value = null }, 1600)
  } catch { /* 剪贴板不可用时静默失败 */ }
}

function startRename(item) {
  renamingId.value = item.id
  renameValue.value = item.title || ""
  renameError.value = ""
  nextTick(() => document.getElementById(`rename-${item.id}`)?.focus())
}

function cancelRename() {
  renamingId.value = null
  renameError.value = ""
}

async function submitRename(item) {
  const title = renameValue.value.trim()
  if (!title) {
    renameError.value = "标题不能为空"
    return
  }
  if (title === item.title) {
    cancelRename()
    return
  }
  renameBusy.value = true
  try {
    const { data } = await api.patch(`/records/${item.id}`, { title })
    item.title = data.title
    renamingId.value = null
    toast.success("重命名成功")
  } catch (e) {
    renameError.value = e.friendly || "重命名失败，请稍后重试"
  } finally {
    renameBusy.value = false
  }
}

function resetFilters() {
  platform.value = ""
  sourceType.value = ""
  q.value = ""
}

/* 卡片追光：把鼠标位置写进 CSS 变量，驱动 ::after 径向辉光 */
function cellSpot(e) {
  const el = e.currentTarget
  const r = el.getBoundingClientRect()
  el.style.setProperty("--mx", `${e.clientX - r.left}px`)
  el.style.setProperty("--my", `${e.clientY - r.top}px`)
}

function pickPlatform(key) {
  platform.value = platform.value === key ? "" : key
}

watch([platform, sourceType, q], () => { page.value = 1; selected.value = []; load() })
watch(page, load)
onMounted(load)
</script>

<template>
  <div class="vh-page">
    <header class="lib-head">
      <div class="lib-head-main">
        <span class="vh-eyebrow vh-fade-in-down">
          <Sparkle size="12" weight="fill" />
          Library
        </span>
        <h1 class="lib-title vh-fade-in-up" style="animation-delay: 0.06s">视频库</h1>
        <p class="lib-sub vh-fade-in-up" style="animation-delay: 0.1s">
          全部解析记录自动入库，可回放、取文案、导图集
        </p>
      </div>

      <div class="lib-stat vh-fade-in-up" style="animation-delay: 0.14s">
        <span class="ls-value"><VhCounter :value="total" /></span>
        <span class="ls-label">累计记录</span>
      </div>
    </header>

    <!-- 筛选：Compact → Expanded -->
    <VhMorphPanel
      v-model="filtersOpen"
      compact-padding="10px 12px"
      expanded-padding="16px 18px"
      compact-radius="12px"
      expanded-radius="16px"
      :duration="380"
      class="filters-wrap"
    >
      <template #compact="{ toggle }">
        <div class="f-compact">
          <div class="search">
            <MagnifyingGlass size="16" weight="regular" class="search-icon" aria-hidden="true" />
            <input v-model="q" class="vh-input" placeholder="搜索标题" aria-label="搜索标题" />
            <button v-if="q" class="search-clear" aria-label="清空搜索" @click="q = ''">
              <X size="12" weight="bold" />
            </button>
          </div>

          <div class="f-actions">
            <button
              class="vh-btn vh-btn-ghost f-toggle"
              :class="{ on: selectMode }"
              :aria-pressed="selectMode"
              @click="toggleSelectMode"
            >
              <SquaresFour size="15" weight="regular" />
              批量管理
            </button>
            <button class="vh-btn vh-btn-ghost f-toggle" :aria-expanded="filtersOpen" @click="toggle">
              <SlidersHorizontal size="15" weight="regular" />
              筛选
              <span v-if="activeFilterCount" class="f-badge num">{{ activeFilterCount }}</span>
            </button>
          </div>
        </div>
      </template>

      <div class="f-expanded">
        <div class="f-row">
          <span class="f-label">平台</span>
          <div class="f-chips">
            <button
              v-for="p in PLATFORMS"
              :key="p"
              class="f-chip"
              :class="{ on: platform === p }"
              @click="pickPlatform(p)"
            >
              {{ platformLabel(p) }}
            </button>
          </div>
        </div>

        <div class="f-row">
          <span class="f-label">来源</span>
          <div class="f-chips">
            <button class="f-chip" :class="{ on: sourceType === '' }" @click="sourceType = ''">全部</button>
            <button
              v-for="(label, key) in SOURCE_LABELS"
              :key="key"
              class="f-chip"
              :class="{ on: sourceType === key }"
              @click="sourceType = sourceType === key ? '' : key"
            >
              {{ label }}
            </button>
          </div>
        </div>

        <div class="f-foot">
          <button class="vh-btn vh-btn-ghost vh-btn-sm" @click="resetFilters">重置筛选</button>
          <span class="f-hit">命中 <b class="num">{{ total }}</b> 条</span>
        </div>
      </div>
    </VhMorphPanel>

    <!-- 本页分布（Expandable Card） -->
    <VhExpandCard v-if="items.length" v-model="distOpen" class="dist" padding="4px 18px 18px">
      <template #head>
        <span class="dist-icon"><ChartBar size="17" weight="regular" /></span>
        <span class="dist-text">
          <span class="dist-title">本页平台分布</span>
          <span class="dist-desc">当前页 {{ items.length }} 条记录的来源构成</span>
        </span>
      </template>

      <ul class="dist-list">
        <li v-for="d in distribution" :key="d.key" class="dist-row">
          <span class="dr-label">{{ d.label }}</span>
          <span class="dr-track"><i class="dr-fill" :style="{ width: d.pct + '%' }"></i></span>
          <span class="dr-count num">{{ d.count }}</span>
        </li>
      </ul>
    </VhExpandCard>

    <!-- 批量管理工具条 -->
    <div v-if="selectMode" class="sel-bar vh-fade-in-up">
      <button class="vh-btn vh-btn-ghost vh-btn-sm" :disabled="!items.length" @click="toggleSelectPage">
        {{ allPageSelected ? "取消全选" : "全选本页" }}
      </button>
      <span class="sel-count num">已选 <b>{{ selected.length }}</b> 条</span>
      <span class="sel-space"></span>
      <button
        class="vh-btn vh-btn-ghost vh-btn-sm"
        :disabled="!selected.length"
        @click="toggleSelectMode"
      >
        退出管理
      </button>
      <button
        class="vh-btn vh-btn-danger vh-btn-sm"
        :disabled="!selected.length || batchBusy"
        @click="batchRemove"
      >
        <Trash size="14" weight="fill" />
        {{ batchBusy ? "删除中…" : `删除所选` }}
      </button>
    </div>

    <!-- 骨架加载 -->
    <div v-if="loading && !items.length" class="grid">
      <div v-for="i in 8" :key="i" class="cell">
        <div class="vh-skeleton cover"></div>
        <div class="vh-skeleton line-title"></div>
        <div class="vh-skeleton line-sub"></div>
      </div>
    </div>

    <!-- 海报墙 -->
    <div v-else-if="items.length" class="grid" :class="{ selecting: selectMode }">
      <article
        v-for="(item, i) in items"
        :key="item.id"
        class="cell"
        :class="{ selected: selected.includes(item.id) }"
        :style="{ animationDelay: Math.min(i, 11) * 0.035 + 's' }"
        @mousemove="cellSpot"
      >
        <div class="cover-wrap">
          <button
            type="button"
            class="cover-btn"
            :aria-label="selectMode ? `选择 ${item.title || '视频'}` : `播放 ${item.title || '视频'}`"
            @click="selectMode ? togglePick(item) : open(item)"
          >
            <span class="cover">
              <img v-if="coverUrl(item)" :src="coverUrl(item)" loading="lazy" :alt="item.title || '视频封面'" />
              <span v-else class="no-cover">
                <span class="nc-wave" aria-hidden="true"></span>
                <span class="nc-badge" aria-hidden="true"><PlayCircle size="20" weight="fill" /></span>
              </span>
              <span class="cover-overlay" aria-hidden="true">
                <span class="play-btn"><PlayCircle size="34" weight="fill" /></span>
              </span>
              <span v-if="item.parse_status === 'link_only'" class="badge">未解析</span>
            </span>
          </button>

          <!-- 多选框（批量管理模式） -->
          <button
            v-if="selectMode"
            type="button"
            class="pick"
            :class="{ on: selected.includes(item.id) }"
            :aria-label="selected.includes(item.id) ? '取消选择' : '选择'"
            @click="togglePick(item)"
          >
            <Check v-if="selected.includes(item.id)" size="13" weight="bold" />
          </button>

          <span class="quick">
            <!-- 更多操作（Popover） -->
            <VhPopover placement="bottom-end" :offset="8" :width="196" padding="8px">
              <template #default>
                <button class="icon-btn" aria-label="更多操作">
                  <DotsThree size="18" weight="bold" />
                </button>
              </template>
              <template #content>
                <div class="qmenu">
                  <button class="qmenu-item" @click="open(item)">
                    <PlayCircle size="15" weight="regular" />
                    播放
                  </button>
                  <button class="qmenu-item" @click="startRename(item)">
                    <PencilSimple size="15" weight="regular" />
                    重命名
                  </button>
                  <button
                    v-if="item.source_url"
                    class="qmenu-item"
                    @click="copyLink(item)"
                  >
                    <Check v-if="copiedId === item.id" size="15" weight="bold" />
                    <CopySimple v-else size="15" weight="regular" />
                    {{ copiedId === item.id ? "已复制" : "复制原链接" }}
                  </button>
                  <a
                    v-if="item.source_url"
                    class="qmenu-item"
                    :href="item.source_url"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Link size="15" weight="regular" />
                    打开来源页
                  </a>
                  <button class="qmenu-item danger" @click="remove(item)">
                    <Trash size="15" weight="regular" />
                    删除记录
                  </button>
                </div>
              </template>
            </VhPopover>
          </span>
        </div>

        <div v-if="renamingId === item.id" class="rename-row">
          <input
            :id="`rename-${item.id}`"
            v-model="renameValue"
            class="vh-input rename-input"
            type="text"
            maxlength="100"
            placeholder="输入新标题，同一账号内不可重复"
            :disabled="renameBusy"
            @keyup.enter="submitRename(item)"
            @keyup.esc="cancelRename"
          />
          <span class="rename-actions">
            <button class="icon-btn" aria-label="确认重命名" :disabled="renameBusy" @click="submitRename(item)">
              <Check size="15" weight="bold" />
            </button>
            <button class="icon-btn" aria-label="取消重命名" :disabled="renameBusy" @click="cancelRename">
              <X size="15" weight="bold" />
            </button>
          </span>
          <p v-if="renameError" class="rename-error" role="alert">{{ renameError }}</p>
        </div>
        <span v-else class="title" title="双击可重命名" @dblclick="!selectMode && startRename(item)">{{ item.title || "未获取视频标题" }}</span>
        <div class="meta-row">
          <span class="meta">
            <span class="vh-chip">{{ platformLabel(item.platform) }}</span>
            <span
              v-if="SOURCE_LABELS[item.source_type]"
              class="vh-chip"
              :class="{ 'vh-chip-gold': item.source_type === 'vip' }"
            >{{ SOURCE_LABELS[item.source_type] }}</span>
          </span>
          <span v-if="formatDate(item)" class="date">
            <Clock size="12" weight="regular" />
            {{ formatDate(item) }}
          </span>
        </div>
      </article>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!loading" class="vh-empty vh-stagger">
      <VhEmptyArt variant="film" />
      <p class="vh-empty-title">暂无记录</p>
      <p class="empty-desc">回到「解析」页粘贴一条链接，解析结果会自动出现在这里。</p>
      <router-link class="vh-btn vh-btn-soft" to="/">
        去解析视频
        <ArrowRight size="15" weight="bold" />
      </router-link>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages() > 1" class="pager">
      <button class="vh-btn vh-btn-ghost vh-btn-sm" :disabled="page <= 1" @click="page--">
        <CaretLeft size="14" weight="bold" />
        上一页
      </button>
      <span class="num pager-info">{{ page }} / {{ totalPages() }}</span>
      <button class="vh-btn vh-btn-ghost vh-btn-sm" :disabled="page >= totalPages()" @click="page++">
        下一页
        <CaretRight size="14" weight="bold" />
      </button>
    </div>

    <!-- 翻页时的轻量指示 -->
    <div v-if="loading && items.length" class="refreshing">
      <VhSpinner variant="pulse" :size="16" />
      <span>正在载入第 {{ page }} 页</span>
    </div>
  </div>
</template>

<style scoped>
/* ---- 页头 ---- */
.lib-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
}
.lib-title {
  margin: 16px 0 6px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.025em;
  color: var(--text-1);
}
.lib-sub { margin: 0; color: var(--text-3); font-size: 14px; }
.lib-stat {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  padding: 10px 18px;
  border-radius: var(--r-md);
  background: var(--grad-panel);
  border: 1px solid var(--line);
}
.ls-value { font-size: 24px; font-weight: 700; color: var(--text-1); line-height: 1.2; }
.ls-label { font-size: 12px; color: var(--text-3); }

/* ---- 筛选（Compact → Expanded） ---- */
.filters-wrap { margin-bottom: 16px; }
.f-compact {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}
.search { position: relative; min-width: 0; }
.search-icon {
  position: absolute;
  top: 50%;
  left: 12px;
  transform: translateY(-50%);
  color: var(--text-3);
  pointer-events: none;
  transition: color var(--dur-1) ease;
}
.search:focus-within .search-icon { color: var(--accent); }
.search .vh-input { padding-left: 36px; padding-right: 34px; }
.search-clear {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: 0;
  border-radius: var(--r-pill);
  background: var(--surface-3);
  color: var(--text-3);
  cursor: pointer;
  transition: color var(--dur-1) ease, background var(--dur-1) ease;
}
.search-clear:hover { color: var(--text-1); background: var(--surface-2); }

.f-toggle { position: relative; }
.f-actions { display: flex; gap: 8px; }
.f-toggle.on {
  color: var(--accent);
  border-color: rgba(30, 215, 96, 0.5);
  background: var(--accent-soft);
}
.f-badge {
  display: inline-grid;
  place-items: center;
  min-width: 17px;
  height: 17px;
  padding: 0 5px;
  border-radius: var(--r-pill);
  background: var(--gold);
  color: var(--bg);
  font-size: 11px;
  font-weight: 700;
  animation: vh-scale-in 0.28s var(--ease-spring) both;
}

.f-expanded { display: flex; flex-direction: column; gap: 12px; margin-top: 14px; }
.f-row { display: flex; align-items: flex-start; gap: 12px; }
.f-label {
  flex-shrink: 0;
  min-width: 34px;
  padding-top: 6px;
  font-size: 12.5px;
  color: var(--text-3);
}
.f-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.f-chip {
  height: 28px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--text-2);
  font: 500 12.5px/1 var(--font-sans);
  cursor: pointer;
  transition: background var(--dur-1) ease, border-color var(--dur-1) ease, color var(--dur-1) ease,
    transform var(--dur-2) var(--ease-out);
}
.f-chip:hover { color: var(--text-1); border-color: var(--line-strong); transform: translateY(-1px); }
.f-chip.on {
  background: var(--accent-soft);
  border-color: rgba(30, 215, 96, 0.5);
  color: var(--accent);
  font-weight: 600;
}
.f-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.f-hit { color: var(--text-3); font-size: 12.5px; }
.f-hit b { color: var(--accent); }

/* ---- 分布卡 ---- */
.dist { margin-bottom: 18px; }
.dist :deep(.vhx-head) { padding: 14px 18px; gap: 13px; }
.dist-icon {
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
.dist.is-open .dist-icon { color: var(--accent); background: var(--accent-soft); border-color: rgba(30, 215, 96, 0.4); }
.dist-text { display: flex; flex-direction: column; line-height: 1.4; }
.dist-title { font-size: 14px; font-weight: 600; color: var(--text-1); }
.dist-desc { font-size: 12px; color: var(--text-3); }

.dist-list { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.dist-row { display: grid; grid-template-columns: 78px minmax(0, 1fr) 34px; align-items: center; gap: 10px; }
.dr-label { font-size: 12.5px; color: var(--text-2); }
.dr-track { height: 6px; border-radius: var(--r-pill); background: var(--surface-2); overflow: hidden; }
.dr-fill {
  display: block;
  height: 100%;
  border-radius: var(--r-pill);
  background: linear-gradient(90deg, var(--accent-strong), var(--accent));
  animation: dr-grow 0.7s var(--ease-out) both;
}
@keyframes dr-grow { from { transform: scaleX(0); transform-origin: left center; } to { transform: scaleX(1); } }
.dr-count { font-size: 12px; color: var(--text-3); text-align: right; }

/* ---- 批量管理 ---- */
.sel-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
  padding: 10px 14px;
  border: 1px solid rgba(30, 215, 96, 0.35);
  border-radius: var(--r-md);
  background: var(--grad-panel);
  animation: vh-fade-in-up 0.3s var(--ease-out) both;
}
.sel-count { color: var(--text-2); font-size: 13px; }
.sel-count b { color: var(--accent); }
.sel-space { flex: 1; }

/* 多选框：封面右上角，选中填充品牌绿 */
.pick {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 3;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 1.5px solid rgba(255, 255, 255, 0.55);
  background: rgba(7, 10, 18, 0.45);
  color: #000;
  cursor: pointer;
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s var(--ease-spring);
}
.pick:hover { transform: scale(1.1); }
.pick.on { background: var(--accent-strong); border-color: var(--accent-strong); }

.cell.selected {
  border-color: rgba(30, 215, 96, 0.55);
  box-shadow: 0 0 0 1px rgba(30, 215, 96, 0.35), var(--shadow-3);
}
.grid.selecting .quick { display: none; }
.grid.selecting .cell:hover .cover img { transform: none; }

/* ---- 海报墙 ---- */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}
.cell {
  position: relative;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 10px 10px 14px;
  text-align: left;
  animation: vh-fade-in-up 0.45s var(--ease-out) both;
  transition: border-color 0.2s ease, transform 0.25s var(--ease-out), box-shadow 0.25s ease;
}
.cell:hover {
  border-color: var(--line-strong);
  transform: translateY(-4px);
  box-shadow: var(--shadow-3);
}
/* 鼠标追随辉光：位置由 --mx/--my 驱动 */
.cell::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: radial-gradient(
    240px circle at var(--mx, 50%) var(--my, 50%),
    rgba(30, 215, 96, 0.07),
    transparent 65%
  );
  opacity: 0;
  transition: opacity 0.25s ease;
  pointer-events: none;
}
.cell:hover::after { opacity: 1; }
.cover-wrap { position: relative; }
.cover-btn {
  display: block;
  width: 100%;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  border-radius: var(--r-sm);
}
.cover {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: var(--r-sm);
  overflow: hidden;
  background: var(--surface-2);
  border: 1px solid var(--line);
}
.cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.45s var(--ease-out);
}
.cell:hover .cover img { transform: scale(1.03); }

.cover-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(7, 10, 18, 0.42);
  opacity: 0;
  transition: opacity 0.25s ease;
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}
.cell:hover .cover-overlay { opacity: 1; }
/* 播放按钮：亮绿圆钮 + 黑色图标（Spotify 播放键同款），重投影托起 */
.play-btn {
  display: grid;
  place-items: center;
  width: 58px;
  height: 58px;
  border-radius: 50%;
  color: #000;
  background: var(--accent-strong);
  border: 0;
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.6);
  transform: scale(0.8);
  transition: transform 0.25s var(--ease-spring), background 0.2s ease;
}
.cell:hover .play-btn { transform: scale(1); }
.play-btn:hover { background: var(--accent-hover); }

/* 无封面占位：暗色渐变波浪 + 品牌水纹 */
.no-cover {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background:
    radial-gradient(120% 90% at 18% 0%, rgba(30, 215, 96, 0.14), transparent 55%),
    radial-gradient(130% 100% at 85% 100%, rgba(255, 164, 43, 0.12), transparent 60%),
    linear-gradient(165deg, #1e1e1e 0%, #121212 62%);
}
.nc-wave {
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='90' viewBox='0 0 220 90'%3E%3Cpath d='M0 45 Q 27.5 20 55 45 T 110 45 T 165 45 T 220 45' fill='none' stroke='rgba(30,215,96,0.28)' stroke-width='1.5'/%3E%3Cpath d='M0 66 Q 27.5 41 55 66 T 110 66 T 165 66 T 220 66' fill='none' stroke='rgba(255,164,43,0.22)' stroke-width='1.5'/%3E%3Cpath d='M0 24 Q 27.5 4 55 24 T 110 24 T 165 24 T 220 24' fill='none' stroke='rgba(30,215,96,0.15)' stroke-width='1.5'/%3E%3C/svg%3E");
  background-size: 220px 90px;
  opacity: 0.85;
}
.nc-badge {
  position: relative;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  color: var(--text-2);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  transition: color 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
}
.cell:hover .nc-badge {
  color: var(--accent);
  border-color: rgba(60, 228, 119, 0.4);
  box-shadow: 0 0 24px -6px rgba(30, 215, 96, 0.55);
}
.badge {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 3px 9px;
  border-radius: var(--r-pill);
  background: rgba(255, 164, 43, 0.92);
  color: var(--bg);
  font-size: 11.5px;
  font-weight: 600;
  backdrop-filter: blur(4px);
}

/* 悬浮快捷操作：弹性上浮入场 */
.quick {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  opacity: 0;
  transform: translateY(8px) scale(0.92);
  transition: opacity 0.2s ease, transform 0.32s var(--ease-spring);
  pointer-events: none;
  z-index: 2;
}
.cell:hover .quick,
.quick:focus-within { opacity: 1; transform: translateY(0); pointer-events: auto; }
.icon-btn {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  background: var(--surface);
  color: var(--text-2);
  cursor: pointer;
  box-shadow: var(--shadow-2);
  transition: color var(--dur-1) ease, background var(--dur-1) ease, border-color var(--dur-1) ease;
}
.icon-btn:hover { color: var(--accent); background: var(--surface-3); border-color: rgba(30, 215, 96, 0.5); }

/* Popover 内的快捷菜单 */
.qmenu { display: flex; flex-direction: column; gap: 2px; }
.qmenu-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 8px 9px;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-2);
  font: 500 13px/1.4 var(--font-sans);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  transition: background var(--dur-1) ease, color var(--dur-1) ease;
}
.qmenu-item:hover { background: var(--surface); color: var(--text-1); text-decoration: none; }
.qmenu-item.danger { color: var(--danger); }
.qmenu-item.danger:hover { background: var(--danger-soft); }
.qmenu-item :deep(svg) { flex-shrink: 0; color: var(--text-3); }
.qmenu-item:hover :deep(svg) { color: var(--accent); }
.qmenu-item.danger :deep(svg),
.qmenu-item.danger:hover :deep(svg) { color: var(--danger); }

.title {
  margin-top: 11px;
  padding: 0 4px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-1);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color 0.16s ease;
}

/* 标题行内重命名 */
.rename-row {
  margin-top: 11px;
  padding: 0 4px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.rename-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  font-size: 13.5px;
}
.rename-actions { display: inline-flex; gap: 4px; }
.rename-error {
  flex-basis: 100%;
  margin: 2px 0 0;
  color: var(--danger);
  font-size: 12px;
  line-height: 1.4;
}
.cell:hover .title { color: var(--accent); }

.meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 9px;
  padding: 0 4px;
}
.meta { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.date { display: inline-flex; align-items: center; gap: 4px; color: var(--text-3); font-size: 11.5px; flex-shrink: 0; }
.date :deep(svg) { flex-shrink: 0; }

/* 翻页指示 */
.refreshing {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  margin-top: 18px;
  color: var(--accent);
  font-size: 12.5px;
}

/* 触屏无 hover */
@media (hover: none) {
  .quick { opacity: 1; transform: none; pointer-events: auto; }
  .cover-overlay { display: none; }
}

/* 骨架 */
.cover.vh-skeleton { aspect-ratio: 16 / 9; border-radius: var(--r-sm); }
.line-title { height: 14px; margin: 12px 4px 0; width: 82%; }
.line-sub { height: 11px; margin: 8px 4px 4px; width: 46%; }

.empty-desc {
  margin: 0;
  max-width: 34em;
  color: var(--text-2);
  font-size: 14px;
  line-height: 1.7;
}

.pager { display: flex; align-items: center; justify-content: center; gap: 14px; margin-top: 36px; }
.pager-info { color: var(--text-2); font-size: 13px; min-width: 60px; text-align: center; }

/* ---- 移动端 ---- */
@media (max-width: 720px) {
  .lib-head { flex-direction: column; align-items: flex-start; gap: 14px; }
  .lib-stat { align-items: flex-start; width: 100%; }
  .f-compact { grid-template-columns: 1fr; }
  .f-row { flex-direction: column; gap: 6px; }
  .grid { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 14px; }
  .cell { padding: 8px 8px 12px; }
  .date { display: none; }
  .dist-row { grid-template-columns: 60px minmax(0, 1fr) 28px; }
}
</style>
