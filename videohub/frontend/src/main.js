import { createPinia } from "pinia"
import { createApp } from "vue"
import App from "./App.vue"
import router from "./router"
import { useThemeStore } from "./stores/theme"
import { vReveal, vGlow } from "./directives/vfx"
import "./styles/tokens.css"

const pinia = createPinia()
const theme = useThemeStore(pinia)
theme.init()

const app = createApp(App)
app.use(pinia).use(router)
/* 全站动效指令：v-reveal 滚动入场 / v-glow 卡片聚光 */
app.directive("reveal", vReveal)
app.directive("glow", vGlow)
app.mount("#app")
