<script setup>
/**
 * DashStatus · 系统状态面板
 *
 * 五行组件状态 + 每行三项真实指标。所有数值都来自可实测的数据源，
 * 不虚构「可用率 / 12.4k/min」这类没有采集出路的装饰性指标：
 *
 *  · API 接口   —— health 探针往返延迟（浏览器实测）· 进程运行时长 · 事件速率（近 60s
 *                  写入的访问日志事件数；仅 visit/login/register/parse 四类动作会计入，
 *                  非全部 API 请求）
 *  · 解析引擎   —— 今日 / 近7日（滚动 7×24h，非自然周）/ 累计解析操作数（AccessLog 口径）
 *  · 数据库     —— SELECT 1 探针延迟 · 用户总数 · 今日事件数
 *  · Storage    —— SQLite 库文件体积 · 解析记录存量（Record 口径，删除记录会下降）· 字幕数
 *  · CDN 加速   —— 接入方式（本次请求是否经 Cloudflare 隧道头到达）· 累计访问 · 在线用户
 *
 * 每行徽章只渲染「有真实信号」的行：API = 浏览器 health 探针成败、
 * 数据库 = 本次看板请求刚跑通的 SELECT 1、Storage = 库体积读取成功；
 * 解析引擎 / CDN 没有独立探针，不渲染徽章，不拿「请求成功」冒充逐组件探测。
 *
 * v8 HUD 视觉层（同 DashPlatforms 设计语言）：行首竖刻度条锚定读数位、
 * 行间极细分割线、读数 azure 微辉光、标题呼吸灯加扩散环（reduced-motion 静止）。
 */
import { computed } from "vue"
import { PhShieldCheck } from "@phosphor-icons/vue"

const props = defineProps({
  /** /admin/dashboard 的 system 字段（真实测量值） */
  system: { type: Object, default: null },
  /** /admin/dashboard 的 kpis 字段（复用其计数，避免重复统计） */
  kpis: { type: Object, default: () => ({}) },
  /** 在线用户数（近 15 分钟活跃，来自同一响应顶层） */
  onlineUsers: { type: Number, default: 0 },
  /** 浏览器实测的 /api/health 往返延迟（ms），未测得时 null */
  healthMs: { type: Number, default: null },
})

/** 运行时长：60 分钟以内显示分钟，以上显示「xh ym」 */
function fmtUptime(minutes) {
  if (minutes == null) return "—"
  if (minutes < 60) return `${minutes}m`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

const rows = computed(() => {
  const s = props.system
  const k = props.kpis || {}
  if (!s) return []
  return [
    {
      name: "API 接口",
      /* 徽章 = 浏览器实测的 /api/health 探针成败（与响应时间同源） */
      badge: props.healthMs != null ? { text: "在线", cls: "ok" } : { text: "异常", cls: "bad" },
      stats: [
        { v: props.healthMs != null ? `${props.healthMs}ms` : "—", l: "响应时间" },
        { v: fmtUptime(s.uptime_minutes), l: "运行时长" },
        { v: `${s.events_per_min}/min`, l: "事件速率" },
      ],
    },
    {
      name: "解析引擎",
      badge: null, // 无独立探针，不渲染徽章
      stats: [
        { v: k.today_parses ?? 0, l: "今日解析" },
        { v: s.week_parses ?? 0, l: "近7日解析" },
        { v: k.total_parses ?? 0, l: "累计解析" },
      ],
    },
    {
      name: "数据库",
      /* 徽章 = 本次看板请求刚执行过的 SELECT 1 探针（能渲染本面板即已跑通） */
      badge: { text: "在线", cls: "ok" },
      stats: [
        { v: s.db_latency_ms != null ? `${s.db_latency_ms}ms` : "—", l: "查询延迟" },
        { v: k.total_users ?? 0, l: "用户总数" },
        { v: s.today_events ?? 0, l: "今日事件" },
      ],
    },
    {
      name: "Storage 存储",
      /* 徽章 = 库体积读取成功（非 SQLite 后端取不到体积，不冒充在线） */
      badge: s.db_size_mb != null ? { text: "在线", cls: "ok" } : null,
      stats: [
        { v: s.db_size_mb != null ? `${s.db_size_mb}MB` : "—", l: "数据文件" },
        { v: k.total_records ?? 0, l: "解析记录" },
        { v: s.captions ?? 0, l: "字幕" },
      ],
    },
    {
      name: "CDN 加速",
      badge: null, // 隧道/直连是事实展示（见「接入方式」），没有 CDN 健康探针
      stats: [
        { v: s.via_tunnel ? "隧道" : "直连", l: "接入方式" },
        { v: k.total_visits ?? 0, l: "累计访问" },
        { v: props.onlineUsers, l: "在线用户" },
      ],
    },
  ]
})
</script>

<template>
  <div class="glassbox panel status-panel">
    <div class="in">
      <div class="p-head">
        <h2 class="p-title">
          <i class="p-ic aqua" aria-hidden="true"><PhShieldCheck :size="14" weight="bold" /></i>
          系统状态
        </h2>
        <span class="st-live" aria-hidden="true"><i></i></span>
      </div>

      <div class="rows">
        <div v-for="r in rows" :key="r.name" class="row">
          <span class="dot" aria-hidden="true"></span>
          <span class="nm">{{ r.name }}</span>
          <!-- 固定宽槽位：无徽章的行也占位，保证各行读数列对齐 -->
          <span class="bslot">
            <span v-if="r.badge" class="badge" :class="r.badge.cls">{{ r.badge.text }}</span>
          </span>
          <span class="stats">
            <span v-for="st in r.stats" :key="st.l" class="st">
              <b>{{ st.v }}</b>
              <span>{{ st.l }}</span>
            </span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* v8 HUD 列表语言：行首刻度条 + 极细分割线 + 读数辉光（同 DashPlatforms/TOP5） */
.status-panel {
  --pad-panel: 13px 14px 11px;
  min-height: 0;
}

/* 标题行右侧的呼吸灯：面板存活的可视暗示（外圈扩散环同 KPI 指示灯语言） */
.st-live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.st-live i {
  position: relative;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bd-ok);
  box-shadow: 0 0 8px var(--bd-ok);
}

.rows {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.row {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 6px 0 7px;
  border-radius: 8px;
  transition: background 0.16s ease;
}
.row:hover { background: var(--bd-hover); }
/* 行间极细分割线（v8 列表语言） */
.row + .row {
  border-top: 1px solid color-mix(in srgb, var(--bd-ln) 55%, transparent);
}
/* 行首 HUD 竖刻度条：给每行一个「仪表读数位」的锚点 */
.row::before {
  content: "";
  flex-shrink: 0;
  width: 3px;
  height: 13px;
  border-radius: 1.5px;
  background: linear-gradient(180deg, var(--bd-hud), color-mix(in srgb, var(--bd-hud) 20%, transparent));
}

.dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--bd-ok);
  box-shadow: 0 0 8px var(--bd-ok);
}
.nm {
  flex-shrink: 0;
  width: 78px;
  font-size: 12px;
  font-weight: 550;
  color: var(--bd-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bslot {
  flex-shrink: 0;
  width: 46px;
  display: inline-flex;
  justify-content: flex-start;
}

.stats {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}
.st {
  min-width: 0;
  text-align: right;
  line-height: 1.15;
}
.st b {
  display: block;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 650;
  color: var(--bd-t1);
  font-variant-numeric: tabular-nums;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  /* v8：读数 azure 微辉光，呼应 KPI 大数字 */
  text-shadow: 0 0 12px color-mix(in srgb, var(--bd-azure) 30%, transparent);
}
.st span {
  display: block;
  font-size: 9px;
  letter-spacing: 0.04em;
  color: var(--bd-t3);
  white-space: nowrap;
}

@media (max-width: 1500px) {
  .nm { width: 66px; }
}

/* 动效收口：系统减少动态时静止 */
@media (prefers-reduced-motion: no-preference) {
  .st-live i::after {
    content: "";
    position: absolute;
    inset: -4px;
    border-radius: 50%;
    border: 1px solid color-mix(in srgb, var(--bd-ok) 65%, transparent);
    animation: st-ring 2.2s ease-out infinite;
  }
}
@keyframes st-ring {
  0% { transform: scale(0.55); opacity: 0.95; }
  70%, 100% { transform: scale(1.55); opacity: 0; }
}
</style>
