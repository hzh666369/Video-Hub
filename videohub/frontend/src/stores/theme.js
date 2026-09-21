import { defineStore } from "pinia"

const STORAGE_KEY = "vh-theme"
const META_SELECTOR = 'meta[name="theme-color"]'
const THEME_COLOR = { dark: "#121212", light: "#f5f6f7" }

function readSaved() {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === "light" || v === "dark" ? v : "dark"
  } catch {
    return "dark"
  }
}

function applyTheme(theme) {
  const root = document.documentElement
  if (theme === "light") root.setAttribute("data-theme", "light")
  else root.removeAttribute("data-theme")
  const meta = document.querySelector(META_SELECTOR)
  if (meta) meta.setAttribute("content", THEME_COLOR[theme])
}

export const useThemeStore = defineStore("theme", {
  state: () => ({ theme: readSaved() }),
  getters: {
    isLight: (s) => s.theme === "light",
  },
  actions: {
    /* 首帧由 index.html 内联脚本先行设置，这里做一次兜底同步 */
    init() {
      applyTheme(this.theme)
    },
    toggle() {
      this.theme = this.theme === "light" ? "dark" : "light"
      try {
        localStorage.setItem(STORAGE_KEY, this.theme)
      } catch {
        /* 隐私模式下持久化失败不影响当次切换 */
      }
      applyTheme(this.theme)
    },
  },
})
