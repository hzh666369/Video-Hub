<script setup>
/**
 * Dashboard · 管理员数据看板（Operations Center 运营中控）
 *
 * v6.0 —— 视觉语言对齐「深蓝科技 HUD 指挥大屏」参考稿：
 *   深夜蓝黑底 + 网格与底部地平线光晕；卡片 = 发光 1px 蓝描边 + 四角 HUD 角标
 *   （见 dashboard.css .glassbox::after）+ 外圈辉光；KPI 图标改圆角方形高辉光芯片；
 *   涨跌改胶囊徽章；页脚加品牌信息带。信息架构、数据口径与语义色锁不变：
 *   访问量 = azure 蓝 / 解析量 = aqua 青；状态色：ok 绿 · info 蓝 · warn 黄 · rose 红。
 *
 * 布局四层：
 *   ① 指令栏：品牌区（VIDEOHUB / OPERATIONS CENTER / 中文副标）+ 日期时钟 + 运行状态 + 刷新 / 全屏 / 管理员
 *   ② KPI 行：4 张独立卡（发光图标 + 实时徽章 + 大数字 + 涨跌胶囊 + 迷你趋势线）
 *   ③ 中部：左 2fr 趋势主图（7D/30D/90D 切换）+ 右 1fr 实时动态（LIVE + 自动滚动开关）
 *   ④ 底部三栏：平台解析占比 ｜ 解析排行 TOP 5 ｜ 系统状态 + 页脚品牌带
 *
 * 数据全部取自 /admin/dashboard 真实字段（含 v5 新增的 online_users / system /
 * delta_pct），不虚构指标；系统状态面板的口径见 DashStatus.vue 头注。
 * 口径约定（2026-09-15 统一）：解析量 = 解析操作次数（AccessLog，单调递增），
 * 解析记录存量另见 Storage 面板/平台占比；访问量 = visit+login+register 活动数。
 * 排行/平台的涨跌均为后端真实今日 vs 昨日同比，无任何伪随机形态曲线。
 * 涨跌口径全页面统一（2026-09-15）：昨日无基线(0)时今日>0 记 +100（从无到有）、
 * 今日=0 记 0（持平，灰色 →）；KPI 卡与排行/平台列表同一约定，不再一处「—」一处「+100%」。
 *
 * 布局：固定视口高 + 分数行网格；视口不足（< 820px）或栅格断到单列时
 * 降级为自然流 + 页面滚动。配色全部走 --bd-* 变量（暗色默认 / 浅色覆盖），
 * 子组件共读同一套变量，切主题时整块看板（含 ECharts 画布）一起换肤。
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import {
  PhArrowsIn as ArrowsIn,
  PhArrowsOut as ArrowsOut,
  PhArrowClockwise as ArrowClockwise,
  PhCaretDown as CaretDown,
  PhCaretRight as CaretRight,
  PhChartBar as ChartBar,
  PhChartPie as ChartPie,
  PhDotsSixVertical as DotsSixVertical,
  PhMonitorPlay as MonitorPlay,
  PhPlay as Play,
  PhStack as Stack,
  PhUser as UserIcon,
  PhUsers as UsersIcon,
} from "@phosphor-icons/vue"
import api from "../api/client"
import { toast } from "../stores/toast"
import { useAuthStore } from "../stores/auth"
import VhCounter from "../components/VhCounter.vue"
import DashTrend from "../components/dashboard/DashTrend.vue"
import DashPlatforms from "../components/dashboard/DashPlatforms.vue"
import DashSpark from "../components/dashboard/DashSpark.vue"
import DashFeed from "../components/dashboard/DashFeed.vue"
import DashStatus from "../components/dashboard/DashStatus.vue"
/* 毛玻璃卡片 / 面板骨架 / 标题栏 / 分段开关 / 徽章等布局原语：与子组件共用，放全局样式 */
import "../styles/dashboard.css"

const auth = useAuthStore()

/* ---- 指令栏日期时钟（v6：常显，参考稿同款「YYYY-MM-DD HH:MM:SS」）+ 全屏模式 ---- */
const full = ref(false)
const clock = ref("")
const dateStr = ref("")
let clockTimer = null

function tick() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, "0")
  clock.value = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  dateStr.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

async function enterFull() {
  full.value = true
  try {
    await document.documentElement.requestFullscreen()
  } catch {
    /* 浏览器拒绝全屏（如非用户手势）时退化为纯覆盖层，功能不受影响 */
  }
}

function exitFull() {
  full.value = false
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
}

/* Esc 退出原生全屏时同步 UI 状态（fullscreenchange 在退出时也触发） */
function onFsChange() {
  if (!document.fullscreenElement && full.value) full.value = false
}

const data = ref(null)          // 最近一次成功响应（失败时保留旧数据继续展示）
const loadError = ref(false)    // 最近一次请求是否失败（驱动指示灯）
const loading = ref(false)
const loadedOnce = ref(false)
const healthMs = ref(null)      // 浏览器实测的 /api/health 往返延迟
let pollTimer = null

/** 涨跌百分比：与后端 _pct_delta 同一约定 —— 昨日无基线(0)时，
 *  今日 >0 记 +100（从无到有）、今日 =0 记 0（持平）。保证 KPI 卡与
 *  排行/平台列表（后端 delta_pct）全页面口径一致，不再出现 null。 */
function delta(today, yesterday) {
  if (!yesterday) return today ? 100 : 0
  return Math.round(((today - yesterday) / yesterday) * 100)
}

async function load() {
  loading.value = true
  /* health 探针延迟与看板数据并行取：一个公开只读端点，1 次/分钟的频率远低于其限流。
   * 注意 client.js 的 baseURL 已含 /api，这里传相对路径 /health */
  const t0 = performance.now()
  const ping = api.get("/health")
    .then(() => { healthMs.value = Math.round(performance.now() - t0) })
    .catch(() => { healthMs.value = null })
  try {
    const r = await api.get("/admin/dashboard")
    data.value = r.data
    loadError.value = false
    if (!loadedOnce.value) loadedOnce.value = true
  } catch (e) {
    loadError.value = true
    if (!loadedOnce.value) {
      toast.error(e.friendly || "看板数据加载失败")
    } else {
      toast.error("看板数据刷新失败，将在下个周期自动重试")
    }
  } finally {
    loading.value = false
  }
  await ping
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(load, 60_000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

onMounted(() => {
  tick()
  clockTimer = setInterval(tick, 1000)
  load()
  startPolling()
  document.addEventListener("fullscreenchange", onFsChange)
})
onBeforeUnmount(() => {
  stopPolling()
  if (clockTimer) { clearInterval(clockTimer); clockTimer = null }
  document.removeEventListener("fullscreenchange", onFsChange)
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
})

/* ---- 模板派生数据 ---- */
const kpis = computed(() => data.value?.kpis)
const trend = computed(() => data.value?.trend || { days: [], visits: [], parses: [] })
const platforms = computed(() => data.value?.platforms || [])
const topUsers = computed(() => data.value?.top_users || [])
const recent = computed(() => data.value?.recent || [])
const onlineUsers = computed(() => data.value?.online_users ?? 0)
const system = computed(() => data.value?.system || null)

/* ---- 趋势图时间范围：90 天全量来自后端，7/30 为尾部切片 ---- */
const RANGES = ["7D", "30D", "90D"]
const range = ref("30D")
const RANGE_DAYS = { "7D": 7, "30D": 30, "90D": 90 }
const RANGE_NAME = { "7D": "7 天", "30D": "30 天", "90D": "90 天" }
const rangeN = computed(() => RANGE_DAYS[range.value])
const sliceTrend = computed(() => ({
  days: trend.value.days.slice(-rangeN.value),
  visits: trend.value.visits.slice(-rangeN.value),
  parses: trend.value.parses.slice(-rangeN.value),
}))

/**
 * KPI 卡片：圆形发光图标 + 标题（前两张带「实时」徽章）+ 大数字 +
 * 底行（涨跌 + sparkline；用户总数卡为「在线 N」+ 占比轨道）。
 * 颜色传 CSS 变量表达式，明暗主题切换时自动跟随。
 */
const spineSegs = computed(() => {
  const k = kpis.value
  if (!k) return []

  /* 累计解析较昨日涨幅 = 今日解析操作 / 截至昨日累计操作数；首日无存量时无从比较 */
  const totalBase = k.total_parses - k.today_parses
  const totalDelta = totalBase > 0
    ? Math.round((k.today_parses / totalBase) * 1000) / 10
    : null

  return [
    {
      key: "visits",
      label: "今日访问",
      live: true,
      icon: UserIcon,
      value: k.today_visits,
      delta: delta(k.today_visits, k.yesterday_visits),
      spark: trend.value.visits.slice(-14),
      sparkColor: "var(--bd-azure)",
    },
    {
      key: "parses",
      label: "今日解析",
      live: true,
      icon: MonitorPlay,
      value: k.today_parses,
      delta: delta(k.today_parses, k.yesterday_parses),
      spark: trend.value.parses.slice(-14),
      sparkColor: "var(--bd-aqua)",
    },
    {
      key: "users",
      label: "用户总数",
      icon: UsersIcon,
      value: k.total_users,
      online: onlineUsers.value,
      rail: k.total_users ? Math.min(100, (onlineUsers.value / k.total_users) * 100) : 0,
    },
    {
      key: "total",
      label: "累计解析",
      icon: Stack,
      value: k.total_parses,
      delta: totalDelta,
      deltaSuffix: totalDelta == null && k.today_parses > 0 ? `今日新增 ${k.today_parses}` : null,
      spark: trend.value.parses.slice(-14),
      sparkColor: "var(--bd-azure)",
    },
  ]
})

/* ---- TOP 5 排行表：数值/涨跌均为后端真实统计（parse_count = 该用户历史解析
 *      操作数，delta_pct = 真实今日 vs 昨日同比）。占比分母 = 全站累计解析操作数
 *      （与 KPI「累计解析」同源；已注销用户的操作不归属任何人，故前五名占比之和
 *      可能 < 100%，这是真实分布而非误差）。不做任何伪随机形态曲线 ---- */
const rankRows = computed(() => {
  const totalOps = kpis.value?.total_parses || 0
  return topUsers.value.map((u) => {
    let h = 0
    for (const ch of u.username) h = (h * 31 + ch.charCodeAt(0)) % 360
    return {
      ...u,
      pct: totalOps ? Math.round((u.parse_count / totalOps) * 1000) / 10 : 0,
      hue: h,
    }
  })
})
const rankMax = computed(() => topUsers.value[0]?.parse_count || 0)
</script>

<template>
  <div class="board" :class="{ full }">
    <!-- ============ ① 指令栏 ============ -->
    <header class="bd-head glassbox">
      <div class="bd-brand">
        <span class="bd-mark" aria-hidden="true"><Play :size="16" weight="fill" /></span>
        <span class="bd-wordmark">VIDEOHUB</span>
        <span class="bd-crumb">
          <b>OPERATIONS CENTER</b>
          <i>视频解析智能运营控制中心</i>
        </span>
      </div>
      <div class="bd-actions">
        <span class="bd-clock"><i class="dt">{{ dateStr }}</i>{{ clock }}</span>
        <span class="bd-live" :class="{ bad: loadError }">
          <i class="bd-dot" aria-hidden="true"></i>{{ loadError ? "同步异常" : "系统运行正常" }}
        </span>
        <button v-if="full" class="bd-btn" @click="exitFull"><ArrowsIn :size="13" />退出全屏</button>
        <button class="bd-btn" :disabled="loading" @click="load">
          <ArrowClockwise :size="13" class="bd-ic" :class="{ spin: loading }" />刷新
        </button>
        <button v-if="!full" class="bd-btn" @click="enterFull"><ArrowsOut :size="13" />全屏</button>
        <RouterLink class="bd-user" to="/settings" title="账号与管理">
          <span class="bd-ava" aria-hidden="true"><UserIcon :size="13" weight="bold" /></span>
          <span class="bd-uname">{{ auth.user?.username || "admin" }}</span>
          <CaretDown :size="12" aria-hidden="true" />
        </RouterLink>
      </div>
    </header>

    <!-- 首次加载失败：整页重试 -->
    <div v-if="!loadedOnce && loadError" class="bd-empty">
      <p>看板数据加载失败</p>
      <button class="bd-btn accent" @click="load">重试</button>
    </div>

    <main v-else class="bd-main">
      <!-- ============ ② KPI 卡片行 ============ -->
      <div v-if="spineSegs.length" class="spine" role="group" aria-label="核心指标">
        <div v-for="seg in spineSegs" :key="seg.key" class="seg-card glassbox">
          <span class="grip" aria-hidden="true"><DotsSixVertical :size="12" /></span>
          <div class="in seg-in">
            <div class="s-top">
              <span class="s-ico" aria-hidden="true"><component :is="seg.icon" :size="16" weight="duotone" /></span>
              <span class="s-lbl">{{ seg.label }}</span>
              <span v-if="seg.live" class="s-live">实时</span>
            </div>
            <span class="s-num"><VhCounter :value="seg.value" :duration="900" /></span>
            <div class="s-foot">
              <span v-if="typeof seg.delta === 'number'" class="delta" :class="seg.delta > 0 ? 'up' : seg.delta < 0 ? 'down' : 'flat'">
                {{ seg.delta > 0 ? "↑" : seg.delta < 0 ? "↓" : "→" }} {{ Math.abs(seg.delta) }}% <i class="d-lbl">较昨日</i>
              </span>
              <span v-else-if="seg.deltaSuffix" class="delta flat">{{ seg.deltaSuffix }}</span>
              <span v-else-if="seg.online != null" class="on-line"><i aria-hidden="true"></i>在线 {{ seg.online }}</span>
              <span v-else class="delta flat">— <i class="d-lbl">较昨日</i></span>

              <DashSpark v-if="seg.spark && seg.spark.length > 1" :values="seg.spark" :color="seg.sparkColor" />
              <span v-else-if="seg.rail != null" class="s-rail" aria-hidden="true">
                <i :style="{ width: Math.min(100, Math.max(0, seg.rail)) + '%' }"></i>
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 首次加载中的骨架：形状贴合 KPI 卡，避免空壳闪烁 -->
      <div v-else class="spine">
        <div v-for="n in 4" :key="n" class="seg-card glassbox">
          <div class="in seg-in">
            <span class="vh-skeleton sk-i"></span>
            <span class="vh-skeleton sk-n"></span>
            <span class="vh-skeleton sk-c"></span>
          </div>
        </div>
      </div>

      <!-- ============ ③ 中部：趋势主图 + 实时动态 ============ -->
      <section class="mid">
        <div class="glassbox panel hero">
          <div class="in">
            <div class="p-head">
              <h2 class="p-title">
                <i class="p-ic" aria-hidden="true"><ChartBar :size="14" weight="bold" /></i>
                {{ RANGE_NAME[range] }}运行趋势
              </h2>
              <div class="seg" role="group" aria-label="趋势时间范围">
                <button
                  v-for="r in RANGES" :key="r" type="button"
                  :class="{ on: range === r }" :aria-pressed="range === r"
                  @click="range = r"
                >{{ r }}</button>
              </div>
            </div>
            <div class="tr-sub">
              <span class="tr-cap">访问量 · 解析量</span>
              <div class="legend">
                <span><i class="lg lg-azure"></i>访问量</span>
                <span><i class="lg lg-aqua"></i>解析量</span>
              </div>
            </div>
            <div class="chart-wrap">
              <DashTrend :days="sliceTrend.days" :visits="sliceTrend.visits" :parses="sliceTrend.parses" />
            </div>
          </div>
        </div>

        <DashFeed :items="recent" />
      </section>

      <!-- ============ ④ 底部：平台占比 ｜ TOP 5 ｜ 系统状态 ============ -->
      <section class="bot">
        <div class="glassbox panel">
          <div class="in">
            <div class="p-head">
              <h2 class="p-title">
                <i class="p-ic" aria-hidden="true"><ChartPie :size="14" weight="bold" /></i>
                平台解析占比
              </h2>
            </div>
            <DashPlatforms :platforms="platforms" />
          </div>
        </div>

        <div class="glassbox panel">
          <div class="in">
            <div class="p-head">
              <h2 class="p-title">
                <i class="p-ic" aria-hidden="true"><UserIcon :size="14" weight="bold" /></i>
                解析排行 TOP 5
              </h2>
              <RouterLink class="p-more" to="/settings">
                查看全部 <CaretRight :size="11" aria-hidden="true" />
              </RouterLink>
            </div>

            <div class="rank" role="table" aria-label="解析排行前五名">
              <div class="tb-head" role="row">
                <span class="ta-c">排名</span><span class="ta-c">用户</span><span class="ta-c">解析数量</span><span class="ta-c">占比</span><span class="ta-r">涨跌</span>
              </div>
              <p v-if="!rankRows.length" class="empty">暂无解析数据</p>
              <div
                v-for="(u, i) in rankRows"
                :key="u.username"
                class="tb-row"
                role="row"
                :class="{ m1: i === 0, m2: i === 1, m3: i === 2 }"
                :style="{ '--h': u.hue }"
              >
                <span class="medal">{{ String(i + 1).padStart(2, "0") }}</span>
                <span class="who">
                  <span class="ava" :style="{ background: `hsl(${u.hue} 55% 42%)` }" aria-hidden="true">
                    {{ u.username.slice(0, 1).toUpperCase() }}
                  </span>
                  <span class="rname">{{ u.username }}</span>
                </span>
                <span class="rcnt ta-c">{{ u.parse_count }}</span>
                <span class="rbar">
                  <em>{{ u.pct }}%</em>
                  <span class="track" aria-hidden="true">
                    <i :style="{ width: rankMax ? Math.max(6, (u.parse_count / rankMax) * 100) + '%' : '0' }"></i>
                  </span>
                </span>
                <span class="rtr ta-r" :class="u.delta_pct > 0 ? 'up' : u.delta_pct < 0 ? 'down' : 'flat'">
                  <template v-if="u.delta_pct == null">—</template>
                  <template v-else>{{ u.delta_pct > 0 ? "↑" : u.delta_pct < 0 ? "↓" : "→" }} {{ Math.abs(u.delta_pct) }}%</template>
                </span>
              </div>
            </div>
          </div>
        </div>

        <DashStatus :system="system" :kpis="kpis || {}" :online-users="onlineUsers" :health-ms="healthMs" />
      </section>
    </main>

    <!-- 页脚品牌带（参考稿同款）：两侧渐隐细线夹品牌文案 -->
    <footer class="bd-foot">VideoHub · 视频解析与管理平台</footer>
  </div>
</template>

<style scoped>
/* ============================================================
   座舱调色板 —— 暗色为默认，浅色由 html[data-theme="light"] 覆盖。
   所有子组件（DashTrend / DashPlatforms / DashSpark / DashFeed / DashStatus）
   都读这套变量，因此切换主题时整块看板（含图表）一起换肤。
   布局原语 / 徽章 / 分段开关在 src/styles/dashboard.css。
   ============================================================ */
.board {
  /* --- 底与面板（v6 HUD：更深的夜空蓝黑 + 底部地平线光晕） --- */
  --bd-ink: #030716;
  --bd-grid: rgba(90, 140, 230, 0.055);
  --bd-aura-1: rgba(37, 99, 235, 0.2);
  --bd-aura-2: rgba(56, 189, 248, 0.1);
  --bd-card-a: rgba(13, 24, 48, 0.78);   /* 半透明深蓝，糊出底层 aura 光斑 */
  --bd-card-b: rgba(6, 12, 26, 0.66);
  --bd-ln-inner: rgba(148, 183, 255, 0.1); /* inset 顶光：玻璃的「厚度」 */
  --bd-solid: #0a1122;                    /* 面板内实底（轴点 / spark 端点） */
  --bd-rail: rgba(148, 163, 184, 0.14);   /* 轨道底 / 空环形底 */
  --bd-fill-soft: rgba(70, 120, 220, 0.08);
  --bd-hover: rgba(70, 120, 220, 0.1);
  --bd-dotgrid: rgba(90, 140, 230, 0.1);

  /* --- 描边 / 景深 / HUD 辉光（角标与外圈光晕，浅色档需同步覆写） --- */
  --bd-ln: rgba(64, 140, 255, 0.26);
  --bd-ln-hi: rgba(96, 175, 255, 0.52);
  --bd-hud: rgba(96, 186, 255, 0.85);
  --bd-hud-glow: rgba(45, 120, 255, 0.5);
  --bd-shadow-c: rgba(1, 4, 12, 0.7);
  --bd-shadow-hi-c: rgba(1, 4, 12, 0.86);

  /* --- 文字三档 --- */
  --bd-t1: #eef3fb;
  --bd-t2: #97a5bc;
  --bd-t3: #64748b;

  /* --- 信号色谱（访问=azure 蓝 / 解析=aqua 青 / 状态 ok 绿） --- */
  --bd-aqua: #45e0c0;
  --bd-azure: #4d8dff;
  --bd-ok: #34d399;
  --bd-amber: #ffb454;
  --bd-rose: #ff7a8a;

  /* --- 排行徽章 · 金属三档 --- */
  --bd-gold-grad: linear-gradient(150deg, #ffe3a3 0%, #f0a92e 55%, #c97e12 100%);
  --bd-silver-grad: linear-gradient(150deg, #f2f6fc 0%, #b9c4d6 55%, #8d9ab0 100%);
  --bd-bronze-grad: linear-gradient(150deg, #f0bd93 0%, #c98a52 55%, #a06835 100%);

  /* --- 环形图回退冷色阶（品牌色未收录的平台） --- */
  --bd-plat-1: #45e0c0;
  --bd-plat-2: #3fc8e8;
  --bd-plat-3: #5aa9ff;
  --bd-plat-4: #7c93d8;
  --bd-plat-5: #6b7a93;
  --bd-plat-6: #55606f;

  /* --- 图表（DashTrend 经 getComputedStyle 读取，canvas 无法直接用 var） --- */
  --bd-chart-axis: rgba(148, 163, 184, 0.16);
  --bd-chart-split: rgba(148, 163, 184, 0.06);
  --bd-chart-label: #64748b;
  --bd-chart-cross: rgba(148, 163, 184, 0.4);
  --bd-tip-bg: rgba(8, 13, 26, 0.94);
  --bd-tip-line: rgba(148, 163, 184, 0.2);
  --bd-area-0: rgba(69, 224, 192, 0.3);
  --bd-area-1: rgba(69, 224, 192, 0.1);
  --bd-area-2: rgba(69, 224, 192, 0);
  --bd-line-glow: rgba(69, 224, 192, 0.65);
  --bd-azure-area-0: rgba(77, 141, 255, 0.34);
  --bd-azure-area-1: rgba(77, 141, 255, 0.11);
  --bd-azure-area-2: rgba(77, 141, 255, 0);
  --bd-azure-glow: rgba(77, 141, 255, 0.55);

  position: relative;
  /* 固定视口高：导航(64) + 页脚(52) 之外全部交给看板，内部用分数行网格分配 */
  height: calc(100dvh - var(--nav-h, 64px) - 52px);
  min-height: 760px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 14px 10px;
  color: var(--bd-t1);
  overflow: hidden;
  background-image:
    linear-gradient(var(--bd-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--bd-grid) 1px, transparent 1px),
    radial-gradient(1100px 320px at 50% 112%, rgba(37, 99, 235, 0.3), transparent 68%),
    radial-gradient(1240px 620px at 42% -14%, var(--bd-aura-1), transparent 62%),
    radial-gradient(900px 520px at 102% -4%, var(--bd-aura-2), transparent 60%),
    linear-gradient(168deg, #0a1124 0%, #050a1c 48%, #030716 100%);
  background-size: 34px 34px, 34px 34px, auto, auto, auto, auto;
  background-color: var(--bd-ink);
}

/* ================= 浅色档 =================
 * 面板转白、文字转近黑、信号色整体加深一档保证白底可读（≥ 4.5:1） */
html[data-theme="light"] .board {
  --bd-ink: #eef1f6;
  --bd-grid: rgba(15, 23, 32, 0.035);
  --bd-aura-1: rgba(37, 99, 235, 0.08);
  --bd-aura-2: rgba(13, 148, 136, 0.06);
  --bd-card-a: rgba(255, 255, 255, 0.8);
  --bd-card-b: rgba(255, 255, 255, 0.58);
  --bd-ln-inner: rgba(255, 255, 255, 0.8);
  --bd-solid: #ffffff;
  --bd-rail: rgba(15, 23, 32, 0.1);
  --bd-fill-soft: rgba(15, 23, 32, 0.045);
  --bd-hover: rgba(15, 23, 32, 0.045);
  --bd-dotgrid: rgba(15, 23, 32, 0.11);

  --bd-ln: rgba(15, 23, 32, 0.1);
  --bd-ln-hi: rgba(15, 23, 32, 0.26);
  --bd-hud: rgba(37, 99, 235, 0.55);
  --bd-hud-glow: rgba(37, 99, 235, 0.14);
  --bd-shadow-c: rgba(16, 24, 40, 0.28);
  --bd-shadow-hi-c: rgba(16, 24, 40, 0.4);

  --bd-t1: #0f1720;
  --bd-t2: #4b5563;
  --bd-t3: #8a94a3;

  --bd-aqua: #0d9488;
  --bd-azure: #2563eb;
  --bd-ok: #059669;
  --bd-amber: #b45309;
  --bd-rose: #dc2626;

  --bd-gold-grad: linear-gradient(150deg, #ffd98a 0%, #e79a1d 55%, #b56f0c 100%);
  --bd-silver-grad: linear-gradient(150deg, #e8edf5 0%, #a9b6ca 55%, #7e8ba0 100%);
  --bd-bronze-grad: linear-gradient(150deg, #e5a96f 0%, #b97a42 55%, #8f5a2c 100%);

  --bd-plat-1: #0d9488;
  --bd-plat-2: #0891b2;
  --bd-plat-3: #2563eb;
  --bd-plat-4: #4f46e5;
  --bd-plat-5: #64748b;
  --bd-plat-6: #94a3b8;

  --bd-chart-axis: rgba(15, 23, 32, 0.18);
  --bd-chart-split: rgba(15, 23, 32, 0.07);
  --bd-chart-label: #8a94a3;
  --bd-chart-cross: rgba(15, 23, 32, 0.35);
  --bd-tip-bg: rgba(255, 255, 255, 0.97);
  --bd-tip-line: rgba(15, 23, 32, 0.14);
  --bd-area-0: rgba(13, 148, 136, 0.2);
  --bd-area-1: rgba(13, 148, 136, 0.07);
  --bd-area-2: rgba(13, 148, 136, 0);
  --bd-line-glow: rgba(13, 148, 136, 0.32);
  --bd-azure-area-0: rgba(37, 99, 235, 0.2);
  --bd-azure-area-1: rgba(37, 99, 235, 0.07);
  --bd-azure-area-2: rgba(37, 99, 235, 0);
  --bd-azure-glow: rgba(37, 99, 235, 0.28);
}

/* ---------- ① 指令栏 ---------- */
.bd-head {
  flex-shrink: 0;
  height: 52px;
  padding: 0 12px 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  /* 覆盖 glassbox 的 flex 拉伸语义（head 是横条不是面板内容列） */
  --accent: color-mix(in srgb, var(--bd-azure) 55%, transparent);
}
.bd-brand { display: flex; align-items: center; gap: 11px; min-width: 0; }
/* 品牌 Logo：参考稿同款玻璃播放按钮 —— 亮蓝渐变玻璃底 + 顶部反光 + 内嵌顶光/底影 + 外圈辉光 */
.bd-mark {
  position: relative;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 9px;
  color: #fff;
  background:
    radial-gradient(130% 100% at 28% 14%, rgba(255, 255, 255, 0.42), transparent 48%),
    linear-gradient(152deg, #61a1ff 0%, #2f6ef2 55%, #1e4fd6 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.5),
    inset 0 -1px 0 rgba(9, 20, 60, 0.35),
    inset 0 0 0 1px rgba(130, 170, 255, 0.5),
    0 8px 20px -8px color-mix(in srgb, var(--bd-azure) 90%, transparent),
    0 0 28px -5px color-mix(in srgb, var(--bd-azure) 75%, transparent);
}
/* 顶部玻璃反光：盖在播放三角形上方，形成「玻璃罩住内容」的层次 */
.bd-mark::after {
  content: "";
  position: absolute;
  top: 1.5px;
  left: 3px;
  right: 3px;
  height: 42%;
  border-radius: 7px 7px 11px 11px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.4), rgba(255, 255, 255, 0));
  pointer-events: none;
}
.bd-mark :deep(svg) { margin-left: 1px; filter: drop-shadow(0 1px 1.5px rgba(10, 25, 70, 0.45)); }
.bd-wordmark { font-size: 15px; font-weight: 800; letter-spacing: 0.08em; color: var(--bd-t1); white-space: nowrap; }
.bd-crumb {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: 13px;
  border-left: 1px solid var(--bd-ln-hi);
  white-space: nowrap;
}
.bd-crumb b { font-size: 10.5px; font-weight: 650; letter-spacing: 0.24em; color: var(--bd-t2); }
.bd-crumb i { font-style: normal; font-size: 10px; letter-spacing: 0.1em; color: var(--bd-t3); }

.bd-actions { display: flex; align-items: center; gap: 9px; font-size: 12px; color: var(--bd-t2); }

.bd-live {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 27px;
  padding: 0 12px 0 11px;
  border-radius: var(--r-pill, 999px);
  background: color-mix(in srgb, var(--bd-ok) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--bd-ok) 30%, transparent);
  color: var(--bd-ok);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.bd-live.bad {
  background: color-mix(in srgb, var(--bd-rose) 9%, transparent);
  border-color: color-mix(in srgb, var(--bd-rose) 32%, transparent);
  color: var(--bd-rose);
}
.bd-dot {
  position: relative;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--bd-ok);
  box-shadow: 0 0 10px var(--bd-ok);
}
.bd-live.bad .bd-dot { background: var(--bd-rose); box-shadow: 0 0 10px var(--bd-rose); }

.bd-clock {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--bd-t1);
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 14px color-mix(in srgb, var(--bd-azure) 45%, transparent);
}
.bd-clock .dt { font-style: normal; font-size: 11.5px; font-weight: 500; color: var(--bd-t2); }

.bd-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 29px;
  padding: 0 13px;
  border: 1px solid var(--bd-ln);
  border-radius: 8px;
  background: var(--bd-fill-soft);
  color: var(--bd-t2);
  font: 500 12px/1 var(--font-sans);
  cursor: pointer;
  transition: color 0.16s ease, border-color 0.16s ease, background 0.16s ease;
}
.bd-btn:hover {
  color: var(--bd-t1);
  border-color: var(--bd-ln-hi);
  background: var(--bd-hover);
}
.bd-btn:disabled { opacity: 0.5; cursor: default; }
.bd-btn.accent {
  color: var(--bd-azure);
  border-color: color-mix(in srgb, var(--bd-azure) 38%, transparent);
  background: color-mix(in srgb, var(--bd-azure) 8%, transparent);
}

.bd-user {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 33px;
  padding: 0 10px 0 5px;
  margin-left: 3px;
  border-radius: 999px;
  border: 1px solid var(--bd-ln);
  background: var(--bd-fill-soft);
  color: var(--bd-t1);
  font-size: 12.5px;
  font-weight: 600;
  text-decoration: none;
  transition: border-color 0.16s ease, background 0.16s ease;
}
.bd-user:hover { border-color: var(--bd-ln-hi); background: var(--bd-hover); }
.bd-ava {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  color: #fff;
  background: linear-gradient(140deg, #4d8dff 0%, #2563eb 100%);
}
.bd-user :deep(svg) { color: var(--bd-t3); }
.bd-uname { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ---------- 主列 ---------- */
.bd-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ---------- ② KPI 卡片行 ---------- */
.spine {
  flex-shrink: 0;
  height: 114px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.seg-card { min-width: 0; }
.seg-in {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 12px 16px 11px;
}
/* 右上角拖点：纯装饰（参考稿同款），不承载交互 */
.grip {
  position: absolute;
  top: 9px;
  right: 9px;
  color: var(--bd-t3);
  opacity: 0.45;
  pointer-events: none;
}
.s-top { display: flex; align-items: center; gap: 9px; min-width: 0; }
/* KPI 图标芯片 v3（v6 HUD）：圆角方形高辉光底 —— 参考稿同款科技蓝发光方块：
 * 亮蓝渐变底 + backdrop blur 磨砂 + 全周受光描边 + 外圈强辉光；字形亮白 */
.s-ico {
  position: relative;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 10px;
  color: #eaf2ff;
  background:
    radial-gradient(120% 95% at 30% 20%, rgba(255, 255, 255, 0.38), transparent 55%),
    linear-gradient(165deg,
      color-mix(in srgb, var(--bd-azure) 55%, transparent) 0%,
      color-mix(in srgb, var(--bd-azure) 22%, transparent) 55%,
      color-mix(in srgb, var(--bd-azure) 8%, transparent) 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    inset 0 -1px 0 rgba(8, 18, 45, 0.3),
    inset 0 0 0 1px rgba(168, 200, 255, 0.26),
    0 0 24px -6px color-mix(in srgb, var(--bd-azure) 90%, transparent);
  -webkit-backdrop-filter: blur(6px) saturate(1.3);
  backdrop-filter: blur(6px) saturate(1.3);
}
/* 顶光：与模块图标芯片同一套玻璃语言 */
.s-ico::after {
  content: "";
  position: absolute;
  top: 2px;
  left: 4px;
  right: 4px;
  height: 40%;
  border-radius: 7px 7px 10px 10px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.34), rgba(255, 255, 255, 0));
  pointer-events: none;
}
/* 浅色档：玻璃底已随 --bd-azure 转深蓝，字形改回深色信号色保证白底可读 */
html[data-theme="light"] .s-ico {
  color: #1d4ed8;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    inset 0 -1px 0 rgba(15, 23, 32, 0.05),
    inset 0 0 0 1px color-mix(in srgb, var(--bd-azure) 26%, transparent),
    0 0 16px -6px color-mix(in srgb, var(--bd-azure) 55%, transparent);
}
.s-lbl {
  font-size: 12.5px;
  font-weight: 550;
  color: var(--bd-t1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.s-live {
  flex-shrink: 0;
  height: 16px;
  padding: 0 6px;
  border-radius: 5px;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--bd-aqua);
  background: color-mix(in srgb, var(--bd-aqua) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--bd-aqua) 34%, transparent);
}
.s-num {
  display: block;
  margin-top: 4px;
  padding-left: 1px;
  line-height: 1.05;
  letter-spacing: -0.02em;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
  color: var(--bd-t1);
  /* v6.1 小数据打磨：数字加大 + 微辉光，小数值也有大屏冲击力 */
  font-size: clamp(27px, 2.5vw, 37px);
  text-shadow: 0 0 18px color-mix(in srgb, var(--bd-azure) 30%, transparent);
}
.s-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: auto;
  min-width: 0;
  /* 卡片里的 sparkline 只做形态度量，压到 20px 高 */
  --spark-h: 20px;
}
.s-foot > :deep(.spark) { flex: 1; min-width: 40px; }

.on-line {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 550;
  color: var(--bd-t2);
  white-space: nowrap;
}
.on-line i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bd-ok);
  box-shadow: 0 0 8px var(--bd-ok);
}
.s-rail {
  flex: 1;
  min-width: 40px;
  height: 4px;
  border-radius: 2px;
  background: var(--bd-rail);
  overflow: hidden;
}
.s-rail i {
  display: block;
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--bd-azure), var(--bd-aqua));
  transition: width 0.8s var(--ease-out, ease-out);
}

/* 骨架占位（贴合 KPI 卡，避免空壳） */
.seg-card .vh-skeleton { display: block; background: var(--bd-rail); border-radius: 6px; }
.seg-card .vh-skeleton::after {
  background: linear-gradient(90deg, transparent, var(--bd-dotgrid), transparent);
}
.sk-i { width: 36px; height: 36px; border-radius: 10px !important; }
.sk-n { width: 56px; height: 28px; margin-top: 8px; }
.sk-c { width: 92px; height: 16px; margin-top: auto; }

/* ---------- ③ 中部：趋势 + 动态 ---------- */
.mid {
  flex: 1.16;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 12px;
}
/* 主视觉面板：顶光染 azure */
.panel.hero { --accent: color-mix(in srgb, var(--bd-azure) 55%, transparent); }
.tr-sub {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-shrink: 0;
  margin: -3px 0 4px;
}
.tr-cap { font-size: 11px; color: var(--bd-t3); }
.legend { display: flex; align-items: center; gap: 14px; font-size: 11px; color: var(--bd-t2); }
.legend .lg { display: inline-block; width: 14px; height: 2px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }
.lg-azure { background: var(--bd-azure); box-shadow: 0 0 8px color-mix(in srgb, var(--bd-azure) 65%, transparent); }
.lg-aqua { background: var(--bd-aqua); box-shadow: 0 0 10px var(--bd-aqua); }

.chart-wrap { position: relative; flex: 1; min-height: 100px; }

/* ---------- ④ 底部三栏 ---------- */
.bot {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.16fr) minmax(0, 1.04fr);
  gap: 12px;
}

/* ---------- 解析排行 TOP 5（v8.1 对齐 DashPlatforms 行内排版：
   占比条右跟百分比、趋势列「涨跌字 + 曲线」同行，行距/分割线同款） ---------- */
.rank { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 9px; }
.tb-head {
  flex-shrink: 0;
  display: grid;
  /* 纵列节奏（v8.2 + 2026-09-15 涨跌列去形态曲线后收窄） */
  grid-template-columns: 30px minmax(0, 0.8fr) 48px minmax(0, 1.35fr) 64px;
  gap: 11px;
  padding: 0 6px 12px;
  border-bottom: 1px solid var(--bd-ln);
  font-size: 10px;
  color: var(--bd-t3);
}
.ta-c { text-align: center; }
.ta-r { text-align: right; }
.tb-row {
  flex: 1 1 0;
  min-height: 0;
  display: grid;
  grid-template-columns: 30px minmax(0, 0.8fr) 48px minmax(0, 1.35fr) 64px;
  gap: 11px;
  align-items: center;
  padding: 0 6px;
  border-radius: 8px;
  font-size: 12.5px;
  transition: background 0.18s ease;
}
/* v8 列表语言：行间极细科技分割线 */
.tb-row + .tb-row {
  border-top: 1px solid color-mix(in srgb, var(--bd-ln) 55%, transparent);
}
.tb-row:hover { background: var(--bd-hover); }
/* 用户列表头相对列中心左移一点点（padding 挤压居中文本），与下方居中的用户名对齐 */
.tb-head span:nth-child(2) { padding-right: 14px; }
/* 用户列内容在列内居中，与「用户」表头对齐（v8.3） */
.who { display: flex; align-items: center; justify-content: center; gap: 9px; min-width: 0; }
.medal {
  display: grid;
  place-items: center;
  justify-self: center;
  width: 23px;
  height: 23px;
  flex-shrink: 0;
  border-radius: 7px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 700;
  background: var(--bd-fill-soft);
  border: 1px solid var(--bd-ln);
  color: var(--bd-t3);
}
/* 金 / 银 / 铜三档金属渐变徽章：仅前三名，其余保持中性 */
.tb-row.m1 .medal {
  background: var(--bd-gold-grad);
  border-color: color-mix(in srgb, var(--bd-amber) 65%, transparent);
  color: #2a1a02;
  box-shadow: 0 0 18px -6px var(--bd-amber), inset 0 1px 0 rgba(255, 255, 255, 0.35);
}
.tb-row.m2 .medal {
  background: var(--bd-silver-grad);
  border-color: rgba(185, 196, 214, 0.55);
  color: #232c3a;
  box-shadow: 0 0 14px -7px #b9c4d6, inset 0 1px 0 rgba(255, 255, 255, 0.4);
}
.tb-row.m3 .medal {
  background: var(--bd-bronze-grad);
  border-color: rgba(201, 138, 82, 0.55);
  color: #2a1608;
  box-shadow: 0 0 14px -7px #c98a52, inset 0 1px 0 rgba(255, 255, 255, 0.3);
}
.ava {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border-radius: 50%;
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  /* v8：头像外圈受光环 + 同色相微辉光（--h 由行内样式按用户注入） */
  box-shadow:
    inset 0 0 0 1px hsl(var(--h) 70% 62% / 0.4),
    0 0 10px -2px hsl(var(--h) 70% 55% / 0.75);
}
.rname {
  min-width: 0;
  color: var(--bd-t1);
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rcnt {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 650;
  color: var(--bd-t1);
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 12px color-mix(in srgb, var(--bd-azure) 30%, transparent);
}
/* 占比列：进度条 + 右侧百分比同行（同 DashPlatforms 的 barrow 结构） */
.rbar {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.rbar .track {
  position: relative;
  flex: 1;
  min-width: 0;
  height: 5px;
  border-radius: 2.5px;
  background: var(--bd-rail);
  overflow: hidden;
}
.rbar .track i {
  position: absolute;
  inset: 0 auto 0 0;
  display: block;
  border-radius: 2.5px;
  /* v8：占比条改用户色相渐变 + 同色辉光（同 DashPlatforms 段色条语言） */
  background: linear-gradient(90deg, hsl(var(--h) 70% 55% / 0.5), hsl(var(--h) 72% 60%));
  box-shadow: 0 0 8px -1px hsl(var(--h) 72% 55% / 0.8);
  transition: width 0.8s var(--ease-out, ease-out);
}
.rbar em {
  flex-shrink: 0;
  width: 38px;
  font-style: normal;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--bd-t2);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
/* 涨跌列：今日 vs 昨日同比（后端真实统计） */
.rtr {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.rtr.up { color: var(--bd-ok); }
.rtr.down { color: var(--bd-rose); }
.rtr.flat { color: var(--bd-t3); font-weight: 400; }

/* 首次加载失败 */
.bd-empty { flex: 1; display: grid; place-content: center; justify-items: center; gap: 12px; color: var(--bd-t2); }
.bd-empty p { margin: 0; font-size: 13px; }

/* ---------- 页脚品牌带（参考稿同款）：两侧渐隐线夹文案 ---------- */
.bd-foot {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  height: 18px;
  font-size: 10.5px;
  letter-spacing: 0.14em;
  color: var(--bd-t3);
  white-space: nowrap;
}
.bd-foot::before,
.bd-foot::after {
  content: "";
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--bd-ln-hi), transparent);
}
.bd-foot::after { transform: scaleX(-1); }

/* ---------- 关键动效 ---------- */
@keyframes bd-ring { 0% { transform: scale(0.55); opacity: 0.95; } 70%, 100% { transform: scale(1.55); opacity: 0; } }
@keyframes bd-spin { to { transform: rotate(360deg); } }
@keyframes bd-blip { 0%, 100% { opacity: 1; } 50% { opacity: 0.28; } }

.bd-dot::after {
  content: "";
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1px solid color-mix(in srgb, var(--bd-ok) 65%, transparent);
}
.bd-live.bad .bd-dot::after { border-color: color-mix(in srgb, var(--bd-rose) 60%, transparent); }

@media (prefers-reduced-motion: no-preference) {
  .bd-dot { animation: bd-blip 2.4s ease-in-out infinite; }
  .bd-dot::after { animation: bd-ring 2.2s ease-out infinite; }
  .bd-ic.spin { animation: bd-spin 0.9s linear infinite; }
}

/* ============================================================
   降级：视口不够高 / 栅格断到单列时，放弃固定高，回到自然流。
   ============================================================ */
@media (max-height: 900px) and (min-width: 1281px) {
  .spine { height: 104px; }
  .seg-in { padding: 10px 16px 9px; }
}

@media (max-height: 820px) {
  .board { height: auto; overflow: visible; }
  .spine { height: auto; }
  .seg-in { min-height: 100px; }
  .mid, .bot { min-height: 0; }
  .chart-wrap { min-height: 190px; }
}

@media (max-width: 1280px) {
  .board { height: auto; overflow: visible; }
  .spine { height: auto; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .seg-in { min-height: 100px; }
  .mid { grid-template-columns: minmax(0, 1fr); }
  .bot { grid-template-columns: minmax(0, 1fr); }
  .chart-wrap { min-height: 220px; }
}

@media (max-width: 900px) {
  .spine { grid-template-columns: minmax(0, 1fr); }
  .bd-crumb { display: none; }
  .bd-live { display: none; }
}

/* 全屏大屏：fixed 铺满视口，z-index 高于导航 / 扫描光 */
.board.full {
  position: fixed;
  inset: 0;
  z-index: 999;
  height: 100dvh;
  min-height: 0;
  border-radius: 0;
  overflow: hidden;
  padding: 14px 18px 18px;
}
</style>
