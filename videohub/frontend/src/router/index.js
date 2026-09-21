import { createRouter, createWebHistory } from "vue-router"
import { useAuthStore } from "../stores/auth"

const routes = [
  { path: "/login", component: () => import("../views/Login.vue") },
  { path: "/", component: () => import("../views/ParseHome.vue"), meta: { requiresAuth: true } },
  { path: "/player/:id", component: () => import("../views/Player.vue"), meta: { requiresAuth: true } },
  { path: "/library", component: () => import("../views/Library.vue"), meta: { requiresAuth: true } },
  { path: "/settings", component: () => import("../views/Settings.vue"),
    meta: { requiresAuth: true, anyPerm: ["routes", "users", "access"] } },
  { path: "/dashboard", component: () => import("../views/Dashboard.vue"),
    meta: { requiresAuth: true, perm: "dashboard" } },
  { path: "/disclaimer", component: () => import("../views/Disclaimer.vue") },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) await auth.fetchMe()
  if (to.meta.requiresAuth && !auth.user) return "/login"
  // 功能点授权:perm 需单码,anyPerm 任一即可(管理员在 can() 内恒真)
  if (to.meta.perm && !auth.can(to.meta.perm)) return "/"
  if (to.meta.anyPerm && !to.meta.anyPerm.some((p) => auth.can(p))) return "/"
  if (to.path === "/login" && auth.user) return "/"
  return true
})

export default router
