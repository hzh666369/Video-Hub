import { defineStore } from "pinia"
import api from "../api/client"

/* ---- 在线心跳：登录态下每 30s 上报一次，驱动看板「在线人数」实时口径 ----
 * 静默失败：401 由 client.js 拦截器统一跳登录页（页面卸载定时器随之销毁）；
 * 其余网络错误下个周期自动重试，不打扰用户。切回前台立即补打一次，
 * 让看板尽快恢复「在线」。后台标签页浏览器会把定时器节流到 ~60s，
 * 后端在线窗口 120s，仍有 2 倍余量。
 *
 * 限流口径按「标签页」计：每个标签页各跑一份定时器，后端 heartbeat_limiter
 * 已按多标签留出余量；单标签页内再用 MIN_BEAT_GAP_MS 节流，避免快速来回切
 * 标签页时 visibilitychange 连续攒出一串重复上报。 */
const HEARTBEAT_MS = 30_000
const MIN_BEAT_GAP_MS = 15_000
let hbTimer = null
let lastBeatAt = 0

function beatOnce() {
  const now = Date.now()
  if (now - lastBeatAt < MIN_BEAT_GAP_MS) return
  lastBeatAt = now
  api.post("/heartbeat").catch(() => {})
}

function onVisible() {
  if (document.visibilityState === "visible") beatOnce()
}

function startHeartbeat() {
  stopHeartbeat()
  lastBeatAt = 0 // 新登录会话可能是另一个账号，立即那一拍不吃节流
  beatOnce()
  hbTimer = setInterval(beatOnce, HEARTBEAT_MS)
  document.addEventListener("visibilitychange", onVisible)
}

function stopHeartbeat() {
  if (hbTimer) { clearInterval(hbTimer); hbTimer = null }
  document.removeEventListener("visibilitychange", onVisible)
}

export const useAuthStore = defineStore("auth", {
  state: () => ({ user: null, loaded: false }),
  getters: {
    // 功能点授权判定:管理员恒真;普通用户看后端下发的 permissions 数组
    can: (state) => (code) => {
      if (!state.user) return false
      return state.user.is_admin || (state.user.permissions || []).includes(code)
    },
    // 设置页任一区块权限(路由守卫与导航入口共用)
    canAnySettings: (state) => {
      if (!state.user) return false
      if (state.user.is_admin) return true
      const perms = state.user.permissions || []
      return ["routes", "users", "access"].some((c) => perms.includes(c))
    },
  },
  actions: {
    async fetchMe() {
      try {
        const { data } = await api.get("/auth/me")
        this.user = data
        startHeartbeat()
      } catch {
        this.user = null
        stopHeartbeat()
      } finally {
        this.loaded = true
      }
    },
    async login(username, password, captcha, totpCode) {
      const { data } = await api.post("/auth/login", {
        username,
        password,
        // 账号维度被锁时后端要求人机验证解锁；平时传 null（契约向后兼容）
        captcha_id: captcha?.id || null,
        captcha_text: captcha?.text || null,
        // TOTP 两步验证（S19）：仅已开启的账户在密码通过后被要求；平时传 null
        totp_code: totpCode?.trim() || null,
      })
      this.user = data
      startHeartbeat()
    },
    async register(username, password, captchaId, captchaText) {
      const { data } = await api.post("/auth/register", {
        username,
        password,
        captcha_id: captchaId,
        captcha_text: captchaText,
      })
      this.user = data
      startHeartbeat()
    },
    async changePassword(oldPassword, newPassword) {
      await api.post("/auth/password", {
        old_password: oldPassword,
        new_password: newPassword,
      })
      // 后端改密即 session.clear()（全端下线，含本人）：本地必须立刻停心跳，
      // 否则定时器会继续每 30s 打一次必然 401 的请求，而拦截器对已在 /login
      // 的页面不再跳转，这个空转循环会一直持续到用户重新登录为止
      stopHeartbeat()
    },
    async deleteAccount(password) {
      await api.delete("/auth/account", { data: { password } })
      stopHeartbeat()
    },
    async completeOnboarding() {
      try {
        await api.post("/auth/onboarding/complete")
      } catch { /* 标记失败不影响本次引导关闭，下次登录会再提示 */ }
      if (this.user) this.user.onboarding_completed = true
    },
    async logout() {
      await api.post("/auth/logout")
      this.user = null
      stopHeartbeat()
    },
  },
})
