<script setup>
import { PhCheckCircle as CheckCircle, PhWarningCircle as WarningCircle, PhInfo as Info } from "@phosphor-icons/vue"
import { dismiss, toasts } from "../stores/toast"

const ICONS = { success: CheckCircle, error: WarningCircle, info: Info }
</script>

<template>
  <!-- 全局操作反馈通知：顶部居中弹出，自动消失，成功 / 失败 / 信息三态 -->
  <teleport to="body">
    <div class="toast-region" aria-live="polite" aria-label="操作通知">
      <transition-group name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="toast"
          :class="`is-${t.type}`"
          role="status"
          @click="dismiss(t.id)"
        >
          <component :is="ICONS[t.type]" size="17" weight="fill" class="toast-icon" />
          <span class="toast-msg">{{ t.message }}</span>
          <button class="toast-close" aria-label="关闭通知" @click.stop="dismiss(t.id)">
            ×
          </button>
        </div>
      </transition-group>
    </div>
  </teleport>
</template>

<style scoped>
.toast-region {
  position: fixed;
  top: calc(var(--nav-h, 60px) + 12px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 120; /* 高于修改密码弹窗（z-index 90） */
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: min(92vw, 440px);
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 11px 14px;
  border-radius: var(--r-md, 12px);
  background: var(--glass-bg);
  backdrop-filter: blur(16px) saturate(1.3);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  border: 1px solid var(--glass-line);
  box-shadow: var(--shadow-3, 0 12px 32px rgba(0, 0, 0, 0.35));
  color: var(--text-1);
  font-size: 13.5px;
  line-height: 1.45;
  cursor: pointer;
}

.toast-icon { flex-shrink: 0; }
.toast.is-success .toast-icon { color: var(--ok, #1ed760); }
.toast.is-success { border-color: rgba(30, 215, 96, 0.35); }
.toast.is-error .toast-icon { color: var(--danger, #f3727f); }
.toast.is-error { border-color: rgba(243, 114, 127, 0.4); }
.toast.is-info .toast-icon { color: var(--accent, #1ed760); }

.toast-msg { flex: 1; min-width: 0; overflow-wrap: anywhere; }

.toast-close {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: var(--r-sm, 8px);
  background: transparent;
  color: var(--text-3);
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}
.toast-close:hover { color: var(--text-1); background: var(--surface-2, rgba(255, 255, 255, 0.08)); }

/* 进出场：从顶部滑入，离场轻微上浮淡出 */
.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.28s var(--ease-out, ease), transform 0.28s var(--ease-out, ease);
}
.toast-enter-from { opacity: 0; transform: translateY(-14px) scale(0.97); }
.toast-leave-to { opacity: 0; transform: translateY(-8px) scale(0.98); }
/* 列表重排（上层消失时下层平滑上移） */
.toast-move { transition: transform 0.28s var(--ease-out, ease); }

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active,
  .toast-move { transition: none; }
}
</style>
