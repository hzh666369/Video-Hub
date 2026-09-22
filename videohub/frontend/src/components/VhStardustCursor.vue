<script setup>
/*
 * VhStardustCursor · 星尘彗尾光标（粒子感全开 · 加强版）
 *
 * 设计：指针 = 一颗白热彗核在星空中航行——
 *  - 彗核：四层辉光（大范围环境光晕 → 绿晕 → 亮绿 → 白热核心），弹性跟随指针；
 *    仅在指针移动时点亮，悬停静止后快速淡出（避免静止时出现刺眼光斑）
 *  - 余烬拖尾：沿轨迹高密度迸溅，颜色随生命周期「冷却」：白热 → 品牌绿 → 琥珀
 *  - 火花：高速划过时频发的亮星，带重力下坠，像烟花余烬
 *  - 星芒：更常闪现的四芒星，随生命周期绽放再收敛
 *  - 静息已移除：指针停住时不再吐出余烬，悬停时画面保持干净
 *  - 按下：爆发放射火花 + 双重扩散冲击波光环
 *
 * 性能底线（交互流畅优先，任何情况下不允许卡顿）：
 *  - 单一 <canvas> fixed 覆盖层，pointer-events: none，不拦截任何交互
 *  - 仅 rAF 驱动；粒子硬上限 240；dt 钳制防止切页回来粒子狂奔
 *  - 粒子绘制全部用预渲染 sprite（径向渐变圆点 / 四芒星），
 *    每帧只做 drawImage + globalAlpha，无路径、无阴影、无滤镜
 *  - devicePixelRatio 封顶 1.5；触屏 (pointer: coarse) 与
 *    prefers-reduced-motion 直接不挂载；页面隐藏时暂停循环
 *  - 暗色主题用 lighter 加法混合叠出辉光；浅色主题退回普通合成并降透明度
 */
import { onBeforeUnmount, onMounted, ref } from "vue"

const canvasRef = ref(null)
const enabled = ref(false)

let ctx = null
let rafId = 0
let running = false
let lastT = 0
let particles = []
let ripples = []
let dustSprites = []
let starSprites = []
let coreSprite = null
let dpr = 1
let W = 0
let H = 0
let theme = "dark"

/* 指针状态：px/py 上一采样点；vx/vy 估算速度（px/s）供粒子继承 */
const pointer = { x: -100, y: -100, px: -100, py: -100, vx: 0, vy: 0, active: false, lastMove: 0 }
const comet = { x: -100, y: -100 }

const MAX_PARTICLES = 280

/* 双主题调色：粒子按生命从索引 0「冷却」到索引 3（白热 → 绿 → 琥珀）。
 * 浅色主题换深色调 + 低透明度，白底上低饱和才不会发灰发脏 */
const PALETTES = {
  dark: {
    dust: [
      [225, 255, 240], // 白热
      [60, 228, 119],  // 品牌绿
      [30, 215, 96],   // 深绿
      [255, 181, 88],  // 琥珀
    ],
    core: [230, 255, 242],
    ripple: [60, 228, 119],
    alpha: 1,
  },
  light: {
    dust: [
      [52, 211, 153],  // 翠绿（可见的「高温」）
      [22, 163, 74],   // 深绿
      [234, 88, 12],   // 橙
      [194, 65, 12],   // 深橙
    ],
    core: [16, 185, 129],
    ripple: [22, 163, 74],
    alpha: 0.68,
  },
}
let P = PALETTES.dark

/* ---------- sprite 预渲染 ---------- */
function makeDustSprite([r, g, b]) {
  const s = 64
  const c = document.createElement("canvas")
  c.width = s
  c.height = s
  const g2 = c.getContext("2d")
  const grad = g2.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2)
  grad.addColorStop(0, `rgba(${r},${g},${b},0.95)`)
  /* 中段渐变更宽更亮：辉光外溢感更强 */
  grad.addColorStop(0.3, `rgba(${r},${g},${b},0.42)`)
  grad.addColorStop(1, `rgba(${r},${g},${b},0)`)
  g2.fillStyle = grad
  g2.fillRect(0, 0, s, s)
  return c
}

/* 四芒星：两条渐变细光交叉 + 中心光点 */
function makeStarSprite([r, g, b]) {
  const s = 48
  const c = document.createElement("canvas")
  c.width = s
  c.height = s
  const g2 = c.getContext("2d")
  g2.translate(s / 2, s / 2)
  for (let i = 0; i < 2; i++) {
    const grad = g2.createLinearGradient(-s / 2, 0, s / 2, 0)
    grad.addColorStop(0, `rgba(${r},${g},${b},0)`)
    grad.addColorStop(0.5, `rgba(${r},${g},${b},0.95)`)
    grad.addColorStop(1, `rgba(${r},${g},${b},0)`)
    g2.fillStyle = grad
    g2.fillRect(-s / 2, -0.8, s, 1.6)
    g2.rotate(Math.PI / 2)
  }
  const dot = g2.createRadialGradient(0, 0, 0, 0, 0, 6)
  dot.addColorStop(0, `rgba(${r},${g},${b},0.95)`)
  dot.addColorStop(1, `rgba(${r},${g},${b},0)`)
  g2.fillStyle = dot
  g2.fillRect(-6, -6, 12, 12)
  return c
}

function buildSprites() {
  P = PALETTES[theme]
  dustSprites = P.dust.map(makeDustSprite)
  starSprites = P.dust.map(makeStarSprite)
  coreSprite = makeDustSprite(P.core)
}

/* ---------- 主题跟随（与 VhParticleField 同款方案） ---------- */
const themeObserver = new MutationObserver(() => {
  theme = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark"
  buildSprites()
})

/* ---------- 粒子发射 ---------- */
function push(p) {
  if (particles.length >= MAX_PARTICLES) particles.shift()
  particles.push(p)
}

/* 余烬：继承较多指针动量（拖尾拉得更长）+ 随机散布，缓慢上浮、受风微卷。
 * decay 压低让单颗粒子存活 ~1.1-1.8s，拖尾时长明显加长 */
function emitDust(x, y, vx, vy) {
  push({
    kind: 0,
    x,
    y,
    vx: vx * 0.28 + (Math.random() - 0.5) * 52,
    vy: vy * 0.28 + (Math.random() - 0.5) * 52 - 12,
    life: 1,
    decay: 0.55 + Math.random() * 0.35,
    size: 5 + Math.random() * 10,
    phase: Math.random() * Math.PI * 2,
  })
}

/* 火花：更小更快，带重力，像烟花余烬坠落后熄灭 */
function emitSpark(x, y, vx, vy) {
  push({
    kind: 1,
    x,
    y,
    vx: vx * 0.32 + (Math.random() - 0.5) * 140,
    vy: vy * 0.32 + (Math.random() - 0.5) * 140,
    life: 1,
    decay: 1.5 + Math.random() * 0.9,
    size: 2.5 + Math.random() * 2.5,
  })
}

/* 星芒：几乎静止地原地绽放再收敛 */
function emitStar(x, y) {
  push({
    kind: 2,
    x: x + (Math.random() - 0.5) * 16,
    y: y + (Math.random() - 0.5) * 16,
    vx: (Math.random() - 0.5) * 14,
    vy: (Math.random() - 0.5) * 14 - 6,
    life: 1,
    decay: 1 + Math.random() * 0.5,
    size: 14 + Math.random() * 14,
    rot: Math.random() * Math.PI,
    rotV: (Math.random() - 0.5) * 1.6,
    ci: Math.random() < 0.5 ? 1 : 3,
    phase: Math.random() * Math.PI * 2,
  })
}

/* 点击爆发：放射火花 + 双重冲击波 */
function burst(x, y) {
  for (let i = 0; i < 22; i++) {
    const a = (i / 22) * Math.PI * 2 + Math.random() * 0.4
    const sp = 110 + Math.random() * 200
    push({
      kind: 1,
      x,
      y,
      vx: Math.cos(a) * sp,
      vy: Math.sin(a) * sp - 30,
      life: 1,
      decay: 1.7 + Math.random() * 1.1,
      size: 2 + Math.random() * 2.6,
    })
  }
  for (let i = 0; i < 8; i++) emitDust(x, y, 0, 0)
  ripples.push({ x, y, r: 3, a: 0.65 })
  ripples.push({ x, y, r: 14, a: 0.4 })
}

/* ---------- 指针事件 ---------- */
function onMove(e) {
  const { clientX: x, clientY: y } = e
  const now = performance.now()
  if (!pointer.active) {
    pointer.px = x
    pointer.py = y
    comet.x = x
    comet.y = y
    pointer.active = true
  }
  const dx = x - pointer.px
  const dy = y - pointer.py
  const dist = Math.hypot(dx, dy)
  const dtm = Math.max(8, now - pointer.lastMove)
  pointer.vx = (dx / dtm) * 1000
  pointer.vy = (dy / dtm) * 1000

  /* 快速移动时在两点间插值补粒子，轨迹不断裂；越快迸溅越密。
   * 插值步距收紧 + 上限放宽，让粒子铺满更长的路径段 */
  const steps = Math.min(Math.max(1, (dist / 4) | 0), 10)
  for (let i = 0; i < steps; i++) {
    const t = (i + 0.5) / steps
    const sx = pointer.px + dx * t
    const sy = pointer.py + dy * t
    emitDust(sx, sy, pointer.vx, pointer.vy)
    if (Math.random() < 0.5) emitDust(sx, sy, pointer.vx, pointer.vy)
    if (Math.random() < 0.2) emitSpark(sx, sy, pointer.vx, pointer.vy)
    if (Math.random() < 0.06) emitStar(sx, sy)
  }
  pointer.px = x
  pointer.py = y
  pointer.x = x
  pointer.y = y
  pointer.lastMove = now
}

function onDown(e) {
  if (pointer.active) burst(e.clientX, e.clientY)
}

function onLeave() {
  pointer.active = false
}

/* ---------- 主循环 ---------- */
function frame(now) {
  if (!running) return
  rafId = requestAnimationFrame(frame)
  const dt = Math.min(0.05, (now - lastT) / 1000 || 0.016)
  lastT = now
  ctx.clearRect(0, 0, W, H)
  ctx.globalCompositeOperation = theme === "dark" ? "lighter" : "source-over"
  const baseAlpha = P.alpha

  /* 彗核弹性跟随（帧率无关的指数趋近；略放宽让拖尾感更明显） */
  const k = 1 - Math.exp(-dt * 11)
  comet.x += (pointer.x - comet.x) * k
  comet.y += (pointer.y - comet.y) * k

  /* 悬停亮度控制：指针静止后彗核辉光在 HOVER_FADE_MS 内淡出到 0，
   * 移动时恒为 1（滑动追尾不受影响）。淡出而非瞬灭，观感不突兀 */
  const HOVER_FADE_MS = 280
  const motion = pointer.active
    ? Math.max(0, 1 - (now - pointer.lastMove) / HOVER_FADE_MS)
    : 0

  /* 彗核辉光：环境光晕 → 极淡绿晕 → 微光核心。
   * 中心区域整体压到很低，只保留可感知的一圈淡光；
   * alpha 乘 motion —— 悬停静止后整组辉光淡出，不再有刺眼光斑 */
  if (pointer.active && motion > 0) {
    ctx.globalAlpha = 0.18 * baseAlpha * motion
    ctx.drawImage(coreSprite, comet.x - 55, comet.y - 55, 110, 110)
    ctx.globalAlpha = 0.25 * baseAlpha * motion
    ctx.drawImage(coreSprite, comet.x - 36, comet.y - 36, 72, 72)
    ctx.globalAlpha = 0.28 * baseAlpha * motion
    ctx.drawImage(dustSprites[1], comet.x - 17, comet.y - 17, 34, 34)
    ctx.globalAlpha = 0.08 * baseAlpha * motion
    ctx.drawImage(coreSprite, comet.x - 5, comet.y - 5, 10, 10)
  }

  /* 冲击波 */
  for (let i = ripples.length - 1; i >= 0; i--) {
    const rp = ripples[i]
    rp.r += 240 * dt
    rp.a *= Math.exp(-5.5 * dt)
    if (rp.a < 0.02) {
      ripples.splice(i, 1)
      continue
    }
    ctx.globalAlpha = rp.a * baseAlpha
    ctx.strokeStyle = `rgba(${P.ripple[0]},${P.ripple[1]},${P.ripple[2]},0.8)`
    ctx.lineWidth = 1.8
    ctx.beginPath()
    ctx.arc(rp.x, rp.y, rp.r, 0, Math.PI * 2)
    ctx.stroke()
  }

  /* 粒子群：按 kind 走各自的物理 */
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]
    p.life -= p.decay * dt
    if (p.life <= 0) {
      particles.splice(i, 1)
      continue
    }
    p.x += p.vx * dt
    p.y += p.vy * dt

    if (p.kind === 0) {
      /* 余烬：较弱阻尼（滑行更远）+ 缓升 + 正弦微风卷 */
      const damp = Math.exp(-2.2 * dt)
      p.vx *= damp
      p.vy = p.vy * damp - 14 * dt
      p.vx += Math.sin(p.phase + now * 0.003) * 7 * dt
      const size = p.size * (0.35 + p.life * 0.65)
      /* 冷却变色：白热 → 绿 → 琥珀 */
      const ci = Math.min(3, ((1 - p.life) * 3.99) | 0)
      ctx.globalAlpha = p.life * baseAlpha
      ctx.drawImage(dustSprites[ci], p.x - size / 2, p.y - size / 2, size, size)
    } else if (p.kind === 1) {
      /* 火花：轻阻尼 + 重力坠落 */
      const damp = Math.exp(-2.2 * dt)
      p.vx *= damp
      p.vy = p.vy * damp + 260 * dt
      const size = p.size * (0.4 + p.life * 0.6)
      const ci = p.life > 0.55 ? 0 : 1
      ctx.globalAlpha = p.life * baseAlpha
      ctx.drawImage(dustSprites[ci], p.x - size / 2, p.y - size / 2, size, size)
    } else {
      /* 星芒：先绽放后收敛 + 闪烁 */
      const damp = Math.exp(-1.5 * dt)
      p.vx *= damp
      p.vy *= damp
      p.rot += p.rotV * dt
      const prog = 1 - p.life
      const scale = Math.sin(prog * Math.PI)
      const twinkle = 0.7 + 0.3 * Math.sin(now * 0.02 + p.phase)
      const size = p.size * scale
      if (size > 0.5) {
        ctx.save()
        ctx.translate(p.x, p.y)
        ctx.rotate(p.rot)
        ctx.globalAlpha = p.life * twinkle * baseAlpha
        ctx.drawImage(starSprites[p.ci], -size / 2, -size / 2, size, size)
        ctx.restore()
      }
    }
  }
  ctx.globalAlpha = 1
}

function start() {
  if (running) return
  running = true
  lastT = performance.now()
  rafId = requestAnimationFrame(frame)
}

function stop() {
  running = false
  cancelAnimationFrame(rafId)
  if (ctx) ctx.clearRect(0, 0, W, H)
}

function onVisibility() {
  if (document.hidden) stop()
  else start()
}

function resize() {
  const c = canvasRef.value
  if (!c) return
  dpr = Math.min(window.devicePixelRatio || 1, 1.5)
  W = window.innerWidth
  H = window.innerHeight
  c.width = Math.round(W * dpr)
  c.height = Math.round(H * dpr)
  c.style.width = W + "px"
  c.style.height = H + "px"
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

onMounted(() => {
  /* 降级守卫：触屏 / 减少动效 → 完全不启用 */
  const coarse = window.matchMedia("(pointer: coarse)").matches
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
  if (coarse || reduced) return

  enabled.value = true
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] })
  theme = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark"

  /* 等 canvas 挂到 DOM 后再初始化 */
  requestAnimationFrame(() => {
    const c = canvasRef.value
    if (!c) return
    ctx = c.getContext("2d", { alpha: true })
    buildSprites()
    resize()
    window.addEventListener("resize", resize, { passive: true })
    window.addEventListener("pointermove", onMove, { passive: true })
    window.addEventListener("pointerdown", onDown, { passive: true })
    document.documentElement.addEventListener("mouseleave", onLeave)
    document.addEventListener("visibilitychange", onVisibility)
    start()
  })
})

onBeforeUnmount(() => {
  stop()
  themeObserver.disconnect()
  window.removeEventListener("resize", resize)
  window.removeEventListener("pointermove", onMove)
  window.removeEventListener("pointerdown", onDown)
  document.documentElement.removeEventListener("mouseleave", onLeave)
  document.removeEventListener("visibilitychange", onVisibility)
})
</script>

<template>
  <canvas
    v-if="enabled"
    ref="canvasRef"
    class="stardust-cursor"
    aria-hidden="true"
  ></canvas>
</template>

<style scoped>
.stardust-cursor {
  position: fixed;
  inset: 0;
  z-index: 9999;
  pointer-events: none;
  mix-blend-mode: screen;
}
/* 浅色主题：screen 混合在白底上不可见，退回普通合成并靠降透明度控制 */
html[data-theme="light"] .stardust-cursor {
  mix-blend-mode: normal;
}
</style>
