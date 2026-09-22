<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import {
  PhPlayCircle as PlayCircle,
  PhSquaresFour as SquaresFour,
  PhGearSix as GearSix,
  PhChartLineUp as ChartLine,
  PhSignOut as SignOut,
  PhCaretUp as CaretUp,
  PhShieldCheck as ShieldCheck,
  PhUserCircle as UserCircle,
  PhUserMinus as UserMinus,
  PhLockKey as LockKey,
  PhCompass as Compass,
  PhScroll as Scroll,
  PhX as X,
  PhCopy as Copy,
} from "@phosphor-icons/vue"
import api from "./api/client"
import { useAuthStore } from "./stores/auth"
import { toast } from "./stores/toast"
import VhPopover from "./components/VhPopover.vue"
import VhThemeToggle from "./components/VhThemeToggle.vue"
import VhOnboarding from "./components/VhOnboarding.vue"
import VhBackTop from "./components/VhBackTop.vue"
import VhStardustCursor from "./components/VhStardustCursor.vue"
import VhToast from "./components/VhToast.vue"

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const menuOpen = ref(false)
const routePulse = ref(false)

/* 页面滚动后给导航加上投影，强化「悬浮在内容之上」的层级 */
const navScrolled = ref(false)
function onWinScroll() {
  navScrolled.value = window.scrollY > 8
}
onMounted(() => {
  window.addEventListener("scroll", onWinScroll, { passive: true })
  onWinScroll()
})
onBeforeUnmount(() => window.removeEventListener("scroll", onWinScroll))

// 修改密码弹窗
const pwdOpen = ref(false)
const oldPassword = ref("")
const newPassword = ref("")
const confirmPassword = ref("")
const pwdError = ref("")
const pwdBusy = ref(false)

/* ---- 新手引导 ---- */
const tourOpen = ref(false)
const tourSteps = computed(() => {
  const steps = [
    {
      title: "欢迎使用 VideoHub",
      body: "这是一个视频解析与管理平台。用一分钟带你了解核心玩法，随时可以在右上角菜单重新查看本引导。",
      selector: null,
    },
    {
      title: "粘贴链接，一键解析",
      body: "把 VIP 影视/剧集链接粘贴到输入框，选一条线路后点「解析并播放」即可观看。",
      selector: "[data-tour='parse-input']",
      route: "/",
    },
    {
      title: "你的私人视频库",
      body: "解析过的视频都会自动沉淀到视频库，随时回看与管理。",
      selector: "[data-tour='nav-library']",
    },
  ]
  if (auth.canAnySettings) {
    steps.push({
      title: "平台设置",
      body: "在这里查看已授权的解析线路、平台账号与访问记录。",
      selector: "[data-tour='nav-settings']",
    })
  }
  steps.push({
    title: "账号菜单",
    body: "右上角头像里有修改密码、新手引导和免责声明入口。",
    selector: "[data-tour='user-menu']",
  })
  steps.push({
    title: "使用前必读",
    body: "本平台仅供个人学习和研究使用，切勿用于任何商业用途。解析内容的版权归原平台所有。",
    selector: null,
    link: "/disclaimer",
  })
  return steps
})

// 未完成过引导的用户（含刚注册）自动弹出；完成后不再打扰
watch(
  () => [auth.loaded, auth.user?.onboarding_completed],
  ([loaded, done]) => {
    if (loaded && auth.user && done === false && !tourOpen.value) tourOpen.value = true
  },
  { immediate: true },
)

function closeTour() {
  tourOpen.value = false
  auth.completeOnboarding()
}

function replayTour() {
  menuOpen.value = false
  tourOpen.value = true
}

function gotoDisclaimer() {
  menuOpen.value = false
  router.push("/disclaimer")
}

const navItems = computed(() => {
  const items = [
    { to: "/", label: "解析", icon: PlayCircle, match: (p) => p === "/", tour: null },
    { to: "/library", label: "视频库", icon: SquaresFour, match: (p) => p.startsWith("/library") || p.startsWith("/player"), tour: "nav-library" },
  ]
  if (auth.can("dashboard")) {
    items.push({ to: "/dashboard", label: "看板", icon: ChartLine, match: (p) => p.startsWith("/dashboard"), tour: null })
  }
  if (auth.canAnySettings) {
    items.push({ to: "/settings", label: "设置", icon: GearSix, match: (p) => p.startsWith("/settings"), tour: "nav-settings" })
  }
  return items
})

const initial = computed(() => (auth.user?.username || "?").slice(0, 1).toUpperCase())

/* 路由切换时顶部走一道扫描光，给页面跳转一个「引擎启动」的仪式感 */
watch(
  () => route.fullPath,
  () => {
    routePulse.value = false
    requestAnimationFrame(() => {
      routePulse.value = true
      setTimeout(() => { routePulse.value = false }, 720)
    })
  },
)

function openPwdDialog() {
  menuOpen.value = false
  oldPassword.value = ""
  newPassword.value = ""
  confirmPassword.value = ""
  pwdError.value = ""
  pwdOpen.value = true
}

async function submitPassword() {
  pwdError.value = ""
  if (newPassword.value !== confirmPassword.value) {
    pwdError.value = "两次输入的新密码不一致"
    return
  }
  pwdBusy.value = true
  try {
    await auth.changePassword(oldPassword.value, newPassword.value)
    pwdOpen.value = false
    // 改密后全端下线（含当前设备，后端已清会话）：本地同步清掉用户态并回登录页
    auth.user = null
    toast.success("密码修改成功，请使用新密码重新登录")
    router.push("/login")
  } catch (e) {
    pwdError.value = e.friendly || "修改失败，请稍后重试"
  } finally {
    pwdBusy.value = false
  }
}

// 注销账户弹窗
const delOpen = ref(false)
const delPassword = ref("")
const delError = ref("")
const delBusy = ref(false)

function openDelDialog() {
  menuOpen.value = false
  delPassword.value = ""
  delError.value = ""
  delOpen.value = true
}

async function submitDeleteAccount() {
  delError.value = ""
  if (!window.confirm("再次确认：注销后账号与全部解析记录将被永久删除，无法恢复。确定继续吗？")) {
    return
  }
  delBusy.value = true
  try {
    await auth.deleteAccount(delPassword.value)
    delOpen.value = false
    // 注销即登出（后端已清会话）：本地清掉用户态并回登录页
    auth.user = null
    toast.success("账户已注销，名下解析记录已一并删除")
    router.push("/login")
  } catch (e) {
    delError.value = e.friendly || "注销失败，请稍后重试"
  } finally {
    delBusy.value = false
  }
}

/* ---- 两步验证（TOTP，S19）----
 * 流程：off →（setup 领密钥+扫码）→ 输入动态码 enable → 展示一次性恢复代码
 * （codes，必须确认已保存）→ on；关闭需密码 + 动态码/恢复代码双确认 */
const mfaOpen = ref(false)
const mfaPhase = ref("off") // off | setup | codes | on | disabling
const mfaBusy = ref(false)
const mfaError = ref("")
const mfaSetup = ref(null) // { secret, otpauth_uri, qr_png }
const mfaCode = ref("")
const mfaRecoveryCodes = ref([])
const mfaDisablePassword = ref("")
const mfaDisableCode = ref("")

function openMfaDialog() {
  menuOpen.value = false
  mfaError.value = ""
  mfaCode.value = ""
  mfaDisablePassword.value = ""
  mfaDisableCode.value = ""
  mfaPhase.value = auth.user?.totp_enabled ? "on" : "off"
  mfaOpen.value = true
}

async function startMfaSetup() {
  mfaError.value = ""
  mfaBusy.value = true
  try {
    const { data } = await api.post("/auth/totp/setup")
    mfaSetup.value = data
    mfaCode.value = ""
    mfaPhase.value = "setup"
  } catch (e) {
    mfaError.value = e.friendly || "获取密钥失败，请稍后再试"
  } finally {
    mfaBusy.value = false
  }
}

async function confirmMfaEnable() {
  mfaError.value = ""
  mfaBusy.value = true
  try {
    const { data } = await api.post("/auth/totp/enable", { code: mfaCode.value.trim() })
    mfaRecoveryCodes.value = data.recovery_codes || []
    if (auth.user) auth.user.totp_enabled = true
    mfaPhase.value = "codes"
  } catch (e) {
    mfaError.value = e.friendly || "验证失败，请稍后再试"
  } finally {
    mfaBusy.value = false
  }
}

async function submitMfaDisable() {
  mfaError.value = ""
  mfaBusy.value = true
  try {
    await api.post("/auth/totp/disable", {
      password: mfaDisablePassword.value,
      code: mfaDisableCode.value.trim(),
    })
    if (auth.user) auth.user.totp_enabled = false
    mfaOpen.value = false
    toast.success("两步验证已关闭")
  } catch (e) {
    mfaError.value = e.friendly || "操作失败，请稍后再试"
  } finally {
    mfaBusy.value = false
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success("已复制到剪贴板")
  } catch {
    toast.error("复制失败，请手动选择复制")
  }
}

async function onLogout() {
  menuOpen.value = false
  try {
    await auth.logout()
    router.push("/login")
  } catch (e) {
    toast.error(e.friendly || "退出失败，请稍后重试")
  }
}

function goto(to) {
  menuOpen.value = false
  router.push(to)
}
</script>

<template>
  <div class="app">
    <!-- 全局星尘彗尾光标（触屏 / 减少动效时自动不渲染，保留原生光标） -->
    <VhStardustCursor />

    <!-- 路由切换扫描光 -->
    <span v-if="routePulse" class="route-beam" aria-hidden="true"></span>

    <header v-if="auth.user" class="nav" :class="{ scrolled: navScrolled }">
      <div class="nav-inner">
        <router-link to="/" class="brand" aria-label="VideoHub 首页">
          <span class="brand-mark">
            <PlayCircle weight="fill" />
            <i class="brand-ring" aria-hidden="true"></i>
          </span>
          <span class="brand-name">VideoHub</span>
        </router-link>

        <nav class="links" aria-label="主导航">
          <router-link
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="link"
            :class="{ active: item.match(route.path) }"
            :data-tour="item.tour || undefined"
          >
            <component :is="item.icon" size="17" weight="regular" />
            {{ item.label }}
          </router-link>
        </nav>

        <div class="spacer"></div>

        <!-- 主题开关：暗色 / 浅色 -->
        <VhThemeToggle />

        <!-- 用户菜单（Popover） -->
        <VhPopover
          v-model="menuOpen"
          placement="bottom-end"
          :offset="12"
          :width="248"
          padding="10px"
        >
          <template #default>
            <button class="user" :class="{ on: menuOpen }" aria-label="账号菜单" data-tour="user-menu">
              <span class="avatar" aria-hidden="true">{{ initial }}</span>
              <span class="username">{{ auth.user.username }}</span>
              <CaretUp size="13" weight="bold" class="user-caret" :class="{ flip: menuOpen }" />
            </button>
          </template>

          <template #content>
            <div class="menu">
              <div class="menu-id">
                <span class="menu-avatar" aria-hidden="true">{{ initial }}</span>
                <span class="menu-meta">
                  <span class="menu-name">{{ auth.user.username }}</span>
                  <span class="menu-role">
                    <ShieldCheck v-if="auth.user.is_admin" size="12" weight="fill" />
                    <UserCircle v-else size="12" weight="regular" />
                    {{ auth.user.is_admin ? "管理员" : "普通用户" }}
                  </span>
                </span>
              </div>

              <div class="menu-links">
                <button class="menu-item" @click="openPwdDialog">
                  <LockKey size="15" weight="regular" />
                  修改密码
                </button>
                <button class="menu-item" @click="openMfaDialog">
                  <ShieldCheck size="15" weight="regular" />
                  <span class="mfa-label">
                    两步验证
                    <em v-if="auth.user?.totp_enabled" class="mfa-badge">已开启</em>
                  </span>
                </button>
                <button class="menu-item" @click="goto('/library')">
                  <SquaresFour size="15" weight="regular" />
                  我的视频库
                </button>
                <button class="menu-item" @click="replayTour">
                  <Compass size="15" weight="regular" />
                  新手引导
                </button>
                <button class="menu-item" @click="gotoDisclaimer">
                  <Scroll size="15" weight="regular" />
                  免责声明
                </button>
                <button v-if="auth.canAnySettings" class="menu-item" @click="goto('/settings')">
                  <GearSix size="15" weight="regular" />
                  平台设置
                </button>
              </div>

              <button class="menu-item danger" @click="openDelDialog">
                <UserMinus size="15" weight="regular" />
                注销账户
              </button>
              <button class="menu-item danger no-divider" @click="onLogout">
                <SignOut size="15" weight="regular" />
                退出登录
              </button>
            </div>
          </template>
        </VhPopover>
      </div>
    </header>

    <main class="main" :class="{ flush: !auth.user }">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- 全局页脚 -->
    <footer v-if="auth.user" class="foot">
      <span>VideoHub · 视频解析与管理平台</span>
      <span class="foot-sep" aria-hidden="true">·</span>
      <router-link to="/disclaimer" class="foot-link">免责声明：仅供个人学习与研究使用</router-link>
      <span class="foot-sep" aria-hidden="true">·</span>
      <span class="foot-ver num">Parse Engine v2</span>
    </footer>

    <!-- 回到顶部 -->
    <VhBackTop v-if="auth.user" />

    <!-- 新手引导 -->
    <VhOnboarding v-model="tourOpen" :steps="tourSteps" @finish="auth.completeOnboarding" />

    <!-- 全局操作反馈通知 -->
    <VhToast />

    <!-- 修改密码弹窗 -->
    <teleport to="body">
      <transition name="pwd-fade">
        <div v-if="pwdOpen" class="pwd-mask" @click.self="pwdOpen = false">
          <section class="pwd-dialog" role="dialog" aria-label="修改密码">
            <header class="pwd-head">
              <h2 class="pwd-title">
                <LockKey size="17" weight="regular" />
                修改密码
              </h2>
              <button class="pwd-close" aria-label="关闭" @click="pwdOpen = false">
                <X size="16" weight="bold" />
              </button>
            </header>
            <form class="pwd-form" @submit.prevent="submitPassword">
              <div class="vh-field">
                <label for="old-password">原密码</label>
                <input
                  id="old-password"
                  v-model="oldPassword"
                  class="vh-input"
                  type="password"
                  autocomplete="current-password"
                  placeholder="输入当前密码"
                  required
                />
              </div>
              <div class="vh-field">
                <label for="new-password">新密码</label>
                <input
                  id="new-password"
                  v-model="newPassword"
                  class="vh-input"
                  type="password"
                  autocomplete="new-password"
                  placeholder="至少 8 位"
                  required
                />
              </div>
              <div class="vh-field">
                <label for="confirm-new-password">确认新密码</label>
                <input
                  id="confirm-new-password"
                  v-model="confirmPassword"
                  class="vh-input"
                  type="password"
                  autocomplete="new-password"
                  placeholder="再次输入新密码"
                  required
                />
              </div>
              <p v-if="pwdError" class="pwd-error" role="alert">{{ pwdError }}</p>
              <button class="vh-btn vh-btn-aurora pwd-submit" type="submit" :disabled="pwdBusy">
                <span>{{ pwdBusy ? "提交中" : "确认修改" }}</span>
              </button>
            </form>
          </section>
        </div>
      </transition>
    </teleport>

    <!-- 注销账户弹窗 -->
    <teleport to="body">
      <transition name="pwd-fade">
        <div v-if="delOpen" class="pwd-mask" @click.self="delOpen = false">
          <section class="pwd-dialog" role="dialog" aria-label="注销账户">
            <header class="pwd-head">
              <h2 class="pwd-title danger-title">
                <UserMinus size="17" weight="regular" />
                注销账户
              </h2>
              <button class="pwd-close" aria-label="关闭" @click="delOpen = false">
                <X size="16" weight="bold" />
              </button>
            </header>
            <form class="pwd-form" @submit.prevent="submitDeleteAccount">
              <p class="del-warn">
                注销后，账号 <strong>{{ auth.user?.username }}</strong> 及名下全部解析记录将被<strong>永久删除</strong>，无法恢复。请输入登录密码确认操作。
              </p>
              <div class="vh-field">
                <label for="del-password">登录密码</label>
                <input
                  id="del-password"
                  v-model="delPassword"
                  class="vh-input"
                  type="password"
                  autocomplete="current-password"
                  placeholder="输入当前密码确认"
                  required
                />
              </div>
              <p v-if="delError" class="pwd-error" role="alert">{{ delError }}</p>
              <button class="vh-btn vh-btn-danger del-submit" type="submit" :disabled="delBusy">
                <span>{{ delBusy ? "注销中" : "确认注销" }}</span>
              </button>
            </form>
          </section>
        </div>
      </transition>
    </teleport>

    <!-- 两步验证弹窗（TOTP，S19） -->
    <teleport to="body">
      <transition name="pwd-fade">
        <div v-if="mfaOpen" class="pwd-mask" @click.self="mfaOpen = false">
          <section class="pwd-dialog mfa-dialog" role="dialog" aria-label="两步验证">
            <header class="pwd-head">
              <h2 class="pwd-title">
                <ShieldCheck size="17" weight="regular" />
                两步验证
              </h2>
              <button class="pwd-close" aria-label="关闭" @click="mfaOpen = false">
                <X size="16" weight="bold" />
              </button>
            </header>

            <!-- 未开启：引导开启 -->
            <div v-if="mfaPhase === 'off'" class="mfa-body">
              <p class="mfa-text">
                为账户增加一道动态验证码（TOTP）防线：即使密码泄露，攻击者没有你手机上的验证码也无法登录。
                支持 Google Authenticator、Microsoft Authenticator、1Password 等验证器。
              </p>
              <p v-if="mfaError" class="pwd-error" role="alert">{{ mfaError }}</p>
              <button class="vh-btn vh-btn-aurora mfa-submit" :disabled="mfaBusy" @click="startMfaSetup">
                <span>{{ mfaBusy ? "获取中" : "开始开启" }}</span>
              </button>
            </div>

            <!-- 扫码 / 录入密钥 + 输入动态码确认 -->
            <div v-else-if="mfaPhase === 'setup'" class="mfa-body">
              <p class="mfa-text">
                用验证器 App 扫描二维码（或复制密钥手动录入），然后输入 App 显示的 6 位动态验证码完成绑定。
              </p>
              <img v-if="mfaSetup?.qr_png" class="mfa-qr" :src="mfaSetup.qr_png" alt="两步验证绑定二维码" />
              <div v-if="mfaSetup?.secret" class="mfa-secret">
                <code>{{ mfaSetup.secret }}</code>
                <button type="button" class="mfa-copy" title="复制密钥" aria-label="复制密钥" @click="copyText(mfaSetup.secret)">
                  <Copy size="14" weight="regular" />
                </button>
              </div>
              <form class="pwd-form" @submit.prevent="confirmMfaEnable">
                <div class="vh-field">
                  <label for="mfa-code">动态验证码</label>
                  <input
                    id="mfa-code"
                    v-model="mfaCode"
                    class="vh-input"
                    type="text"
                    inputmode="numeric"
                    autocomplete="one-time-code"
                    placeholder="6 位动态验证码"
                    maxlength="6"
                    required
                  />
                </div>
                <p v-if="mfaError" class="pwd-error" role="alert">{{ mfaError }}</p>
                <button class="vh-btn vh-btn-aurora mfa-submit" type="submit" :disabled="mfaBusy">
                  <span>{{ mfaBusy ? "验证中" : "确认开启" }}</span>
                </button>
              </form>
            </div>

            <!-- 启用成功：一次性恢复代码（必须确认已保存） -->
            <div v-else-if="mfaPhase === 'codes'" class="mfa-body">
              <p class="del-warn">
                两步验证已开启。请把以下<strong>恢复代码</strong>保存在安全的地方——手机丢失时它们是唯一的登录通道，
                每个代码只能使用一次，<strong>关闭本窗口后将不再显示</strong>。
              </p>
              <ul class="mfa-codes">
                <li v-for="c in mfaRecoveryCodes" :key="c"><code>{{ c }}</code></li>
              </ul>
              <button type="button" class="mfa-copy-all" @click="copyText(mfaRecoveryCodes.join('\n'))">
                <Copy size="14" weight="regular" />
                复制全部恢复代码
              </button>
              <button class="vh-btn vh-btn-aurora mfa-submit" @click="mfaPhase = 'on'">
                <span>我已妥善保存</span>
              </button>
            </div>

            <!-- 已开启 -->
            <div v-else-if="mfaPhase === 'on'" class="mfa-body">
              <p class="mfa-text ok-text">
                两步验证已开启：登录时需要「密码 + 动态验证码」双因子，安全性已增强。
              </p>
              <button class="vh-btn vh-btn-danger mfa-submit" :disabled="mfaBusy" @click="mfaPhase = 'disabling'; mfaError = ''">
                <span>关闭两步验证</span>
              </button>
            </div>

            <!-- 关闭确认：密码 + 动态码/恢复代码 -->
            <form v-else class="pwd-form" @submit.prevent="submitMfaDisable">
              <p class="mfa-text">关闭两步验证需要「登录密码 + 动态验证码」双重确认。</p>
              <div class="vh-field">
                <label for="mfa-pwd">登录密码</label>
                <input
                  id="mfa-pwd"
                  v-model="mfaDisablePassword"
                  class="vh-input"
                  type="password"
                  autocomplete="current-password"
                  placeholder="输入当前密码"
                  required
                />
              </div>
              <div class="vh-field">
                <label for="mfa-disable-code">动态验证码</label>
                <input
                  id="mfa-disable-code"
                  v-model="mfaDisableCode"
                  class="vh-input"
                  type="text"
                  inputmode="numeric"
                  autocomplete="one-time-code"
                  placeholder="6 位验证码或恢复代码"
                  maxlength="9"
                  required
                />
              </div>
              <p v-if="mfaError" class="pwd-error" role="alert">{{ mfaError }}</p>
              <button class="vh-btn vh-btn-danger mfa-submit" type="submit" :disabled="mfaBusy">
                <span>{{ mfaBusy ? "提交中" : "确认关闭" }}</span>
              </button>
            </form>
          </section>
        </div>
      </transition>
    </teleport>
  </div>
</template>

<style scoped>
.app { min-height: 100dvh; display: flex; flex-direction: column; }

/* 路由切换时的顶部扫描光 */
.route-beam {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  z-index: calc(var(--z-nav) + 5);
  background: linear-gradient(90deg, transparent, var(--accent), var(--gold-bright), transparent);
  background-size: 40% 100%;
  background-repeat: no-repeat;
  animation: nav-beam 0.72s var(--ease-out) 1 both;
  pointer-events: none;
}
@keyframes nav-beam {
  from { background-position: -40% 0; opacity: 1; }
  to { background-position: 140% 0; opacity: 0; }
}

/* 导航：毛玻璃 blur(16px) + 低透底 + 微光边框（底色随主题切换）；
 * 页面滚动后浮起一层重投影，强化层级 */
.nav {
  position: sticky;
  top: 0;
  z-index: var(--z-nav);
  height: var(--nav-h);
  background: var(--nav-bg);
  backdrop-filter: blur(16px) saturate(1.3);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  border-bottom: 1px solid var(--line);
  transition: box-shadow 0.3s ease, border-color 0.3s ease;
}
.nav.scrolled {
  border-bottom-color: var(--line-strong);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}
html[data-theme="light"] .nav.scrolled { box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08); }
.nav-inner {
  max-width: var(--page-w);
  height: 100%;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  align-items: center;
  gap: 28px;
}

.brand { display: flex; align-items: center; gap: 9px; text-decoration: none; }
.brand:hover { text-decoration: none; }
.brand-mark {
  position: relative;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--accent-strong);
  color: #000;
  transition: transform 0.25s var(--ease-spring), box-shadow 0.25s ease;
}
.brand:hover .brand-mark {
  transform: scale(1.06);
  box-shadow: 0 0 0 1px rgba(30, 215, 96, 0.4), 0 6px 18px -6px rgba(30, 215, 96, 0.7);
}
.brand-mark :deep(svg) { width: 19px; height: 19px; position: relative; z-index: 1; }
/* 品牌外圈：常态缓慢巡游，hover 加速发光 */
.brand-ring {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1px solid rgba(60, 228, 119, 0.28);
  opacity: 0;
  transition: opacity 0.3s ease;
}
.brand:hover .brand-ring {
  opacity: 1;
  border-color: rgba(255, 181, 88, 0.55);
  animation: vh-rotate 3.2s linear infinite;
}
.brand-name { font-size: 17px; font-weight: 700; letter-spacing: -0.01em; color: var(--text-1); }

.links { display: flex; align-items: center; gap: 4px; height: 100%; }
.link {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 13px;
  border-radius: var(--r-pill);
  color: var(--text-3);
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  text-decoration: none;
  transition: color 0.16s ease, background 0.16s ease;
}
.link:hover { color: var(--text-2); background: var(--surface-2); text-decoration: none; }
.link.active { color: var(--accent); background: var(--surface-2); }
/* 选中指示器：一道会呼吸的绿琥珀短光条 */
.link.active::after {
  content: "";
  position: absolute;
  left: 50%;
  bottom: -16px;
  width: 16px;
  height: 2px;
  transform: translateX(-50%);
  border-radius: var(--r-pill);
  background: linear-gradient(90deg, var(--accent), var(--gold-bright));
  box-shadow: 0 0 8px rgba(255, 181, 88, 0.6);
  animation: nav-underline 3.4s var(--ease-in-out) infinite;
}
@keyframes nav-underline {
  0%, 100% { width: 10px; opacity: 0.75; }
  50% { width: 22px; opacity: 1; }
}

.spacer { flex: 1; }

/* 用户区（Popover 触发器） */
.user {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 4px 8px 4px 4px;
  border: 1px solid transparent;
  border-radius: var(--r-pill);
  background: transparent;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease;
}
.user:hover,
.user.on {
  background: var(--surface-2);
  border-color: var(--line);
}
.avatar {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--r-pill);
  background: var(--surface-3);
  border: 1px solid rgba(255, 164, 43, 0.45);
  color: var(--gold-bright);
  font-size: 13px;
  font-weight: 600;
  transition: box-shadow 0.25s ease;
}
.user:hover .avatar,
.user.on .avatar { box-shadow: 0 0 0 3px var(--gold-soft); }
.username { color: var(--text-2); font-size: 13px; }
.user-caret {
  color: var(--text-3);
  transition: transform 0.3s var(--ease-spring), color 0.16s ease;
}
.user-caret.flip { transform: rotate(180deg); color: var(--accent); }

/* 菜单内容 */
.menu { display: flex; flex-direction: column; gap: 6px; }
.menu-id {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 8px 8px 10px;
  border-bottom: 1px solid var(--line);
}
.menu-avatar {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--r-pill);
  background: var(--surface-3);
  border: 1px solid rgba(255, 164, 43, 0.45);
  color: var(--gold-bright);
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}
.menu-meta { display: flex; flex-direction: column; line-height: 1.35; min-width: 0; }
.menu-name { font-size: 13.5px; font-weight: 600; color: var(--text-1); }
.menu-role {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: var(--text-3);
}
.menu-role :deep(svg) { color: var(--accent); }

.menu-links { display: flex; flex-direction: column; gap: 2px; padding-top: 4px; }
.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 9px;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-2);
  font: 500 13px/1.4 var(--font-sans);
  text-align: left;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
}
.menu-item:hover { background: var(--surface); color: var(--text-1); }
.menu-item.danger {
  margin-top: 4px;
  padding-top: 9px;
  border-top: 1px solid var(--line);
  border-radius: 0 0 var(--r-sm) var(--r-sm);
}
/* 危险区第二项（退出登录）：紧跟注销账户之后，不再重复分隔线 */
.menu-item.danger.no-divider { margin-top: 0; border-top: 0; }
.menu-item.danger:hover { background: var(--danger-soft); color: var(--danger); }
.menu-item :deep(svg) { flex-shrink: 0; color: var(--text-3); }

/* ---- 修改密码弹窗 ---- */
.pwd-mask {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(10, 14, 24, 0.55);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.pwd-dialog {
  width: 100%;
  max-width: 380px;
  padding: 22px 24px 24px;
  border-radius: 18px;
  background: var(--glass-bg);
  backdrop-filter: blur(16px) saturate(1.3);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  border: 1px solid var(--glass-line);
  box-shadow: var(--shadow-3);
}
.pwd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.pwd-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-1);
}
.pwd-title :deep(svg) { color: var(--accent); }
.pwd-close {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: background var(--dur-2) ease, color var(--dur-2) ease;
}
.pwd-close:hover { background: var(--surface); color: var(--text-1); }
.pwd-form { display: flex; flex-direction: column; gap: 14px; }
.pwd-error {
  margin: 0;
  padding: 9px 12px;
  border-radius: var(--r-sm);
  background: var(--danger-soft);
  border: 1px solid rgba(243, 114, 127, 0.4);
  color: var(--danger);
  font-size: 13px;
}
.pwd-submit { height: 42px; margin-top: 4px; border: 0; }

/* ---- 注销账户弹窗 ---- */
.pwd-title.danger-title,
.pwd-title.danger-title :deep(svg) { color: var(--danger); }
.del-warn {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: var(--danger-soft);
  border: 1px solid rgba(243, 114, 127, 0.4);
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.6;
}
.del-warn strong { color: var(--danger); font-weight: 600; }
.del-submit { height: 42px; margin-top: 4px; border: 0; }

/* ---- 两步验证弹窗（TOTP，S19）---- */
.mfa-label { display: inline-flex; align-items: center; gap: 6px; }
.mfa-badge {
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: var(--accent-soft, rgba(30, 215, 96, 0.12));
  color: var(--accent);
  font-size: 10.5px;
  font-style: normal;
  font-weight: 600;
}
.mfa-dialog { max-width: 400px; }
.mfa-body { display: flex; flex-direction: column; gap: 14px; }
.mfa-text {
  margin: 0;
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.7;
}
.mfa-text.ok-text { color: var(--text-2); }
.mfa-qr {
  align-self: center;
  width: 168px;
  height: 168px;
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: #fff;
}
.mfa-secret {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px dashed var(--line);
  border-radius: var(--r-sm);
  background: var(--tint);
}
.mfa-secret code {
  font-family: var(--font-mono);
  font-size: 12.5px;
  letter-spacing: 0.04em;
  color: var(--text-1);
  word-break: break-all;
}
.mfa-copy {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: color var(--dur-1) ease, background var(--dur-1) ease;
}
.mfa-copy:hover { color: var(--accent); background: var(--surface); }
.mfa-codes {
  list-style: none;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 14px;
  margin: 0;
  padding: 10px 12px;
  border: 1px dashed var(--line);
  border-radius: var(--r-sm);
  background: var(--tint);
}
.mfa-codes li {
  font-family: var(--font-mono);
  font-size: 12.5px;
  letter-spacing: 0.05em;
  color: var(--text-1);
  text-align: center;
}
.mfa-copy-all {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-2);
  font: 500 12.5px/1 var(--font-sans);
  cursor: pointer;
  transition: color var(--dur-1) ease, border-color var(--dur-1) ease;
}
.mfa-copy-all:hover { color: var(--accent); border-color: rgba(60, 228, 119, 0.5); }
.mfa-submit { height: 42px; margin-top: 4px; border: 0; }
.pwd-fade-enter-active,
.pwd-fade-leave-active { transition: opacity 0.22s ease; }
.pwd-fade-enter-from,
.pwd-fade-leave-to { opacity: 0; }
.menu-item:hover :deep(svg) { color: var(--accent); }
.menu-item.danger:hover :deep(svg) { color: var(--danger); }

.main { flex: 1; }
.main.flush { padding: 0; }

/* 全局页脚 */
.foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 24px 18px;
  color: var(--text-3);
  font-size: 12px;
}
.foot-sep { opacity: 0.6; }
.foot-ver {
  padding: 2px 9px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line);
  background: var(--tint);
  color: var(--text-3);
  font-size: 11px;
  letter-spacing: 0.06em;
}
.foot-link {
  color: var(--text-3);
  text-decoration: none;
  transition: color 0.16s ease;
}
.foot-link:hover { color: var(--accent); text-decoration: underline; }

/* 路由过渡：位移 + 轻微缩放，页面切换更有「推进感」 */
.page-enter-active,
.page-leave-active {
  transition: opacity 0.3s var(--ease-out), transform 0.3s var(--ease-out);
}
.page-enter-from { opacity: 0; transform: translateY(14px) scale(0.995); }
.page-leave-to { opacity: 0; transform: translateY(-8px) scale(0.998); }

@media (max-width: 720px) {
  .nav-inner { padding: 0 12px; gap: 8px; }
  .brand-mark { width: 28px; height: 28px; }
  .brand-name { display: none; }
  .link { padding: 0 8px; font-size: 13.5px; }
  .link :deep(svg) { display: none; }
  .username { display: none; }
  .user { padding: 4px; }
}
</style>
