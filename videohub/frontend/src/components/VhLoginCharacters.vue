<script setup>
import { computed, onBeforeUnmount, ref, watch, watchEffect } from "vue"
import VhEyeBall from "./VhEyeBall.vue"

/**
 * 登录页左侧互动角色组（借鉴自 AnimatedCharacters，Vue 移植版）。
 * 四个几何角色：紫（高个矩形）、黑（中矩形）、橙（半圆）、黄（圆角矩形）。
 * 行为：随机眨眼 / 眼球跟随鼠标 / 输入时身体倾斜对视 /
 *       密码可见时偷偷张望，密码隐藏时紧张站直变高。
 */
const props = defineProps({
  isTyping: { type: Boolean, default: false },
  showPassword: { type: Boolean, default: false },
  passwordLength: { type: Number, default: 0 },
})

/* ---------- 全局鼠标追踪 ---------- */
const mouseX = ref(0)
const mouseY = ref(0)
function onMouseMove(e) {
  mouseX.value = e.clientX
  mouseY.value = e.clientY
}
window.addEventListener("mousemove", onMouseMove, { passive: true })

/* ---------- 随机眨眼 ---------- */
const purpleBlink = ref(false)
const blackBlink = ref(false)
const blinkTimers = []
function scheduleBlink(target) {
  const t1 = setTimeout(() => {
    target.value = true
    const t2 = setTimeout(() => {
      target.value = false
      scheduleBlink(target)
    }, 150)
    blinkTimers.push(t2)
  }, Math.random() * 4000 + 3000)
  blinkTimers.push(t1)
}
scheduleBlink(purpleBlink)
scheduleBlink(blackBlink)

/* ---------- 输入时对视 800ms ---------- */
const looking = ref(false)
let lookTimer = 0
watch(
  () => props.isTyping,
  (v) => {
    if (v) {
      looking.value = true
      clearTimeout(lookTimer)
      lookTimer = setTimeout(() => {
        looking.value = false
      }, 800)
    } else {
      looking.value = false
    }
  }
)

/* ---------- 密码可见时紫角色偷偷张望 ---------- */
const peeking = ref(false)
const peekTimers = []
watchEffect((onCleanup) => {
  if (props.passwordLength > 0 && props.showPassword) {
    let loop = true
    const schedule = () => {
      if (!loop) return
      const t = setTimeout(() => {
        peeking.value = true
        const t2 = setTimeout(() => {
          peeking.value = false
          schedule()
        }, 800)
        peekTimers.push(t2)
      }, Math.random() * 3000 + 2000)
      peekTimers.push(t)
    }
    schedule()
    onCleanup(() => {
      loop = false
      peekTimers.forEach(clearTimeout)
      peeking.value = false
    })
  } else {
    peeking.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener("mousemove", onMouseMove)
  blinkTimers.forEach(clearTimeout)
  clearTimeout(lookTimer)
})

/* ---------- 姿态计算：脸部偏移 + 身体倾斜 ---------- */
const purpleRef = ref(null)
const blackRef = ref(null)
const orangeRef = ref(null)
const yellowRef = ref(null)

function pose(el) {
  if (!el) return { faceX: 0, faceY: 0, skew: 0 }
  const r = el.getBoundingClientRect()
  const cx = r.left + r.width / 2
  const cy = r.top + r.height / 3
  const dx = mouseX.value - cx
  const dy = mouseY.value - cy
  return {
    faceX: Math.max(-15, Math.min(15, dx / 20)),
    faceY: Math.max(-10, Math.min(10, dy / 30)),
    skew: Math.max(-6, Math.min(6, -dx / 120)),
  }
}

const purplePose = computed(() => pose(purpleRef.value))
const blackPose = computed(() => pose(blackRef.value))
const orangePose = computed(() => pose(orangeRef.value))
const yellowPose = computed(() => pose(yellowRef.value))

const hidingPwd = computed(() => props.passwordLength > 0 && !props.showPassword)
const peekMode = computed(() => props.passwordLength > 0 && props.showPassword)
const stiffen = computed(() => peekMode.value || false) // 密码可见时全体站直

const typing = computed(() => props.isTyping || hidingPwd.value)

/* ---- 紫（高个矩形） ---- */
const purpleHeight = computed(() => (typing.value ? "440px" : "400px"))
const purpleTransform = computed(() => {
  if (stiffen.value) return "skewX(0deg)"
  if (typing.value) return `skewX(${(purplePose.value.skew - 12).toFixed(2)}deg) translateX(40px)`
  return `skewX(${purplePose.value.skew.toFixed(2)}deg)`
})
const purpleEyes = computed(() => {
  if (peekMode.value) return { left: "20px", top: "35px" }
  if (looking.value) return { left: "55px", top: "65px" }
  return { left: `${45 + purplePose.value.faceX}px`, top: `${40 + purplePose.value.faceY}px` }
})
const purpleForce = computed(() => {
  if (peekMode.value) return peeking.value ? { x: 4, y: 5 } : { x: -4, y: -4 }
  if (looking.value) return { x: 3, y: 4 }
  return {}
})

/* ---- 黑（中矩形） ---- */
const blackTransform = computed(() => {
  if (stiffen.value) return "skewX(0deg)"
  if (looking.value) return `skewX(${(blackPose.value.skew * 1.5 + 10).toFixed(2)}deg) translateX(20px)`
  if (typing.value) return `skewX(${(blackPose.value.skew * 1.5).toFixed(2)}deg)`
  return `skewX(${blackPose.value.skew.toFixed(2)}deg)`
})
const blackEyes = computed(() => {
  if (peekMode.value) return { left: "10px", top: "28px" }
  if (looking.value) return { left: "32px", top: "12px" }
  return { left: `${26 + blackPose.value.faceX}px`, top: `${32 + blackPose.value.faceY}px` }
})
const blackForce = computed(() => {
  if (peekMode.value) return { x: -4, y: -4 }
  if (looking.value) return { x: 0, y: -4 }
  return {}
})

/* ---- 橙（半圆） ---- */
const orangeTransform = computed(() =>
  stiffen.value ? "skewX(0deg)" : `skewX(${orangePose.value.skew.toFixed(2)}deg)`
)
const orangeEyes = computed(() => {
  if (peekMode.value) return { left: "50px", top: "85px" }
  return { left: `${82 + orangePose.value.faceX}px`, top: `${90 + orangePose.value.faceY}px` }
})
const orangeForce = computed(() => (peekMode.value ? { x: -5, y: -4 } : {}))

/* ---- 黄（圆角矩形） ---- */
const yellowTransform = computed(() =>
  stiffen.value ? "skewX(0deg)" : `skewX(${yellowPose.value.skew.toFixed(2)}deg)`
)
const yellowEyes = computed(() => {
  if (peekMode.value) return { left: "20px", top: "35px" }
  return { left: `${52 + yellowPose.value.faceX}px`, top: `${40 + yellowPose.value.faceY}px` }
})
const yellowMouth = computed(() => {
  if (peekMode.value) return { left: "10px", top: "88px" }
  return { left: `${40 + yellowPose.value.faceX}px`, top: `${88 + yellowPose.value.faceY}px` }
})
const yellowForce = computed(() => (peekMode.value ? { x: -5, y: -4 } : {}))
</script>

<template>
  <div class="chars">
    <!-- 紫：高个矩形（后排） -->
    <div
      ref="purpleRef"
      class="char slow"
      :style="{
        left: '70px',
        width: '180px',
        height: purpleHeight,
        backgroundColor: '#6C3FF5',
        borderRadius: '10px 10px 0 0',
        zIndex: 1,
        transform: purpleTransform,
      }"
    >
      <div class="eyes slow" :style="{ ...purpleEyes, columnGap: '32px' }">
        <VhEyeBall
          :size="18" :pupil-size="7" :max-distance="5"
          eye-color="#ffffff" pupil-color="#2D2D2D"
          :blinking="purpleBlink"
          :force-x="purpleForce.x" :force-y="purpleForce.y"
          :mouse-x="mouseX" :mouse-y="mouseY"
        />
        <VhEyeBall
          :size="18" :pupil-size="7" :max-distance="5"
          eye-color="#ffffff" pupil-color="#2D2D2D"
          :blinking="purpleBlink"
          :force-x="purpleForce.x" :force-y="purpleForce.y"
          :mouse-x="mouseX" :mouse-y="mouseY"
        />
      </div>
    </div>

    <!-- 黑：中矩形（中排） -->
    <div
      ref="blackRef"
      class="char slow"
      :style="{
        left: '240px',
        width: '120px',
        height: '310px',
        backgroundColor: '#2D2D2D',
        borderRadius: '8px 8px 0 0',
        zIndex: 2,
        transform: blackTransform,
      }"
    >
      <div class="eyes slow" :style="{ ...blackEyes, columnGap: '24px' }">
        <VhEyeBall
          :size="16" :pupil-size="6" :max-distance="4"
          eye-color="#ffffff" pupil-color="#2D2D2D"
          :blinking="blackBlink"
          :force-x="blackForce.x" :force-y="blackForce.y"
          :mouse-x="mouseX" :mouse-y="mouseY"
        />
        <VhEyeBall
          :size="16" :pupil-size="6" :max-distance="4"
          eye-color="#ffffff" pupil-color="#2D2D2D"
          :blinking="blackBlink"
          :force-x="blackForce.x" :force-y="blackForce.y"
          :mouse-x="mouseX" :mouse-y="mouseY"
        />
      </div>
    </div>

    <!-- 橙：半圆（前排左） -->
    <div
      ref="orangeRef"
      class="char slow"
      :style="{
        left: '0px',
        width: '240px',
        height: '200px',
        backgroundColor: '#FF9B6B',
        borderRadius: '120px 120px 0 0',
        zIndex: 3,
        transform: orangeTransform,
      }"
    >
      <div class="eyes fast" :style="{ ...orangeEyes, columnGap: '32px' }">
        <VhEyeBall bare :size="12" :max-distance="5" pupil-color="#2D2D2D"
          :force-x="orangeForce.x" :force-y="orangeForce.y"
          :mouse-x="mouseX" :mouse-y="mouseY" />
        <VhEyeBall bare :size="12" :max-distance="5" pupil-color="#2D2D2D"
          :force-x="orangeForce.x" :force-y="orangeForce.y"
          :mouse-x="mouseX" :mouse-y="mouseY" />
      </div>
    </div>

    <!-- 黄：圆角矩形（前排右） -->
    <div
      ref="yellowRef"
      class="char slow"
      :style="{
        left: '310px',
        width: '140px',
        height: '230px',
        backgroundColor: '#E8D754',
        borderRadius: '70px 70px 0 0',
        zIndex: 4,
        transform: yellowTransform,
      }"
    >
      <div class="eyes fast" :style="{ ...yellowEyes, columnGap: '24px' }">
        <VhEyeBall bare :size="12" :max-distance="5" pupil-color="#2D2D2D"
          :force-x="yellowForce.x" :force-y="yellowForce.y"
          :mouse-x="mouseX" :mouse-y="mouseY" />
        <VhEyeBall bare :size="12" :max-distance="5" pupil-color="#2D2D2D"
          :force-x="yellowForce.x" :force-y="yellowForce.y"
          :mouse-x="mouseX" :mouse-y="mouseY" />
      </div>
      <!-- 嘴 -->
      <div
        class="mouth"
        :style="{ ...yellowMouth }"
      ></div>
    </div>
  </div>
</template>

<style scoped>
.chars {
  position: relative;
  width: 550px;
  height: 440px;
  flex-shrink: 0;
}

.char {
  position: absolute;
  bottom: 0;
  transform-origin: bottom center;
}
.char.slow {
  transition: all 0.7s ease-in-out;
}

.eyes {
  position: absolute;
  display: flex;
}
.eyes.slow { transition: all 0.7s ease-in-out; }
.eyes.fast { transition: all 0.2s ease-out; }

.mouth {
  position: absolute;
  width: 80px;
  height: 4px;
  border-radius: 999px;
  background: #2d2d2d;
  transition: all 0.2s ease-out;
}

/* 尊重系统减弱动效 */
@media (prefers-reduced-motion: reduce) {
  .char.slow, .eyes.slow, .eyes.fast, .mouth { transition: none; }
}
</style>
