<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import {
  PhPlayCircle as PlayCircle,
  PhWarningCircle as WarningCircle,
  PhCrownSimple as CrownSimple,
  PhDatabase as Database,
  PhPlugsConnected as PlugsConnected,
  PhShieldCheck as ShieldCheck,
  PhSparkle as Sparkle,
  PhArrowRight as ArrowRight,
  PhArrowsClockwise as ArrowsClockwise,
  PhEye as Eye,
  PhEyeSlash as EyeSlash,
} from "@phosphor-icons/vue"
import api from "../api/client"
import { useAuthStore } from "../stores/auth"
import VhSpinner from "../components/VhSpinner.vue"
import VhThemeToggle from "../components/VhThemeToggle.vue"
import VhLoginCharacters from "../components/VhLoginCharacters.vue"
import VhPasswordTier from "../components/VhPasswordTier.vue"

const auth = useAuthStore()
const router = useRouter()

/* ============ 左侧互动角色面板（借鉴布局） ============ */
const isTyping = ref(false)
const charsWrapRef = ref(null)
const charsScale = ref(1)

// 角色画布原始 550px 宽，面板变窄时等比缩小
let charsRO = null
onMounted(() => {
  if (charsWrapRef.value && "ResizeObserver" in window) {
    charsRO = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect?.width ?? 0
      charsScale.value = Math.max(0.55, Math.min(1, w / 580))
    })
    charsRO.observe(charsWrapRef.value)
  }
})
onBeforeUnmount(() => {
  charsRO?.disconnect()
})

const passwordLength = computed(() => password.value.length)

/* ============ 高级感氛围层：视频背景 + 卡片 3D 倾斜 + 光晕视差 ============
 * 性能约束：仅 transform / opacity / CSS 变量，全部走合成层；
 * 触屏与 prefers-reduced-motion 自动关闭全部指针特效。 */
const rootRef = ref(null)
const cardRef = ref(null)
const videoRef = ref(null)
const videoReady = ref(false)

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
const finePointer = window.matchMedia("(pointer: fine)").matches
const fxOn = finePointer && !reducedMotion

let fxRaf = 0
let targetRX = 0
let targetRY = 0
let curRX = 0
let curRY = 0
let glowMX = 0
let glowMY = 0

function fxTick() {
  fxRaf = 0
  curRX += (targetRX - curRX) * 0.12
  curRY += (targetRY - curRY) * 0.12
  const root = rootRef.value
  if (root) {
    root.style.setProperty("--mx", glowMX.toFixed(3))
    root.style.setProperty("--my", glowMY.toFixed(3))
  }
  const card = cardRef.value
  if (card) {
    card.style.transform =
      `perspective(1100px) rotateX(${curRX.toFixed(2)}deg) rotateY(${curRY.toFixed(2)}deg)`
  }
  /* 收敛到目标后停帧，不空转 */
  if (Math.abs(targetRX - curRX) > 0.02 || Math.abs(targetRY - curRY) > 0.02) {
    fxRaf = requestAnimationFrame(fxTick)
  }
}

function fxSchedule() {
  if (!fxRaf) fxRaf = requestAnimationFrame(fxTick)
}

function onFxPointerMove(e) {
  if (!fxOn) return
  const root = rootRef.value
  if (!root) return
  const r = root.getBoundingClientRect()
  glowMX = ((e.clientX - r.left) / r.width) * 2 - 1
  glowMY = ((e.clientY - r.top) / r.height) * 2 - 1
  const card = cardRef.value
  if (card) {
    const cr = card.getBoundingClientRect()
    const cx = (e.clientX - (cr.left + cr.width / 2)) / (cr.width / 2)
    const cy = (e.clientY - (cr.top + cr.height / 2)) / (cr.height / 2)
    targetRY = Math.max(-1, Math.min(1, cx)) * 3.6
    targetRX = Math.max(-1, Math.min(1, -cy)) * 3.6
  }
  fxSchedule()
}

function onFxPointerLeave() {
  targetRX = 0
  targetRY = 0
  fxSchedule()
}

/* 页面隐藏时暂停背景视频，回前台恢复，省电省 GPU */
function onFxVisibility() {
  const v = videoRef.value
  if (!v) return
  if (document.hidden) v.pause()
  else v.play().catch(() => {})
}

onMounted(() => {
  document.addEventListener("visibilitychange", onFxVisibility)
  /* 指针倾斜走 rAF 插值，关闭 CSS transform 过渡避免双重缓动造成拖尾感 */
  if (fxOn && cardRef.value) {
    cardRef.value.style.transition = "box-shadow 0.4s var(--ease-out)"
  }
})
onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", onFxVisibility)
  if (fxRaf) cancelAnimationFrame(fxRaf)
})

const mode = ref("login") // login | register
const username = ref("")
const password = ref("")
const showPwd = ref(false)
const confirmPassword = ref("")
const captchaId = ref("")
const captchaImg = ref("")
const captchaText = ref("")
// 登录态专用：账号维度被后端锁定（该账号失败次数过多）时，后端回 429 +
// X-Videohub-Captcha: required，此时就地展开人机验证让人机解锁，而不是把
// 本人也挡在门外（定向账号锁死 DoS 的缓解，见 docs/SECURITY.md §3.2）
const needCaptcha = ref(false)
// 登录二步验证（S19）：已开启 TOTP 的账户密码通过后，后端回 401 +
// X-Videohub-Totp: required，就地展开动态码输入（无需重输用户名密码）
const needTotp = ref(false)
const totpCode = ref("")
const error = ref("")
const busy = ref(false)

// 逐字段即时校验（仅注册模式）：失焦校验，报错后输入实时刷新
const fieldErrors = ref({ username: "", password: "", confirmPassword: "", captcha: "" })
const usernameAvailable = ref(false)
let usernameCheckTimer = null

const USERNAME_RE = /^[A-Za-z][A-Za-z0-9_]{2,31}$/

function validateUsername(showRequired = true) {
  const v = username.value.trim()
  usernameAvailable.value = false
  if (!v) {
    fieldErrors.value.username = showRequired ? "请输入用户名" : ""
  } else if (!USERNAME_RE.test(v)) {
    fieldErrors.value.username = "用户名需为 3-32 位，字母开头，仅含字母、数字、下划线"
  } else {
    fieldErrors.value.username = ""
  }
  return !fieldErrors.value.username
}

function validatePassword() {
  if (!password.value) {
    fieldErrors.value.password = "请输入密码"
  } else if (password.value.length < 8) {
    fieldErrors.value.password = "密码至少 8 位"
  } else {
    fieldErrors.value.password = ""
  }
  // 密码变动时联动已填写的确认密码
  if (confirmPassword.value) validateConfirm()
  return !fieldErrors.value.password
}

function validateConfirm() {
  if (!confirmPassword.value) {
    fieldErrors.value.confirmPassword = "请再次输入密码"
  } else if (confirmPassword.value !== password.value) {
    fieldErrors.value.confirmPassword = "两次输入的密码不一致"
  } else {
    fieldErrors.value.confirmPassword = ""
  }
  return !fieldErrors.value.confirmPassword
}

async function checkUsernameTaken() {
  const v = username.value.trim()
  if (mode.value !== "register" || !USERNAME_RE.test(v)) return
  try {
    const { data } = await api.get("/auth/username-available", { params: { username: v } })
    if (username.value.trim() !== v) return // 查询期间用户又改了内容，结果作废
    if (data.available) {
      usernameAvailable.value = true
    } else {
      fieldErrors.value.username = "该用户名已被注册"
    }
  } catch { /* 网络异常静默，提交时由后端兜底 */ }
}

function onUsernameInput() {
  usernameAvailable.value = false
  if (fieldErrors.value.username) validateUsername(false)
  clearTimeout(usernameCheckTimer)
  if (mode.value === "register" && USERNAME_RE.test(username.value.trim())) {
    usernameCheckTimer = setTimeout(checkUsernameTaken, 500)
  }
}

function onUsernameBlur() {
  if (mode.value !== "register") return
  if (validateUsername(false) && username.value.trim()) checkUsernameTaken()
}

function onPasswordInput() {
  if (fieldErrors.value.password) validatePassword()
}

function onPasswordBlur() {
  // 空字段只是路过（Tab 切换）时不报红，提交时再统一提示
  if (mode.value === "register" && (password.value || fieldErrors.value.password)) validatePassword()
}

function onConfirmInput() {
  if (fieldErrors.value.confirmPassword) validateConfirm()
}

function onConfirmBlur() {
  if (mode.value === "register" && (confirmPassword.value || fieldErrors.value.confirmPassword)) validateConfirm()
}

function clearFieldErrors() {
  fieldErrors.value = { username: "", password: "", confirmPassword: "", captcha: "" }
  usernameAvailable.value = false
  clearTimeout(usernameCheckTimer)
}

const FEATURES = [
  { icon: CrownSimple, label: "VIP 长视频解析" },
  { icon: PlugsConnected, label: "多线路切换" },
  { icon: Database, label: "历史记录库" },
]

const CAPS = [
  { icon: Database, label: "全量入库" },
  { icon: PlugsConnected, label: "5 个平台" },
  { icon: ShieldCheck, label: "私有部署" },
]

async function loadCaptcha() {
  captchaText.value = ""
  try {
    const { data } = await api.get("/auth/captcha")
    captchaId.value = data.captcha_id
    captchaImg.value = data.image
  } catch {
    captchaId.value = ""
    captchaImg.value = ""
  }
}

function switchMode(next) {
  if (mode.value === next) return
  mode.value = next
  error.value = ""
  confirmPassword.value = ""
  needCaptcha.value = false
  needTotp.value = false
  totpCode.value = ""
  clearFieldErrors()
  if (next === "register" && !captchaId.value) loadCaptcha()
}

async function submit() {
  error.value = ""
  busy.value = true
  try {
    if (mode.value === "login") {
      if (needTotp.value && !totpCode.value.trim()) {
        error.value = "请输入动态验证码"
        document.getElementById("totp")?.focus()
        return
      }
      if (needCaptcha.value && !captchaText.value.trim()) {
        fieldErrors.value.captcha = "请输入图形验证码"
        // 直接按 id 取元素：此时验证码块已渲染（needCaptcha 为真），可同步定位；
        // 若改用 querySelector(".input-invalid") 会因 Vue 异步刷新而拿不到刚加上的类
        document.getElementById("captcha")?.focus()
        return
      }
      await auth.login(
        username.value.trim(),
        password.value,
        needCaptcha.value ? { id: captchaId.value, text: captchaText.value } : null,
        totpCode.value,
      )
    } else {
      const ok = [validateUsername(), validatePassword(), validateConfirm()]
      if (!captchaText.value.trim()) {
        fieldErrors.value.captcha = "请输入图形验证码"
        ok.push(false)
      } else {
        fieldErrors.value.captcha = ""
      }
      if (ok.includes(false)) {
        document.querySelector(".input-invalid")?.focus()
        return
      }
      await auth.register(username.value.trim(), password.value, captchaId.value, captchaText.value)
    }
    router.push("/")
  } catch (e) {
    error.value = e.friendly || (mode.value === "login" ? "登录失败，请检查用户名与密码" : "注册失败，请稍后重试")
    const captchaRequired = e.response?.headers?.["x-videohub-captcha"] === "required"
    if (mode.value === "register") {
      if (error.value.includes("用户名")) fieldErrors.value.username = error.value
      if (error.value.includes("验证码")) fieldErrors.value.captcha = error.value
      loadCaptcha() // 验证码一次性，失败后换新
    } else if (e.response?.headers?.["x-videohub-totp"] === "required") {
      // 密码已通过，缺/错动态验证码：展开二步验证输入，用户名密码保持不必重输
      needTotp.value = true
      totpCode.value = ""
    } else if (e.response?.status === 429 && captchaRequired) {
      // 账号维锁定（区别于 IP 维限流）：展开验证码，解锁后本人仍能用正确密码登录
      needCaptcha.value = true
      fieldErrors.value.captcha = ""
      loadCaptcha() // 一次性，每次失败都换新图
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div
    ref="rootRef"
    class="login"
    @pointermove="onFxPointerMove"
    @pointerleave="onFxPointerLeave"
  >
    <!-- 主题开关：右上角常驻，登录前也可切换 -->
    <div class="login-theme vh-fade-in" aria-hidden="false">
      <VhThemeToggle />
    </div>

    <!-- ============ 环境层：深空视频 + 弥散霓虹光晕 ============ -->
    <div class="ambient" aria-hidden="true">
      <!-- 深空氛围视频：加载完成后淡入，暗色主题专属；底层渐变兜底保证首帧即有氛围 -->
      <video
        v-if="!reducedMotion"
        ref="videoRef"
        class="bg-video"
        :class="{ ready: videoReady }"
        src="/media/login-bg.mp4"
        autoplay
        muted
        loop
        playsinline
        preload="auto"
        disablepictureinpicture
        @canplay="videoReady = true"
      ></video>
      <span class="bg-shade"></span>
      <span class="glow glow-a"></span>
      <span class="glow glow-b"></span>
      <span class="glow glow-c"></span>
      <span class="grid-space"></span>
      <span class="noise"></span>
    </div>

    <!-- ============ 双栏布局：左侧角色面板 + 右侧登录区 ============ -->
    <div class="layout">
      <!-- 左栏：借鉴过来的品牌 + 互动角色面板 -->
      <aside class="hero vh-fade-in" aria-hidden="false">
        <!-- 品牌标识 -->
        <div class="brand vh-fade-in-down">
          <span class="brand-mark">
            <PlayCircle weight="fill" />
            <i class="brand-ring" aria-hidden="true"></i>
          </span>
          <span class="brand-name">VideoHub</span>
          <span class="vh-eyebrow brand-tag">
            <Sparkle size="11" weight="fill" />
            Parse Engine
          </span>
        </div>

        <!-- 互动角色舞台：跟随输入 / 密码显隐做表情互动 -->
        <div ref="charsWrapRef" class="hero-stage">
          <div
            class="hero-chars vh-fade-in-up"
            style="animation-delay: 0.15s"
            :style="{ transform: `scale(${charsScale})` }"
          >
            <VhLoginCharacters
              :is-typing="isTyping"
              :show-password="showPwd"
              :password-length="passwordLength"
            />
          </div>
        </div>

        <!-- 底部链接 -->
        <div class="hero-foot vh-fade-in" style="animation-delay: 0.35s">
          <router-link to="/disclaimer" class="hero-link">免责声明</router-link>
          <span class="hero-dot" aria-hidden="true"></span>
          <span>私有部署 · 视频解析与管理平台</span>
        </div>
      </aside>

      <!-- 右栏：沿用原有登录卡片与全部逻辑 -->
      <main class="stage">
        <!-- 移动端品牌标识（左栏隐藏时兜底） -->
        <div class="brand brand-mobile vh-fade-in-down">
          <span class="brand-mark">
            <PlayCircle weight="fill" />
            <i class="brand-ring" aria-hidden="true"></i>
          </span>
          <span class="brand-name">VideoHub</span>
        </div>

      <!-- 悬浮毛玻璃登录卡片（指针驱动 3D 倾斜） -->
      <section ref="cardRef" class="card vh-fade-in-up" style="animation-delay: 0.1s" :aria-label="mode === 'login' ? '登录' : '注册'">
        <div class="card-beam" aria-hidden="true"></div>

        <!-- 登录 / 注册 切换 -->
        <div class="tabs" role="tablist">
          <button
            type="button"
            class="tab"
            :class="{ on: mode === 'login' }"
            role="tab"
            :aria-selected="mode === 'login'"
            @click="switchMode('login')"
          >登录</button>
          <button
            type="button"
            class="tab"
            :class="{ on: mode === 'register' }"
            role="tab"
            :aria-selected="mode === 'register'"
            @click="switchMode('register')"
          >注册</button>
          <span class="tab-ink" :class="{ right: mode === 'register' }" aria-hidden="true"></span>
        </div>

        <h1 class="title">{{ mode === "login" ? "欢迎回来" : "创建账号" }}</h1>
        <p class="subtitle">
          {{ mode === "login" ? "使用平台账号继续，登录后即可解析与管理视频" : "注册即可拥有自己的视频库，用户名注册后不可修改" }}
        </p>

        <form class="form" @submit.prevent="submit">
          <div class="vh-field">
            <label for="username">用户名</label>
            <input
              id="username"
              v-model="username"
              class="vh-input"
              :class="{ 'input-invalid': mode === 'register' && fieldErrors.username }"
              type="text"
              autocomplete="username"
              :placeholder="mode === 'login' ? '输入用户名' : '3-32 位，字母开头，仅字母/数字/下划线'"
              :aria-invalid="mode === 'register' && !!fieldErrors.username"
              required
              @input="onUsernameInput"
              @blur="onUsernameBlur(); isTyping = false"
              @focus="isTyping = true"
            />
            <p v-if="mode === 'register' && fieldErrors.username" class="field-error" role="alert">
              <WarningCircle size="13" weight="fill" />
              {{ fieldErrors.username }}
            </p>
            <p v-else-if="mode === 'register' && usernameAvailable" class="field-ok">
              用户名可用
            </p>
          </div>
          <div class="vh-field">
            <label for="password">密码</label>
            <div class="pwd-wrap">
              <input
                id="password"
                v-model="password"
                class="vh-input"
                :class="{ 'input-invalid': mode === 'register' && fieldErrors.password }"
                :type="showPwd ? 'text' : 'password'"
                :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
                placeholder="输入密码（至少 8 位）"
                :aria-invalid="mode === 'register' && !!fieldErrors.password"
                required
                @input="onPasswordInput"
                @blur="onPasswordBlur; isTyping = false"
                @focus="isTyping = true"
              />
              <button
                type="button"
                class="pwd-eye"
                :aria-label="showPwd ? '隐藏密码' : '显示密码'"
                :title="showPwd ? '隐藏密码' : '显示密码'"
                @click="showPwd = !showPwd"
              >
                <Eye v-if="showPwd" size="15" weight="regular" />
                <EyeSlash v-else size="15" weight="regular" />
              </button>
            </div>
            <p v-if="mode === 'register' && fieldErrors.password" class="field-error" role="alert">
              <WarningCircle size="13" weight="fill" />
              {{ fieldErrors.password }}
            </p>
            <!-- 注册模式：实时密码强度段位（青铜 ~ 王者） -->
            <VhPasswordTier v-if="mode === 'register'" :password="password" />
          </div>

          <template v-if="mode === 'register'">
            <div class="vh-field">
              <label for="confirm-password">确认密码</label>
              <input
                id="confirm-password"
                v-model="confirmPassword"
                class="vh-input"
                :class="{ 'input-invalid': fieldErrors.confirmPassword }"
                type="password"
                autocomplete="new-password"
                placeholder="再次输入密码"
                :aria-invalid="!!fieldErrors.confirmPassword"
                required
                @input="onConfirmInput"
                @blur="onConfirmBlur"
              />
              <p v-if="fieldErrors.confirmPassword" class="field-error" role="alert">
                <WarningCircle size="13" weight="fill" />
                {{ fieldErrors.confirmPassword }}
              </p>
            </div>
          </template>

          <!-- 两步验证（仅登录态）：已开启 TOTP 的账户密码通过后出现，输入 6 位
               动态验证码；设备丢失时改输恢复代码（XXXX-XXXX） -->
          <div v-if="mode === 'login' && needTotp" class="vh-field">
            <label for="totp">动态验证码</label>
            <input
              id="totp"
              v-model="totpCode"
              class="vh-input"
              type="text"
              inputmode="numeric"
              autocomplete="one-time-code"
              placeholder="6 位动态验证码"
              maxlength="9"
              autofocus
              required
            />
            <p class="totp-hint">
              该账户已开启两步验证：请输入验证器 App 中的 6 位动态验证码；
              设备不在身边时可输入恢复代码
            </p>
          </div>

          <!-- 人机验证：注册模式必填；登录模式仅当账号维被后端锁定（429 要求）时出现 -->
          <div v-if="mode === 'register' || needCaptcha" class="vh-field">
            <label for="captcha">人机验证</label>
            <div class="captcha-row">
              <input
                id="captcha"
                v-model="captchaText"
                class="vh-input"
                :class="{ 'input-invalid': fieldErrors.captcha }"
                type="text"
                autocomplete="off"
                placeholder="输入图中字符"
                maxlength="4"
                :aria-invalid="!!fieldErrors.captcha"
                required
                @input="fieldErrors.captcha = ''"
              />
              <button
                type="button"
                class="captcha-img"
                title="看不清？点击换一张"
                aria-label="刷新验证码"
                @click="loadCaptcha"
              >
                <img v-if="captchaImg" :src="captchaImg" alt="验证码" />
                <ArrowsClockwise v-else size="16" weight="bold" />
              </button>
            </div>
            <p v-if="fieldErrors.captcha" class="field-error" role="alert">
              <WarningCircle size="13" weight="fill" />
              {{ fieldErrors.captcha }}
            </p>
          </div>

          <button class="vh-btn vh-btn-aurora submit" type="submit" :disabled="busy">
            <VhSpinner v-if="busy" variant="orbit" :size="16" />
            <span>{{ busy ? (mode === "login" ? "登录中" : "注册中") : (mode === "login" ? "登录" : "注册并登录") }}</span>
            <ArrowRight v-if="!busy" size="15" weight="bold" />
          </button>

          <transition name="alert">
            <p v-if="error" class="error" role="alert">
              <WarningCircle size="16" weight="fill" />
              {{ error }}
            </p>
          </transition>
        </form>
      </section>

      <!-- 特性胶囊 -->
      <ul class="features vh-fade-in-up" style="animation-delay: 0.28s">
        <li v-for="f in FEATURES" :key="f.label">
          <component :is="f.icon" size="15" weight="regular" />
          {{ f.label }}
        </li>
      </ul>

        <!-- 能力条 -->
        <ul class="caps vh-fade-in" style="animation-delay: 0.4s">
          <li v-for="c in CAPS" :key="c.label">
            <component :is="c.icon" size="13" weight="regular" />
            {{ c.label }}
          </li>
        </ul>
      </main>
    </div>

    <footer class="foot vh-fade-in" style="animation-delay: 0.55s">
      <span class="dot" aria-hidden="true"></span>
      VideoHub · 视频解析与管理平台
      <span aria-hidden="true">·</span>
      <router-link to="/disclaimer" class="foot-link">免责声明</router-link>
    </footer>
  </div>
</template>

<style scoped>
.login {
  position: relative;
  min-height: 100dvh;
  overflow: hidden;
  background: var(--login-bg);
  display: flex;
  flex-direction: column;
}

/* 右上角主题开关 */
.login-theme {
  position: absolute;
  top: 18px;
  right: 20px;
  z-index: 2;
}

/* ============ 环境层 ============ */
.ambient {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

/* 深空氛围视频：压暗 + 降饱和，甘当底色不抢戏；
 * 默认透明，canplay 后 1.4s 缓慢淡入，避免硬切 */
.bg-video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  filter: saturate(0.9) brightness(0.7);
  transition: opacity 1.4s ease;
}
.bg-video.ready { opacity: 0.62; }
/* 浅色主题：视频会破坏灰白纯净感，直接隐藏（不加载画面） */
html[data-theme="light"] .bg-video { display: none; }

/* 暗角遮罩：压住视频亮度，保证中央卡片的可读性与层次 */
.bg-shade {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(90% 70% at 50% 42%, transparent 30%, rgba(10, 10, 10, 0.52) 100%),
    linear-gradient(180deg, rgba(14, 14, 14, 0.42), rgba(14, 14, 14, 0.16) 42%, rgba(12, 12, 12, 0.55));
}
html[data-theme="light"] .bg-shade { display: none; }

/* 三颗弥散光球：绿 / 琥珀 / 白，沿对角线极弱呼吸浮动；
 * translate 独立属性承载指针视差，与 keyframes 的 transform 呼吸叠加互不冲突 */
.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  animation: vh-float 13s var(--ease-in-out) infinite;
  will-change: transform;
}
.glow-a {
  width: 560px;
  height: 560px;
  top: -180px;
  left: -80px;
  background: radial-gradient(closest-side, rgba(30, 215, 96, 0.14), transparent 72%);
  translate: calc(var(--mx, 0) * 26px) calc(var(--my, 0) * 26px);
}
.glow-b {
  width: 620px;
  height: 620px;
  bottom: -240px;
  right: -120px;
  background: radial-gradient(closest-side, rgba(255, 164, 43, 0.1), transparent 72%);
  animation-delay: -5s;
  animation-duration: 16s;
  translate: calc(var(--mx, 0) * -20px) calc(var(--my, 0) * -20px);
}
.glow-c {
  width: 420px;
  height: 420px;
  top: 34%;
  left: 56%;
  background: radial-gradient(closest-side, rgba(255, 255, 255, 0.04), transparent 70%);
  animation-delay: -9s;
  animation-duration: 19s;
  translate: calc(var(--mx, 0) * 13px) calc(var(--my, 0) * 13px);
}

/* 浅色主题：光球整体调淡，避免浅底上色斑过重 */
html[data-theme="light"] .glow-a { background: radial-gradient(closest-side, rgba(30, 215, 96, 0.1), transparent 72%); }
html[data-theme="light"] .glow-b { background: radial-gradient(closest-side, rgba(255, 164, 43, 0.08), transparent 72%); }
html[data-theme="light"] .glow-c { background: radial-gradient(closest-side, rgba(30, 215, 96, 0.06), transparent 70%); }
html[data-theme="light"] .noise { opacity: 0.03; }

/* 极细网格空间：随指针极缓反向漂移，强化纵深 */
.grid-space {
  position: absolute;
  inset: -10% -6% 0;
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.05) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(80% 60% at 50% 0%, #000 10%, transparent 75%);
  -webkit-mask-image: radial-gradient(80% 60% at 50% 0%, #000 10%, transparent 75%);
  animation: vh-grid-drift 30s linear infinite;
  translate: calc(var(--mx, 0) * -9px) calc(var(--my, 0) * -9px);
}

/* 冷调噪点，压住渐变带状感 */
.noise {
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 0.62  0 0 0 0 0.68  0 0 0 0 0.82  0 0 0 0.5 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 160px 160px;
  opacity: 0.05;
}

/* ============ 双栏布局 ============ */
.layout {
  position: relative;
  z-index: 1;
  flex: 1;
  display: grid;
  grid-template-columns: 1.08fr 1fr;
  min-height: 0;
}

/* 左栏：品牌 + 互动角色 + 底部链接 */
.hero {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 0;
  padding: 34px 44px 22px;
}
.hero-stage {
  flex: 1;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  overflow: hidden;
  min-height: 300px;
  padding-bottom: 8px;
}
.hero-chars {
  transform-origin: bottom center;
}
.hero-foot {
  display: flex;
  align-items: center;
  gap: 14px;
  color: var(--text-3);
  font-size: 12.5px;
  font-family: var(--font-mono);
  letter-spacing: 0.03em;
}
.hero-link {
  color: var(--text-3);
  text-decoration: none;
  transition: color var(--dur-2) ease;
}
.hero-link:hover { color: var(--accent); text-decoration: underline; }
.hero-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
  animation: vh-breathe 2.4s var(--ease-in-out) infinite;
}

/* ============ 内容层 ============ */
.stage {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  min-width: 0;
}

/* 移动端兜底品牌：桌面端隐藏左栏时显示 */
.brand-mobile { display: none; }

/* 品牌标识：hover 时脉冲放大 + 光环加速 */
.brand { display: flex; align-items: center; gap: 10px; margin-bottom: 0; }
.brand-mark {
  position: relative;
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: var(--grad-brand);
  color: #000;
  box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.55), 0 0 26px -6px rgba(30, 215, 96, 0.4);
  transition: transform 0.35s var(--ease-spring), box-shadow 0.35s ease;
}
.brand:hover .brand-mark {
  transform: scale(1.08);
  box-shadow: 0 6px 26px -4px rgba(0, 0, 0, 0.6), 0 0 34px -6px rgba(30, 215, 96, 0.6);
}
.brand:hover .brand-ring { animation-duration: 3.5s; }
.brand-mark :deep(svg) { width: 25px; height: 25px; position: relative; z-index: 1; }
.brand-ring {
  position: absolute;
  inset: -5px;
  border-radius: 50%;
  border: 1px solid rgba(255, 181, 88, 0.45);
  animation: vh-rotate 9s linear infinite;
}
.brand-name { font-size: 21px; font-weight: 700; letter-spacing: -0.01em; color: var(--text-1); }
.brand-tag { margin-left: 4px; }

/* ============ 悬浮毛玻璃卡片 ============ */
.card {
  position: relative;
  width: 100%;
  max-width: 408px;
  padding: 26px 34px 30px;
  border-radius: 16px;
  background: var(--glass-bg);
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
  border: 1px solid var(--glass-line);
  box-shadow:
    var(--shadow-3),
    0 0 44px -12px rgba(30, 215, 96, 0.14);
  transition: box-shadow 0.4s var(--ease-out), transform 0.4s var(--ease-out);
  will-change: transform;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow:
    var(--shadow-3),
    0 0 54px -10px rgba(30, 215, 96, 0.2);
}

/* 卡片上沿一道巡游流光 */
.card-beam {
  position: absolute;
  top: -1px;
  left: 14%;
  right: 14%;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(60, 228, 119, 0.7),
    rgba(255, 181, 88, 0.7),
    transparent
  );
  background-size: 220% 100%;
  animation: card-beam-pan 5.5s linear infinite;
  pointer-events: none;
}
@keyframes card-beam-pan {
  from { background-position: 220% 0; }
  to { background-position: -220% 0; }
}

/* 登录 / 注册 切换页签 */
.tabs {
  position: relative;
  display: flex;
  gap: 4px;
  margin-bottom: 22px;
  padding: 4px;
  border-radius: var(--r-pill);
  background: var(--tint);
  border: 1px solid var(--line);
}
.tab {
  position: relative;
  z-index: 1;
  flex: 1;
  height: 34px;
  border: 0;
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--text-2);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: color var(--dur-2) ease;
}
.tab.on { color: #000; font-weight: 700; }
.tab-ink {
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 4px;
  width: calc(50% - 4px);
  border-radius: var(--r-pill);
  background: #ffffff;
  box-shadow: 0 2px 12px -2px rgba(0, 0, 0, 0.5);
  transition: transform 0.3s var(--ease-out);
}
.tab-ink.right { transform: translateX(100%); }
/* 浅色主题：白色滑块在白卡片上不可见，反转为黑底白字 */
html[data-theme="light"] .tab-ink { background: #121212; box-shadow: 0 2px 12px -2px rgba(0, 0, 0, 0.3); }
html[data-theme="light"] .tab.on { color: #fff; }

.title { margin: 0 0 8px; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
.subtitle { margin: 0 0 26px; color: var(--text-2); font-size: 14px; line-height: 1.6; }

.form { display: flex; flex-direction: column; gap: 18px; }

/* 字段级即时校验：错误文案 / 可用提示 / 输入框错误态 */
.field-error {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 6px 0 0;
  color: var(--danger);
  font-size: 12px;
  line-height: 1.4;
  animation: vh-fade-in 0.2s ease;
}
.field-error :deep(svg) { flex-shrink: 0; }
.field-ok {
  margin: 6px 0 0;
  color: var(--success, #1ed760);
  font-size: 12px;
  animation: vh-fade-in 0.2s ease;
}
.input-invalid {
  border-color: rgba(243, 114, 127, 0.55) !important;
  box-shadow: 0 0 0 3px rgba(243, 114, 127, 0.12) !important;
}

/* 密码可见性切换 */
.pwd-wrap { position: relative; }
.pwd-wrap .vh-input { padding-right: 40px; }
.pwd-eye {
  position: absolute;
  top: 50%;
  right: 7px;
  transform: translateY(-50%);
  display: grid;
  place-items: center;
  width: 27px;
  height: 27px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: color var(--dur-1) ease, background var(--dur-1) ease;
}
.pwd-eye:hover { color: var(--text-1); background: var(--tint-hover); }

/* 两步验证提示：与字段级提示同层级但更克制（信息型而非错误） */
.totp-hint {
  margin: 6px 0 0;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.5;
}

/* 验证码行：输入框 + 可点击刷新的图片 */
.captcha-row {
  display: flex;
  gap: 10px;
  align-items: stretch;
}
.captcha-row .vh-input { flex: 1; min-width: 0; }
.captcha-img {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 108px;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: #f8fafc;
  cursor: pointer;
  overflow: hidden;
  transition: border-color var(--dur-2) ease, box-shadow var(--dur-2) ease;
}
.captcha-img:hover {
  border-color: rgba(60, 228, 119, 0.5);
  box-shadow: 0 0 14px -4px rgba(30, 215, 96, 0.5);
}
.captcha-img img { display: block; width: 100%; height: 100%; object-fit: cover; }
.captcha-img :deep(svg) { color: var(--text-3); }

/* 登录按钮：高饱和极光渐变 + hover 外发光浮起 */
.submit {
  height: 46px;
  margin-top: 6px;
  font-size: 15px;
  gap: 8px;
  border: 0;
}

.error {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: var(--danger-soft);
  border: 1px solid rgba(243, 114, 127, 0.4);
  color: var(--danger);
  font-size: 13px;
}
.error :deep(svg) { flex-shrink: 0; }

.alert-enter-active,
.alert-leave-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.alert-enter-from,
.alert-leave-to { opacity: 0; transform: translateY(-6px); }

/* ============ 特性胶囊 ============ */
.features {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin: 26px 0 0;
  padding: 0;
}
.features li {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 15px;
  border-radius: var(--r-pill);
  background: var(--tint);
  border: 1px solid var(--line);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  color: var(--text-2);
  font-size: 13px;
  font-weight: 500;
  transition: color var(--dur-2) ease, border-color var(--dur-2) ease, box-shadow var(--dur-2) ease,
    transform var(--dur-2) var(--ease-out);
}
.features li:hover {
  color: var(--accent);
  border-color: rgba(60, 228, 119, 0.4);
  box-shadow: 0 0 18px -6px rgba(30, 215, 96, 0.5);
  transform: translateY(-2px);
}
.features :deep(svg) { color: var(--accent); }

.caps {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 18px;
  margin: 18px 0 0;
  padding: 0;
}
.caps li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-3);
  font-size: 12px;
}
.caps :deep(svg) { color: var(--gold-bright); }

/* 底部信息 */
.foot {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 24px 26px;
  color: var(--text-3);
  font-size: 12px;
  font-family: var(--font-mono);
  letter-spacing: 0.03em;
}
.foot .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
  animation: vh-breathe 2.4s var(--ease-in-out) infinite;
}
.foot-link {
  color: var(--text-3);
  text-decoration: none;
  transition: color var(--dur-2) ease;
}
.foot-link:hover { color: var(--accent); text-decoration: underline; }

/* ---- 移动端 ---- */
@media (max-width: 1023px) {
  /* 窄屏：左栏角色面板隐藏，退回单栏居中卡片布局 */
  .layout { grid-template-columns: 1fr; }
  .hero { display: none; }
  .brand-mobile { display: flex; margin-bottom: 26px; }
}
@media (max-width: 560px) {
  .stage { padding: 36px 16px; }
  .card { padding: 20px 22px 24px; border-radius: 16px; }
  .brand-tag { display: none; }
  .features { gap: 8px; }
  .features li { height: 30px; padding: 0 12px; font-size: 12.5px; }
}
</style>
