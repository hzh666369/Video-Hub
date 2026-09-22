<script setup>
import { computed } from "vue"
import { classifyPassword, TIERS } from "../utils/passwordTier"

const props = defineProps({
  password: { type: String, default: "" },
})

const tier = computed(() => {
  const level = classifyPassword(props.password)
  return TIERS[level] ?? TIERS[0]
})
</script>

<template>
  <div class="pwd-tier" role="status" :aria-label="`密码强度段位：${tier.label}`">
    <div class="tier-bar" aria-hidden="true">
      <span
        v-for="i in 7"
        :key="i"
        class="seg"
        :class="{ on: i <= tier.level }"
        :style="i <= tier.level
          ? { background: tier.color, boxShadow: `0 0 8px -2px ${tier.color}` }
          : undefined"
      ></span>
    </div>
    <span class="tier-label" :style="{ color: tier.level ? tier.color : 'var(--text-3)' }">
      {{ tier.level ? tier.label : "无段位 · 至少 8 位" }}
    </span>
  </div>
</template>

<style scoped>
.pwd-tier {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0 0;
}

/* 7 段强度条：点亮段使用段位主色并带微光 */
.tier-bar {
  display: flex;
  flex: 1;
  gap: 3px;
  min-width: 0;
}
.seg {
  flex: 1;
  height: 4px;
  border-radius: 2px;
  background: var(--tint, rgba(128, 128, 128, 0.22));
  border: 1px solid var(--line, rgba(128, 128, 128, 0.25));
  transition: background 0.25s ease, box-shadow 0.25s ease;
}

.tier-label {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
  line-height: 1;
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .seg { transition: none; }
}
</style>
