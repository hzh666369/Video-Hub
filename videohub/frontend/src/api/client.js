import axios from "axios"

// timeout：后端假死时避免 30s/60s 轮询的请求无限堆积（浏览器自身 ~300s 才兜底）
const api = axios.create({ baseURL: "/api", timeout: 15000 })

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const detail = err.response?.data?.detail
    err.friendly = typeof detail === "string" ? detail : err.message || "请求失败"
    if (err.response?.status === 401 && !location.pathname.startsWith("/login")) {
      location.href = "/login"
    }
    return Promise.reject(err)
  },
)

export default api
