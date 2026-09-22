/* 全局操作反馈通知：任何「点了按钮不知道成没成功」的地方都应调用这里
 * 用法：
 *   import { toast } from "../stores/toast"
 *   toast.success("设置已保存")
 *   toast.error(e.friendly || "操作失败")
 */
import { reactive } from "vue"

let seq = 0
export const toasts = reactive([])

function push(type, message, duration) {
  const id = ++seq
  toasts.push({ id, type, message })
  /* 最多同时展示 4 条，超出的挤掉最旧的 */
  if (toasts.length > 4) toasts.shift()
  setTimeout(() => dismiss(id), duration)
}

export function dismiss(id) {
  const i = toasts.findIndex((t) => t.id === id)
  if (i >= 0) toasts.splice(i, 1)
}

export const toast = {
  success: (msg, duration = 3000) => push("success", msg, duration),
  error: (msg, duration = 4200) => push("error", msg, duration),
  info: (msg, duration = 3000) => push("info", msg, duration),
}
