<script setup>
/**
 * DashPlatforms · 平台解析占比（v8「HUD 多层环形仪表」）
 *
 * 左：多层半透明发光环形图（纯 SVG，无图表库）——
 *   外圈细密科技刻度（72 根，主刻度每 30°）+ HUD 角括弧/十字标 + 外沿呼吸粒子；
 *   主环 = 段色 stroke 弧（core 17px）+ 同弧加宽低透明 halo（30px）+ 内侧细 echo 环，
 *   三层叠加出「多层半透明发光」厚度感；旋转层：虚线内环（64s）、雷达扫描扇面（7.5s）、
 *   双轨道动态光点（13s / 21s 逆向）；环心 = 总记录数大数字（浅蓝辉光）+「解析记录」。
 *   大段（≥8%）外沿引出 HUD 标注（色点 + 细引线 + 百分比），小段不标避免拥挤。
 * 右：纵向数据列表 —— LOGO / 名称 / 占比进度条（右侧标百分比）/ 解析数量 / 涨跌，
 *   行间极细分割线，与主环悬停联动（dim 非活动段与标注）。
 *   数据：后端已按展示口径返回（总量降序前 5 + 其余合并 other，合并段涨跌用
 *   今日/昨日窗口计数重算），本组件只做展示映射、不再二次合并——前端没有窗口
 *   计数，对百分比做加法在数学上不成立。count = 该平台当前解析记录存量（Record
 *   口径，用户删除记录会下降），环心总数同口径、标注「解析记录」；涨跌 = 该平台
 *   今日新增记录 vs 昨日新增记录，均为后端真实统计，无伪随机形态曲线。
 *
 * 段色：固定身份映射（品牌色仅在不撞色时保留，youku 蓝→琥珀等替代同 v6），
 * 明暗主题通用不随 --bd-* 换肤（同 ParseHome 图标先例）；回退色阶走 --bd-plat-*。
 *
 * 几何：viewBox 260 + C=130；弧段间留 ~1.6° 缺口；单平台时弧公式自然画近整圆。
 * 所有动效包在 prefers-reduced-motion: no-preference 内。
 *
 * PLATFORM_NAMES / PLATFORM_ICONS / SEGMENT_COLORS 均为源码内静态常量
 * （键来自后端 platform.py::detect）—— 按 SECURITY.md 3.5 不绑接口数据渲染 HTML。
 */
import { computed, ref } from "vue"

const PLATFORM_NAMES = {
  bilibili: "哔哩哔哩", tencent: "腾讯视频", youku: "优酷", iqiyi: "爱奇艺",
  mgtv: "芒果TV", douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书",
  unknown: "未知来源", other: "其他",
}

/* 品牌图标：源码内静态 SVG 常量（v-html 数据来源为静态，SECURITY.md 3.5 允许） */
const PLATFORM_ICONS = {
  bilibili: `<svg viewBox="0 0 24 24" role="img" aria-label="哔哩哔哩"><rect width="24" height="24" rx="6" fill="#FB7299"/><path d="M7.4 4.2 10 7.2M16.6 4.2 14 7.2" stroke="#FFFFFF" stroke-width="1.9" stroke-linecap="round"/><rect x="4.4" y="7.2" width="15.2" height="12" rx="3.1" fill="none" stroke="#FFFFFF" stroke-width="1.9"/><circle cx="9.2" cy="13.2" r="1.5" fill="#FFFFFF"/><circle cx="14.8" cy="13.2" r="1.5" fill="#FFFFFF"/></svg>`,
  tencent: `<svg viewBox="0 0 24 24" role="img" aria-label="腾讯视频"><defs><linearGradient id="dp-tencent-g" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse"><stop stop-color="#17C3CE"/><stop offset="1" stop-color="#2E7CE8"/></linearGradient></defs><circle cx="12" cy="12" r="11" fill="url(#dp-tencent-g)"/><path d="M9.9 8.1v7.8l6.5-3.9z" fill="#FFFFFF"/></svg>`,
  youku: `<svg viewBox="0 0 24 24" role="img" aria-label="优酷"><circle cx="12" cy="12" r="11" fill="#0C7FF0"/><circle cx="12" cy="12" r="4.7" fill="none" stroke="#FFFFFF" stroke-width="2.7"/><circle cx="12" cy="12" r="1.2" fill="#FFFFFF"/></svg>`,
  iqiyi: `<svg viewBox="0 0 24 24" role="img" aria-label="爱奇艺"><circle cx="12" cy="12" r="11" fill="#00BE06"/><path d="M10 8.3v7.4l6.1-3.7z" fill="#FFFFFF"/></svg>`,
  mgtv: `<svg viewBox="0 0 24 24" role="img" aria-label="芒果TV"><defs><linearGradient id="dp-mgtv-g" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse"><stop stop-color="#FFC125"/><stop offset="1" stop-color="#FF8A00"/></linearGradient></defs><circle cx="12" cy="12" r="11" fill="url(#dp-mgtv-g)"/><path d="M7 16V9.2l5 4.4 5-4.4V16" stroke="#FFFFFF" stroke-width="2.1" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  douyin: `<svg viewBox="0 0 24 24" role="img" aria-label="抖音"><rect width="24" height="24" rx="6" fill="#161823"/><path d="M14.6 5.2c.4 1.9 1.6 3 3.5 3.2v2.3c-1.3 0-2.5-.4-3.5-1.1v4.9c0 2.7-2 4.5-4.5 4.3-2.1-.2-3.7-2-3.6-4.2.1-2.3 2-4 4.4-3.9v2.4c-1.1-.2-2 .4-2.1 1.5-.1.9.6 1.7 1.5 1.8 1 .1 1.9-.6 1.9-1.7V5.2h2.4z" fill="#25F4EE"/><path d="M15 4.8c.4 1.9 1.6 3 3.5 3.2v2.3c-1.3 0-2.5-.4-3.5-1.1v4.9c0 2.7-2 4.5-4.5 4.3-2.1-.2-3.7-2-3.6-4.2.1-2.3 2-4 4.4-3.9v2.4c-1.1-.2-2 .4-2.1 1.5-.1.9.6 1.7 1.5 1.8 1 .1 1.9-.6 1.9-1.7V4.8H15z" fill="#FE2C55" fill-opacity="0.85"/></svg>`,
  kuaishou: `<svg viewBox="0 0 24 24" role="img" aria-label="快手"><rect width="24" height="24" rx="6" fill="#FF7300"/><rect x="6" y="8.6" width="8" height="7" rx="2.2" fill="none" stroke="#FFFFFF" stroke-width="1.8"/><path d="M14.6 12.6l3.6-2.1v4.4l-3.6-2.1z" fill="#FFFFFF"/></svg>`,
  xiaohongshu: `<svg viewBox="0 0 24 24" role="img" aria-label="小红书"><rect width="24" height="24" rx="6" fill="#FF2442"/><rect x="5.4" y="9.4" width="13.2" height="6.8" rx="2" fill="none" stroke="#FFFFFF" stroke-width="1.7"/><path d="M9 12.8h6" stroke="#FFFFFF" stroke-width="1.7" stroke-linecap="round"/></svg>`,
  unknown: `<svg viewBox="0 0 24 24" role="img" aria-label="未知来源"><circle cx="12" cy="12" r="11" fill="#475569"/><path d="M9.6 9.6a2.5 2.5 0 1 1 3.4 2.9c-.7.3-1 .8-1 1.5v.4" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17" r="1.1" fill="#FFFFFF"/></svg>`,
  other: `<svg viewBox="0 0 24 24" role="img" aria-label="其他"><circle cx="12" cy="12" r="11" fill="#3d4a5f"/><circle cx="8.4" cy="12" r="1.3" fill="#FFFFFF"/><circle cx="12" cy="12" r="1.3" fill="#FFFFFF"/><circle cx="15.6" cy="12" r="1.3" fill="#FFFFFF"/></svg>`,
}

/* 段色：高对比固定映射（身份常量，明暗主题通用）。未收录平台回退冷色阶。 */
const SEGMENT_COLORS = {
  bilibili: "#FB7299",   // 粉（品牌）
  tencent: "#4D8EFF",    // 蓝（品牌）
  douyin: "#25F4EE",     // 亮青（品牌）
  iqiyi: "#35D461",      // 绿（品牌提亮）
  youku: "#FFC53D",      // 琥珀（原蓝与腾讯撞色，改暖色）
  mgtv: "#FF7A45",       // 橙（品牌）
  kuaishou: "#B583FF",   // 紫（原橙与芒果撞色，改冷色）
  xiaohongshu: "#FF3B30",// 深红（与粉拉开饱和度/明度）
  unknown: "#94A3B8",    // 浅灰
  other: "#56637A",      // 石板灰
}
/* 冷色漂移色阶（回退）：引用 CSS 变量，随明暗主题自动换肤 */
const FALLBACK_SCALE = [
  "var(--bd-plat-1)", "var(--bd-plat-2)", "var(--bd-plat-3)",
  "var(--bd-plat-4)", "var(--bd-plat-5)", "var(--bd-plat-6)",
]

/* ---- 环形几何常量（viewBox 260，圆心 130） ---- */
const VB = 260
const C = 130
const R_MAIN = 86      // 主环半径（core stroke 17 → 77.5..94.5，halo 到 101）
const R_ECHO = 68      // 内侧细 echo 环
const R_DASH = 56      // 旋转虚线内环
const GAP = 0.028      // 弧段间缺口（弧度 ≈1.6°）
const DEG = Math.PI / 180

const props = defineProps({
  /** 平台项：{ platform, count, delta_pct }。后端已按展示口径返回（总量降序
   *  前 5 + 其余合并 other，合并段涨跌用窗口计数重算）；count 为该平台当前
   *  解析记录存量，delta_pct 为今日新增 vs 昨日新增的真实同比 */
  platforms: { type: Array, default: () => [] },
})

/** 悬停高亮的平台 key（主环与列表联动），null = 无高亮 */
const active = ref(null)

/* 确定性伪随机（mulberry32）：呼吸粒子用，保证每次渲染形态一致 */
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/* 直接展示后端列表：过滤零量、按量降序，占比分母 = 展示行合计（后端 other
 * 已兜住全部剩余平台，合计即全站解析记录存量） */
const rows = computed(() => {
  const list = [...props.platforms]
    .filter((p) => p && p.count > 0)
    .sort((a, b) => b.count - a.count)
  const totalN = list.reduce((s, p) => s + p.count, 0) || 1

  return list.map((p, i) => ({
    key: p.platform,
    name: PLATFORM_NAMES[p.platform] || p.platform,
    count: p.count,
    pct: Math.round((p.count / totalN) * 1000) / 10,
    delta: typeof p.delta_pct === "number" ? p.delta_pct : null,
    color: SEGMENT_COLORS[p.platform] || FALLBACK_SCALE[i % FALLBACK_SCALE.length],
  }))
})

const total = computed(() => rows.value.reduce((s, r) => s + r.count, 0))
/* 进度条以榜首为满轨基准（同 TOP5 口径），最小 6% 保证可见 */
const maxCount = computed(() => rows.value[0]?.count || 0)

/** 两点圆弧路径（顺时针，a0/a1 为相对 12 点钟的弧度） */
function arcPath(r, a0, a1) {
  const x0 = C + r * Math.sin(a0)
  const y0 = C - r * Math.cos(a0)
  const x1 = C + r * Math.sin(a1)
  const y1 = C - r * Math.cos(a1)
  const large = a1 - a0 > Math.PI ? 1 : 0
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`
}

/** 预计算每段弧线（core / echo 共用缺口几何）与 HUD 标注锚点 */
const slices = computed(() => {
  let cum = 0
  return rows.value.map((r) => {
    const frac = total.value ? r.count / total.value : 0
    const full = frac * Math.PI * 2
    const pad = Math.min(GAP, full / 4)
    const a0 = cum * Math.PI * 2 - Math.PI / 2 + pad
    const a1 = (cum + frac) * Math.PI * 2 - Math.PI / 2 - pad
    const mid = (cum + frac / 2) * Math.PI * 2 - Math.PI / 2
    cum += frac
    const s = Math.sin(mid)
    const c = Math.cos(mid)
    return {
      ...r,
      d: frac > 0 ? arcPath(R_MAIN, a0, a1) : "",
      echo: frac > 0 ? arcPath(R_ECHO, a0, a1) : "",
      showLabel: rows.value.length > 1 && r.pct >= 8,
      dx: +(C + 95.5 * s).toFixed(1), dy: +(C - 95.5 * c).toFixed(1),
      lx: +(C + 107 * s).toFixed(1), ly: +(C - 107 * c).toFixed(1),
      anchor: s >= 0 ? "start" : "end",
    }
  })
})

/* 外圈 72 根科技刻度：主刻度每 30°（更长更粗） */
const TICKS = (() => {
  const arr = []
  for (let i = 0; i < 72; i++) {
    const a = i * 5 * DEG
    const s = Math.sin(a)
    const c = Math.cos(a)
    const major = i % 6 === 0
    const r0 = major ? 98 : 100.5
    arr.push({
      x1: +(C + r0 * s).toFixed(1), y1: +(C - r0 * c).toFixed(1),
      x2: +(C + 107 * s).toFixed(1), y2: +(C - 107 * c).toFixed(1),
      major,
    })
  }
  return arr
})()

/* 四向 HUD 十字标 + 两段角括弧（左上 / 右下） */
const CROSSES = [0, 90, 180, 270].map((d) => {
  const a = d * DEG
  return {
    x1: +(C + 112.5 * Math.sin(a)).toFixed(1), y1: +(C - 112.5 * Math.cos(a)).toFixed(1),
    x2: +(C + 117.5 * Math.sin(a)).toFixed(1), y2: +(C - 117.5 * Math.cos(a)).toFixed(1),
  }
})
const BRACKETS = [
  arcPath(114.5, -100 * DEG, -66 * DEG),
  arcPath(114.5, 80 * DEG, 114 * DEG),
]

/* 呼吸粒子：内圈散布 + 主环外沿散布，确定性生成 */
const PARTICLES = (() => {
  const rnd = mulberry32(20260915)
  return Array.from({ length: 16 }, (_, i) => {
    const a = rnd() * Math.PI * 2
    const r = i % 3 === 0 ? 96 + rnd() * 10 : 20 + rnd() * 30
    return {
      x: +(C + r * Math.sin(a)).toFixed(1), y: +(C - r * Math.cos(a)).toFixed(1),
      r: +(0.7 + rnd() * 0.9).toFixed(2),
      o: +(0.3 + rnd() * 0.45).toFixed(2),
      cls: `pt t${i % 3}`,
    }
  })
})()

/* 雷达扫描扇面（旋转组内）：71..101 环带，-35°..15°，尾迹沿行进方向渐隐 */
const SWEEP = (() => {
  const r0 = 71
  const r1 = 101
  const a0 = -35 * DEG
  const a1 = 15 * DEG
  const p = (r, a) => `${(C + r * Math.sin(a)).toFixed(2)} ${(C - r * Math.cos(a)).toFixed(2)}`
  return `M ${p(r0, a0)} L ${p(r1, a0)} A ${r1} ${r1} 0 0 1 ${p(r1, a1)} L ${p(r0, a1)} A ${r0} ${r0} 0 0 0 ${p(r0, a0)} Z`
})()
</script>

<template>
  <div class="plat">
    <p v-if="!rows.length" class="empty">暂无解析数据</p>

    <template v-else>
      <!-- ============ 左：多层发光环形仪表 ============ -->
      <div class="ring-col">
        <div class="ring">
          <svg
            :viewBox="`0 0 ${VB} ${VB}`"
            role="img"
            :aria-label="`平台解析占比环形图，共 ${total} 条解析记录`"
          >
            <defs>
              <!-- 环心辉光（径向渐隐） -->
              <radialGradient id="dp-core-g">
                <stop offset="0%" :style="{ stopColor: 'var(--bd-azure)' }" stop-opacity="0.26" />
                <stop offset="70%" :style="{ stopColor: 'var(--bd-azure)' }" stop-opacity="0.06" />
                <stop offset="100%" :style="{ stopColor: 'var(--bd-azure)' }" stop-opacity="0" />
              </radialGradient>
              <!-- 扫描扇面尾迹（沿行进方向渐隐，userSpaceOnUse 跨弦渐变） -->
              <linearGradient
                id="dp-sweep-g" gradientUnits="userSpaceOnUse"
                :x1="(C + 86 * Math.sin(-35 * Math.PI / 180)).toFixed(1)"
                :y1="(C - 86 * Math.cos(-35 * Math.PI / 180)).toFixed(1)"
                :x2="(C + 86 * Math.sin(15 * Math.PI / 180)).toFixed(1)"
                :y2="(C - 86 * Math.cos(15 * Math.PI / 180)).toFixed(1)"
              >
                <stop offset="0%" :style="{ stopColor: 'var(--bd-azure)' }" stop-opacity="0" />
                <stop offset="100%" :style="{ stopColor: 'var(--bd-azure)' }" stop-opacity="0.3" />
              </linearGradient>
            </defs>

            <!-- 外沿细圈 + 刻度 + HUD 标记 -->
            <circle :cx="C" :cy="C" r="110" fill="none" class="outer-c" />
            <g class="ticks">
              <line
                v-for="(t, i) in TICKS" :key="i"
                :x1="t.x1" :y1="t.y1" :x2="t.x2" :y2="t.y2"
                :stroke-width="t.major ? 1.4 : 0.7"
              />
            </g>
            <g class="hud">
              <line
                v-for="(cr, i) in CROSSES" :key="'c' + i"
                :x1="cr.x1" :y1="cr.y1" :x2="cr.x2" :y2="cr.y2" stroke-width="1.4"
              />
              <path v-for="(b, i) in BRACKETS" :key="'b' + i" :d="b" fill="none" stroke-width="1.5" />
            </g>

            <!-- 呼吸粒子 -->
            <g>
              <circle
                v-for="(pt, i) in PARTICLES" :key="'p' + i"
                :cx="pt.x" :cy="pt.y" :r="pt.r" :class="pt.cls"
                :style="{ fillOpacity: pt.o }"
              />
            </g>

            <!-- 主环 halo 层（加宽低透明，叠出多层厚度） -->
            <g class="halo">
              <path
                v-for="s in slices" v-show="s.d" :key="'h' + s.key"
                :d="s.d" fill="none" stroke-width="30"
                :class="{ dim: active && active !== s.key }"
                :style="{ stroke: s.color }" stroke-opacity="0.13"
              />
            </g>

            <!-- 主环 core 层（悬停交互在此层） -->
            <g class="segs">
              <path
                v-for="s in slices" v-show="s.d" :key="s.key"
                class="segp" :class="{ dim: active && active !== s.key }"
                :d="s.d" fill="none" stroke-width="17"
                :style="{ stroke: s.color, filter: `drop-shadow(0 0 4px ${s.color})` }"
                @mouseenter="active = s.key"
                @mouseleave="active = null"
              />
            </g>

            <!-- 内侧 echo 细环（第三层） -->
            <g class="echo-g">
              <path
                v-for="s in slices" v-show="s.echo" :key="'e' + s.key"
                :d="s.echo" fill="none" stroke-width="3"
                :class="{ dim: active && active !== s.key }"
                :style="{ stroke: s.color }" stroke-opacity="0.5"
              />
            </g>

            <!-- 旋转层：虚线内环 / 扫描扇面 / 双轨道光点 -->
            <g class="dp-dash">
              <circle :cx="C" :cy="C" :r="R_DASH" fill="none" class="dash-c" />
            </g>
            <g class="dp-sweep">
              <path :d="SWEEP" fill="url(#dp-sweep-g)" />
              <circle
                :cx="(C + 86 * Math.sin(15 * Math.PI / 180)).toFixed(1)"
                :cy="(C - 86 * Math.cos(15 * Math.PI / 180)).toFixed(1)"
                r="2.1" class="sweep-dot"
              />
            </g>
            <g class="dp-orb">
              <circle :cx="C" :cy="C - R_MAIN" r="2.3" class="orb orb-a" />
            </g>
            <g class="dp-orb2">
              <circle :cx="C" :cy="C - R_DASH" r="1.7" class="orb orb-b" />
            </g>

            <!-- 环心：辉光盘 + 大数字 + 标题 -->
            <circle :cx="C" :cy="C" r="44" class="core-bg" />
            <circle :cx="C" :cy="C" r="44" fill="url(#dp-core-g)" />
            <circle :cx="C" :cy="C" r="44" fill="none" class="core-ln" />
            <text class="c-num" :x="C" :y="C + 10" text-anchor="middle">{{ total }}</text>
            <text class="c-cap" :x="C" :y="C + 25" text-anchor="middle">解析记录</text>

            <!-- 大段外沿 HUD 标注：色点 + 引线 + 百分比 -->
            <g class="labels">
              <template v-for="s in slices" :key="'l' + s.key">
                <template v-if="s.showLabel">
                  <circle
                    :cx="s.dx" :cy="s.dy" r="2"
                    :class="{ dim: active && active !== s.key }"
                    :style="{ fill: s.color }"
                  />
                  <line
                    :x1="s.dx" :y1="s.dy" :x2="s.lx" :y2="s.ly"
                    :class="{ dim: active && active !== s.key }"
                  />
                  <text
                    :x="s.lx" :y="s.ly" :text-anchor="s.anchor"
                    dominant-baseline="middle"
                    :class="{ dim: active && active !== s.key }"
                  >{{ s.pct }}%</text>
                </template>
              </template>
            </g>
          </svg>
        </div>
      </div>

      <!-- ============ 右：纵向数据列表 ============ -->
      <div class="plist" role="table" aria-label="平台解析占比明细">
        <div
          v-for="r in slices"
          :key="r.key"
          class="r"
          role="row"
          :class="{ on: active === r.key }"
          :style="{ '--seg-c': r.color }"
          @mouseenter="active = r.key"
          @mouseleave="active = null"
        >
          <span class="ic" aria-hidden="true" v-html="PLATFORM_ICONS[r.key] || PLATFORM_ICONS.other"></span>

          <span class="mid">
            <span class="nm">{{ r.name }}</span>
            <span class="barrow">
              <span class="track" aria-hidden="true">
                <i :style="{ width: maxCount ? Math.max(6, (r.count / maxCount) * 100) + '%' : '0%' }"></i>
              </span>
              <em class="bpct">{{ r.pct }}%</em>
            </span>
          </span>

          <span class="cnt">
            <b>{{ r.count }}</b>
          </span>

          <span class="d" :class="r.delta > 0 ? 'up' : r.delta < 0 ? 'down' : 'flat'">
            <template v-if="r.delta == null">—</template>
            <template v-else>{{ r.delta > 0 ? "↑" : r.delta < 0 ? "↓" : "→" }} {{ Math.abs(r.delta) }}%</template>
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.plat {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 14px;
}

/* ---- 左：环形仪表 ---- */
.ring-col {
  flex: 0 1 auto;
  width: 45%;
  max-width: 212px;
  min-width: 150px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ring {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
}
/* 细微蓝色辉光垫底 */
.ring::before {
  content: "";
  position: absolute;
  inset: 4%;
  border-radius: 50%;
  background: radial-gradient(circle, color-mix(in srgb, var(--bd-azure) 12%, transparent) 0%, transparent 66%);
  pointer-events: none;
}
.ring svg {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.outer-c { stroke: var(--bd-ln); stroke-width: 1; opacity: 0.6; }
.ticks line { stroke: var(--bd-hud); opacity: 0.6; }
.ticks line { transition: opacity 0.2s ease; }
.hud line, .hud path { stroke: var(--bd-hud); opacity: 0.85; }

.pt { fill: var(--bd-hud); }

/* 主环 */
.segp {
  cursor: default;
  transition: opacity 0.2s ease, filter 0.2s ease;
  pointer-events: stroke;
}
.dim { opacity: 0.16 !important; }
.segp.dim { filter: none !important; }

/* 旋转虚线内环 */
.dash-c { stroke: var(--bd-hud); stroke-width: 1; stroke-dasharray: 2 5; opacity: 0.55; }
/* 扫描扇面前沿光点 */
.sweep-dot { fill: var(--bd-azure); filter: drop-shadow(0 0 4px var(--bd-azure)); }
/* 轨道光点 */
.orb-a { fill: var(--bd-aqua); filter: drop-shadow(0 0 5px var(--bd-aqua)); }
.orb-b { fill: var(--bd-t1); opacity: 0.85; }

/* 环心 */
.core-bg { fill: var(--bd-fill-soft); }
.core-ln { stroke: var(--bd-ln); stroke-width: 1; }
.c-num {
  font-family: var(--font-mono);
  font-size: 30px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  fill: var(--bd-t1);
  filter: drop-shadow(0 0 7px color-mix(in srgb, var(--bd-azure) 80%, transparent));
}
.c-cap {
  font-family: var(--font-sans, sans-serif);
  font-size: 10px;
  letter-spacing: 0.14em;
  fill: var(--bd-t2);
}

/* HUD 标注 */
.labels line { stroke: var(--bd-hud); stroke-width: 1; opacity: 0.55; }
.labels text {
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  fill: var(--bd-t1);
  /* 描边垫底盖住底下穿过的刻度线，保证文字可读 */
  paint-order: stroke;
  stroke: var(--bd-ink);
  stroke-width: 3px;
}

/* ---- 右：纵向数据列表（行间极细分割线） ---- */
.plist {
  flex: 1;
  align-self: stretch;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.plist .r {
  flex: 1 1 0;
  min-height: 0;
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) 34px 48px;
  gap: 9px;
  align-items: center;
  padding: 0 2px;
  border-radius: 6px;
  transition: background 0.16s ease;
}
.plist .r + .r {
  border-top: 1px solid color-mix(in srgb, var(--bd-ln) 55%, transparent);
}
.plist .r.on { background: var(--bd-hover); }

.plist .ic {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border-radius: 6px;
  overflow: hidden;
}
.plist .ic :deep(svg) { width: 22px; height: 22px; display: block; }

.plist .mid {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.plist .nm {
  font-size: 12px;
  font-weight: 550;
  color: var(--bd-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.1;
}
.plist .barrow {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.plist .track {
  position: relative;
  flex: 1;
  min-width: 0;
  height: 4px;
  border-radius: 2px;
  background: var(--bd-rail);
  overflow: hidden;
}
.plist .track i {
  position: absolute;
  inset: 0 auto 0 0;
  display: block;
  border-radius: 2px;
  background: linear-gradient(90deg, color-mix(in srgb, var(--seg-c) 55%, transparent), var(--seg-c));
  box-shadow: 0 0 8px -1px var(--seg-c);
  transition: width 0.8s var(--ease-out, ease-out);
}
.plist .bpct {
  flex-shrink: 0;
  width: 38px;
  font-style: normal;
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--bd-t2);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* 解析数量列：单个大数字（占比只保留进度条右侧那一处，去重） */
.plist .cnt {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  line-height: 1;
}
.plist .cnt b {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 700;
  color: var(--bd-t1);
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 12px color-mix(in srgb, var(--bd-azure) 30%, transparent);
}

.plist .d {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.plist .d.up { color: var(--bd-ok); }
.plist .d.down { color: var(--bd-rose); }
.plist .d.flat { color: var(--bd-t3); font-weight: 400; }

@media (max-width: 1500px) {
  .plat { gap: 10px; }
  .ring-col { min-width: 128px; max-width: 172px; }
  .labels { display: none; }
  .plist { gap: 0; }
  .plist .r { gap: 7px; grid-template-columns: 20px minmax(0, 1fr) 28px 44px; }
  .plist .bpct { width: 34px; }
}

.empty {
  margin: auto;
  font-size: 11.5px;
  color: var(--bd-t3);
  text-align: center;
}
</style>

<style scoped>
/* 动效统一收口：系统减少动态时全部静止（结构层不可省略，故单独一段） */
@media (prefers-reduced-motion: no-preference) {
  .dp-dash,
  .dp-sweep,
  .dp-orb,
  .dp-orb2 {
    transform-box: view-box;
    transform-origin: 50% 50%;
  }
  .dp-dash { animation: dp-rot 64s linear infinite; }
  .dp-sweep { animation: dp-rot 7.5s linear infinite; }
  .dp-orb { animation: dp-rot 13s linear infinite; }
  .dp-orb2 { animation: dp-rot-rev 21s linear infinite; }
  .pt { animation: dp-tw 3.2s ease-in-out infinite; }
  .pt.t1 { animation-duration: 2.4s; animation-delay: -0.8s; }
  .pt.t2 { animation-duration: 4.1s; animation-delay: -1.6s; }
}
@keyframes dp-rot { to { transform: rotate(360deg); } }
@keyframes dp-rot-rev { to { transform: rotate(-360deg); } }
@keyframes dp-tw { 0%, 100% { opacity: 1; } 50% { opacity: 0.15; } }
</style>
