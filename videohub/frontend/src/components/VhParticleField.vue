<script setup>
/**
 * VhParticleField · WebGL 星际粒子场背景（Three.js）
 *
 * 复刻参考视频的「galactic drift」效果：
 *  - 紫 / 青 / 墨蓝多彩粒子在三维空间中随流场漂移，快速粒子拉出彗尾拖痕
 *  - 拖痕用「速度拉伸四边形」实现：顶点着色器把粒子沿屏幕空间速度方向拉长，
 *    片元着色器做彗星轮廓（头亮尾淡），单 draw call，无需反馈缓冲
 *  - 鼠标移动会扰动流场：靠近光标的粒子被推斥 + 绕光标旋转 + 顺着光标
 *    速度方向拖走（MOVE MOUSEPOWER TO WARP GALACTIC DRIFT）
 *  - 粒子带 z 深度：远小近大、透视缩放，形成视差纵深
 *  - 全局能量周期：流场速度在平静与涌动之间缓慢起伏，画面张弛有致
 *
 * 工程细节：
 *  - 双主题配色自动跟随 html[data-theme]（深色=亮青紫蓝绿发光头；浅色=白底上的
 *    青紫蓝绿墨流，彗核压深保持清晰，低透明度避免重叠糊块）
 *  - prefers-reduced-motion 时只渲染静态粒子点阵，不做动画
 *  - 页签隐藏时暂停 rAF；WebGL 不可用时静默降级为透明背景
 *  - 纯装饰层：pointer-events: none、aria-hidden，不进无障碍树
 */
import { onBeforeUnmount, onMounted, ref } from "vue"

const props = defineProps({
  /** page=全视口固定底（fixed） | hero=局部区块底（absolute） */
  variant: { type: String, default: "page" },
  /** 粒子密度系数 0.4 ~ 2 */
  density: { type: Number, default: 1 },
  /** 是否响应鼠标扰动 */
  interactive: { type: Boolean, default: true },
})

const host = ref(null)

/* ---- 双主题色板 ----
 * 深色：亮青紫蓝绿 + 混白彗核 = 黑夜里的发光星尘，0.82 高不透明度撑起氛围
 * 浅色：感知权重反转 —— 同样粒子在白底的对比度远高于黑底，
 *   深色墨点会读成「脏点」，必须走低透明度水彩路线：
 *   中饱和色 + 低 opacity（0.42，峰值 0.42*1.4≈0.59 永不触顶钳制，
 *   轮廓全程保持渐变不会出现方块平顶）+ 中等柔边 + 混白彗核（柔焦 bokeh 感） */
const PALETTES = {
  dark: { colors: ["#4de3c2", "#a78bfa", "#5ab8ff", "#1ed760"], core: "#ffffff", opacity: 0.82, sharp: 0 },
  light: { colors: ["#14b8a6", "#8b5cf6", "#3b82f6", "#22c55e"], core: "#ffffff", opacity: 0.42, sharp: 0.35 },
}

let renderer = null
let scene = null
let camera = null
let material = null
let geometry = null
let mesh = null
let rafId = 0
let disposed = false
let reducedMotion = false
// three.js 走动态导入：不阻塞 ParseHome 主包，组件挂载时才拉取
let THREE = null

let sim = null
let resizeObs = null
let themeObs = null

/* ---- 世界参数（与相机联动） ---- */
const CAM_DIST = 90
const FOV = 55
const Z_NEAR = -78
const Z_FAR = 28

function initSim(w, h) {
  const aspect = w / h
  const halfH = Math.tan(((FOV / 2) * Math.PI) / 180) * CAM_DIST
  const halfW = halfH * aspect
  const isSmall = w < 720
  const base = (w * h) / (isSmall ? 1300 : 850)
  const count = Math.max(200, Math.min(isSmall ? 1100 : 3000, Math.round(base * props.density)))

  const pos = new Float32Array(count * 3)
  const prev = new Float32Array(count * 3)
  const vel = new Float32Array(count * 2)
  const seed = new Float32Array(count)
  const bW = halfW + 10
  const bH = halfH + 10

  for (let i = 0; i < count; i++) {
    const x = (Math.random() * 2 - 1) * bW
    const y = (Math.random() * 2 - 1) * bH
    const z = Z_NEAR + Math.random() * (Z_FAR - Z_NEAR)
    pos[i * 3] = x
    pos[i * 3 + 1] = y
    pos[i * 3 + 2] = z
    prev[i * 3] = x
    prev[i * 3 + 1] = y
    prev[i * 3 + 2] = z
    seed[i] = Math.random()
  }
  return {
    count, pos, prev, vel, seed, bW, bH,
    aspect, halfH, halfW,
    time: Math.random() * 100,
    mouseOn: false,
    mx: 0, my: 0, smx: 0, smy: 0,
    mvx: 0, mvy: 0, lastMoveT: 0,
  }
}

/* ---- 流场模拟：连贯涡流（无散度势流） + 星系旋涡 + 鼠标扰动 ----
 * 势流 ψ = Σ aᵢ·sin(kᵢ·p + ωᵢt)，v = (∂ψ/∂y, −∂ψ/∂x) 解析求导：
 * 无散度 → 相邻粒子速度方向连贯，呈现大尺度「旋臂」整体结构而非碎乱噪点 */
const POTENTIAL = [
  // kx, ky, ω, a（波长 0.5~1.7 倍屏高，缓慢演化）
  [0.04562, 0.03437, 0.21, 45.5],
  [-0.04189, 0.07256, 0.32, 23.9],
  [0.01082, -0.03775, 0.16, 40.7],
  [-0.11204, -0.04527, 0.42, 10.8],
]
function stepSim(dt) {
  const s = sim
  s.time += dt
  const t = s.time
  const { pos, prev, vel, seed, count, bW, bH } = s

  // 能量周期：0.45 ~ 1 缓慢起伏，制造「平静 → 涌动」节奏
  const g = 0.45 + 0.55 * Math.pow(0.5 + 0.5 * Math.sin(t * 0.32 + Math.sin(t * 0.11) * 1.7), 1.6)
  const swirlK = 3.8 * g
  const driftX = 0.9 * Math.sin(t * 0.05)
  const driftY = 0.6 * Math.cos(t * 0.04)
  const invH = 1 / s.halfH

  // 鼠标平滑跟随 + 速度衰减
  if (s.mouseOn) {
    const k = 1 - Math.exp(-dt * 9)
    s.smx += (s.mx - s.smx) * k
    s.smy += (s.my - s.smy) * k
    s.mvx *= Math.exp(-dt * 3.5)
    s.mvy *= Math.exp(-dt * 3.5)
  }
  const useMouse = props.interactive && s.mouseOn && !reducedMotion
  const R2 = 900 // 半径 30 世界单位

  // 较大的跟随时间常数：粒子速度向流场收敛，轨迹更顺滑连贯
  const smooth = 1 - Math.exp(-dt * 2.2)

  for (let i = 0; i < count; i++) {
    const i3 = i * 3
    const i2 = i * 2
    const x = pos[i3]
    const y = pos[i3 + 1]
    const z = pos[i3 + 2]

    // 1) 连贯涡流：势流解析求导（4 次 cos 覆盖全部速度分量）
    let tx = 0
    let ty = 0
    for (let e = 0; e < 4; e++) {
      const E = POTENTIAL[e]
      const c = Math.cos(E[0] * x + E[1] * y + E[2] * t)
      tx += E[3] * E[1] * c
      ty -= E[3] * E[0] * c
    }
    tx *= g
    ty *= g

    // 2) 星系旋涡：绕原点切向流动，内侧更快
    const r = Math.sqrt(x * x + y * y) + 1e-4
    const inv = 1 / r
    const om = swirlK / (0.42 + r * invH)
    tx += -y * inv * om
    ty += x * inv * om

    // 3) 极缓慢的整体漂移
    tx += driftX
    ty += driftY

    // 4) 越出视野的粒子被柔和拉回
    const edge = Math.max(Math.abs(x) / bW, Math.abs(y) / bH)
    if (edge > 1) {
      const f = (edge - 1) * 2.4
      tx -= x * f
      ty -= y * f
    }

    // 5) 鼠标扰动：径向推斥 + 绕光标旋转 + 顺光标速度拖走
    if (useMouse) {
      const dx = x - s.smx
      const dy = y - s.smy
      const d2 = dx * dx + dy * dy
      if (d2 < R2) {
        const fall = Math.exp((-d2 / R2) * 3)
        const dr = Math.sqrt(d2) + 1e-3
        tx += (dx / dr) * 26 * fall - (dy / dr) * 18 * fall + s.mvx * 0.8 * fall
        ty += (dy / dr) * 26 * fall + (dx / dr) * 18 * fall + s.mvy * 0.8 * fall
      }
    }

    // 6) 速度平滑后积分
    vel[i2] += (tx - vel[i2]) * smooth
    vel[i2 + 1] += (ty - vel[i2 + 1]) * smooth

    prev[i3] = x
    prev[i3 + 1] = y
    prev[i3 + 2] = z

    let nx = x + vel[i2] * dt
    let ny = y + vel[i2 + 1] * dt
    let nz = z + Math.sin(t * 0.2 + x * 0.008) * 0.35

    // 越界回绕：重置 prev 防止跨屏拖痕
    if (nx > bW) { nx = -bW; ny = (Math.random() * 2 - 1) * bH }
    else if (nx < -bW) { nx = bW; ny = (Math.random() * 2 - 1) * bH }
    if (ny > bH) { ny = -bH; nx = (Math.random() * 2 - 1) * bW }
    else if (ny < -bH) { ny = bH; nx = (Math.random() * 2 - 1) * bW }
    if (nz < Z_NEAR) nz = Z_FAR
    else if (nz > Z_FAR) nz = Z_NEAR

    pos[i3] = nx
    pos[i3 + 1] = ny
    pos[i3 + 2] = nz
    if (seed[i] > 0.995) seed[i] = Math.random() // 极少数粒子换色，色彩缓慢流转
  }
}

/* ---- 渲染管线：单 draw call 拉伸四边形 ---- */
function buildMesh() {
  const n = sim.count
  const quadCount = n * 4
  const corners = new Float32Array(quadCount * 2)
  const seeds = new Float32Array(quadCount)
  const index = new Uint32Array(n * 6)
  for (let i = 0; i < n; i++) {
    const q = i * 4
    corners[q * 2] = -1; corners[q * 2 + 1] = -1
    corners[(q + 1) * 2] = 1; corners[(q + 1) * 2 + 1] = -1
    corners[(q + 2) * 2] = -1; corners[(q + 2) * 2 + 1] = 1
    corners[(q + 3) * 2] = 1; corners[(q + 3) * 2 + 1] = 1
    seeds[q] = seeds[q + 1] = seeds[q + 2] = seeds[q + 3] = sim.seed[i]
    const v = i * 6
    index[v] = q; index[v + 1] = q + 1; index[v + 2] = q + 2
    index[v + 3] = q + 1; index[v + 4] = q + 3; index[v + 5] = q + 2
  }

  geometry = new THREE.BufferGeometry()
  geometry.setAttribute("aCorner", new THREE.BufferAttribute(corners, 2))
  geometry.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1))
  geometry.setAttribute("aPos", new THREE.BufferAttribute(new Float32Array(quadCount * 3), 3))
  geometry.setAttribute("aPrev", new THREE.BufferAttribute(new Float32Array(quadCount * 3), 3))
  geometry.setIndex(new THREE.BufferAttribute(index, 1))

  material = new THREE.ShaderMaterial({
    transparent: true,
    depthTest: false,
    depthWrite: false,
    premultipliedAlpha: true,
    blending: THREE.NormalBlending,
    uniforms: {
      uAspect: { value: sim.aspect },
      uViewportH: { value: 1080 },
      uSize: { value: 5.5 },
      uStretch: { value: 8 },
      uMaxLen: { value: 60 },
      uRefW: { value: CAM_DIST },
      uOpacity: { value: PALETTES.dark.opacity },
      uSharp: { value: PALETTES.dark.sharp },
      uCoreCol: { value: new THREE.Color(PALETTES.dark.core) },
      uColorA: { value: new THREE.Color(PALETTES.dark.colors[0]) },
      uColorB: { value: new THREE.Color(PALETTES.dark.colors[1]) },
      uColorC: { value: new THREE.Color(PALETTES.dark.colors[2]) },
      uColorD: { value: new THREE.Color(PALETTES.dark.colors[3]) },
    },
    vertexShader: /* glsl */ `
      uniform float uAspect;
      uniform float uViewportH;
      uniform float uSize;
      uniform float uStretch;
      uniform float uMaxLen;
      uniform float uRefW;
      uniform vec3 uColorA;
      uniform vec3 uColorB;
      uniform vec3 uColorC;
      uniform vec3 uColorD;
      attribute vec3 aPos;
      attribute vec3 aPrev;
      attribute vec2 aCorner;
      attribute float aSeed;
      varying vec2 vCorner;
      varying vec3 vColor;
      varying float vFade;
      varying float vGlow;

      void main() {
        vec4 clip1 = projectionMatrix * modelViewMatrix * vec4(aPos, 1.0);
        vec4 clip0 = projectionMatrix * modelViewMatrix * vec4(aPrev, 1.0);
        float w1 = max(clip1.w, 0.0001);
        float w0 = max(clip0.w, 0.0001);
        vec2 n1 = clip1.xy / w1;
        vec2 n0 = clip0.xy / w0;

        // 屏幕空间速度方向（宽高比校正后的 NDC 空间）
        vec2 dh = (n1 - n0) * vec2(uAspect, 1.0);
        float distH = length(dh);
        vec2 dir = distH > 1e-6 ? dh / distH : vec2(1.0, 0.0);

        float persp = clamp(uRefW / w1, 0.35, 1.6);
        float distPx = distH * uViewportH * 0.5;
        float size = uSize * persp * (0.6 + 0.85 * fract(aSeed * 13.37));
        // 拖尾长度按粒子个体差异化：少数粒子拉长尾，多数只有短尾
        float streakGain = uStretch * (0.35 + 0.9 * fract(aSeed * 5.7));
        float len = max(size, min(distPx * streakGain, uMaxLen) * persp);

        vec2 perp = vec2(-dir.y, dir.x);
        float k = 2.0 / uViewportH;
        vec2 offH = (dir * aCorner.x * len + perp * aCorner.y * size) * k;
        vec2 ndc = n1 + vec2(offH.x / uAspect, offH.y);
        gl_Position = vec4(ndc * w1, clip1.z, w1);

        // 按种子分档取色 + 明度抖动
        vec3 c = uColorA;
        if (aSeed > 0.24) c = uColorB;
        if (aSeed > 0.48) c = uColorC;
        if (aSeed > 0.72) c = uColorD;
        c *= 0.8 + 0.4 * fract(aSeed * 7.31);
        vColor = c;
        vCorner = aCorner;
        vFade = persp < 0.55 ? persp / 0.55 : 1.0;
        // 速度加权亮度：快粒子成为「主线条」，慢粒子退为背景尘埃 → 层次感
        vGlow = clamp(0.5 + distPx * 0.12, 0.5, 1.25);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uOpacity;
      uniform float uSharp;
      uniform vec3 uCoreCol;
      varying vec2 vCorner;
      varying vec3 vColor;
      varying float vFade;
      varying float vGlow;

      void main() {
        float x = vCorner.x;
        float r = abs(vCorner.y);
        // 彗星轮廓：横向截面柔边 + 尾淡头亮 + 高斯亮核
        // uSharp=1（浅色主题）时收紧截面与亮核，墨点边缘利落不糊底
        float across = 1.0 - smoothstep(mix(0.55, 0.28, uSharp), mix(1.0, 0.78, uSharp), r);
        float tail = smoothstep(-1.0, 0.55, x);
        float head = 1.0 - smoothstep(0.5, 1.0, x);
        float cx = (x - 0.42) * mix(1.8, 2.8, uSharp);
        float core = exp(-cx * cx - r * r * mix(2.0, 3.2, uSharp));
        float a = across * tail * head * 0.55 + core * across * 0.85;
        a *= uOpacity * vFade * vGlow;
        if (a < 0.003) discard;
        vec3 col = mix(vColor, uCoreCol, core * 0.3);
        gl_FragColor = vec4(col * a, a);
      }
    `,
  })

  mesh = new THREE.Mesh(geometry, material)
  mesh.frustumCulled = false
  scene.add(mesh)
}

function syncAttributes() {
  const n = sim.count
  const posAttr = geometry.getAttribute("aPos")
  const prevAttr = geometry.getAttribute("aPrev")
  const seedAttr = geometry.getAttribute("aSeed")
  const src = sim.pos
  const prv = sim.prev
  const dst = posAttr.array
  const dstP = prevAttr.array
  for (let i = 0; i < n; i++) {
    const s3 = i * 3
    const d = i * 12
    dst[d] = dst[d + 3] = dst[d + 6] = dst[d + 9] = src[s3]
    dst[d + 1] = dst[d + 4] = dst[d + 7] = dst[d + 10] = src[s3 + 1]
    dst[d + 2] = dst[d + 5] = dst[d + 8] = dst[d + 11] = src[s3 + 2]
    dstP[d] = dstP[d + 3] = dstP[d + 6] = dstP[d + 9] = prv[s3]
    dstP[d + 1] = dstP[d + 4] = dstP[d + 7] = dstP[d + 10] = prv[s3 + 1]
    dstP[d + 2] = dstP[d + 5] = dstP[d + 8] = dstP[d + 11] = prv[s3 + 2]
  }
  // 种子可能被缓慢轮换
  const sd = seedAttr.array
  for (let i = 0; i < n; i++) {
    const v = sim.seed[i]
    sd[i * 4] = sd[i * 4 + 1] = sd[i * 4 + 2] = sd[i * 4 + 3] = v
  }
  posAttr.needsUpdate = true
  prevAttr.needsUpdate = true
  seedAttr.needsUpdate = true
}

/* ---- 尺寸 / 主题 ---- */
function resize() {
  if (!renderer || !sim || disposed) return
  const el = host.value
  const w = Math.max(1, el.clientWidth)
  const h = Math.max(1, el.clientHeight)
  const dpr = Math.min(window.devicePixelRatio || 1, 1.75)
  renderer.setPixelRatio(dpr)
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()

  // 世界边界随视口变化（保持粒子相对位置，仅更新包裹盒）
  const halfH = Math.tan(((FOV / 2) * Math.PI) / 180) * CAM_DIST
  sim.halfH = halfH
  sim.halfW = halfH * camera.aspect
  sim.aspect = camera.aspect
  sim.bW = sim.halfW + 10
  sim.bH = halfH + 10

  material.uniforms.uAspect.value = camera.aspect
  material.uniforms.uViewportH.value = renderer.domElement.height
  material.uniforms.uSize.value = 5.5 * dpr
}

function applyTheme() {
  if (!material) return
  const mode = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark"
  const p = PALETTES[mode]
  material.uniforms.uColorA.value.set(p.colors[0])
  material.uniforms.uColorB.value.set(p.colors[1])
  material.uniforms.uColorC.value.set(p.colors[2])
  material.uniforms.uColorD.value.set(p.colors[3])
  material.uniforms.uCoreCol.value.set(p.core)
  material.uniforms.uOpacity.value = p.opacity
  material.uniforms.uSharp.value = p.sharp
}

/* ---- 鼠标 ---- */
function onPointerMove(e) {
  if (!sim) return
  const rect = host.value.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const nx = ((e.clientX - rect.left) / rect.width) * 2 - 1
  const ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1)
  const wx = nx * sim.halfW
  const wy = ny * sim.halfH
  const now = performance.now()
  if (sim.mouseOn) {
    const dt = Math.max(8, now - sim.lastMoveT) / 1000
    const a = 0.25
    sim.mvx = sim.mvx * (1 - a) + ((wx - sim.mx) / dt) * a
    sim.mvy = sim.mvy * (1 - a) + ((wy - sim.my) / dt) * a
  }
  sim.mx = wx
  sim.my = wy
  sim.smx = sim.smx || wx
  sim.smy = sim.smy || wy
  sim.mouseOn = true
  sim.lastMoveT = now
}
function onPointerLeave() {
  if (sim) sim.mouseOn = false
}

/* ---- 主循环 ---- */
let lastT = 0
let paused = false
function frame(now) {
  if (disposed) return
  rafId = requestAnimationFrame(frame)
  if (paused) return
  const dt = Math.min(1 / 30, lastT ? (now - lastT) / 1000 : 1 / 60)
  lastT = now
  stepSim(dt)
  syncAttributes()
  renderer.render(scene, camera)
}
function onVisibility() {
  paused = document.hidden
  if (!paused) lastT = 0
}

onMounted(async () => {
  reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
  try {
    THREE = await import("three")
    if (disposed) return // 等待加载期间组件已卸载
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: "high-performance" })
  } catch {
    return // WebGL 不可用 / 资源加载失败：保持透明背景静默降级
  }
  renderer.setClearColor(0x000000, 0)
  renderer.domElement.className = "pf-canvas"
  host.value.appendChild(renderer.domElement)
  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(FOV, 1, 10, 400)
  camera.position.set(0, 0, CAM_DIST)

  sim = initSim(host.value.clientWidth || window.innerWidth, host.value.clientHeight || window.innerHeight)
  buildMesh()
  resize()
  applyTheme()

  // 预热流场：首帧即有拖尾，避免「从零启动」的突兀
  for (let i = 0; i < 40; i++) stepSim(1 / 30)
  syncAttributes()
  renderer.render(scene, camera)

  if (reducedMotion) {
    // 减少动效：只渲染静态点阵，窗口变化时重绘
    resizeObs = new ResizeObserver(() => {
      resize()
      stepSim(1 / 60)
      syncAttributes()
      renderer.render(scene, camera)
    })
    resizeObs.observe(host.value)
  } else {
    resizeObs = new ResizeObserver(() => resize())
    resizeObs.observe(host.value)
    window.addEventListener("pointermove", onPointerMove, { passive: true })
    window.addEventListener("pointerdown", onPointerMove, { passive: true })
    document.documentElement.addEventListener("pointerleave", onPointerLeave)
    document.addEventListener("visibilitychange", onVisibility)
    rafId = requestAnimationFrame(frame)
  }

  // 跟随主题切换换色
  themeObs = new MutationObserver(applyTheme)
  themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] })
})

onBeforeUnmount(() => {
  disposed = true
  cancelAnimationFrame(rafId)
  resizeObs?.disconnect()
  themeObs?.disconnect()
  window.removeEventListener("pointermove", onPointerMove)
  window.removeEventListener("pointerdown", onPointerMove)
  document.documentElement.removeEventListener("pointerleave", onPointerLeave)
  document.removeEventListener("visibilitychange", onVisibility)
  geometry?.dispose()
  material?.dispose()
  renderer?.domElement?.remove()
  renderer?.dispose()
  renderer = null
})
</script>

<template>
  <!-- page 模式必须挂到 body：父级 .vh-page 的入场动画带 transform，
       会把 position:fixed 的画布困在 1200px 内容列里导致「铺不满全屏」；
       Teleport 到 body + z-index:-1 = body 背景之上、所有内容之下的真·全视口底 -->
  <Teleport to="body">
    <div v-if="variant === 'page'" ref="host" class="pfield pf-page" aria-hidden="true"></div>
  </Teleport>
  <div v-if="variant === 'hero'" ref="host" class="pfield pf-hero" aria-hidden="true"></div>
</template>

<style scoped>
.pfield {
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}
.pfield.pf-page {
  position: fixed;
  /* body 背景之上、其余内容之下（负 z-index 仍绘制在根背景之前的内容之后） */
  z-index: -1;
}
.pfield.pf-hero { position: absolute; z-index: 0; }

/* canvas 由 three.js 运行时插入 */
.pfield :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
