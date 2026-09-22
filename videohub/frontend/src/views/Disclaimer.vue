<script setup>
import { onMounted, ref } from "vue"
import {
  PhScroll as Scroll,
  PhArrowLeft as ArrowLeft,
  PhWarningCircle as WarningCircle,
  PhBookOpen as BookOpen,
  PhShieldCheck as ShieldCheck,
  PhXCircle as XCircle,
  PhCopyright as Copyright,
  PhProhibit as Prohibit,
  PhDatabase as Database,
  PhCheckCircle as CheckCircle,
  PhInfo as Info,
  PhLifebuoy as Lifebuoy,
  PhCheck as Check,
  PhX as X,
} from "@phosphor-icons/vue"
import VhAurora from "../components/VhAurora.vue"

/**
 * 免责声明 · 内容增强版
 * 要点速览卡片 → 允许/禁止对照 → 完整条款 → 反馈入口 → 已阅读确认（localStorage 持久化）
 */
const SUMMARIES = [
  { icon: BookOpen, title: "学习研究", desc: "仅限个人学习与技术研究场景", tone: "ok" },
  { icon: Prohibit, title: "严禁商用", desc: "售卖、引流、二次分发均被禁止", tone: "danger" },
  { icon: Copyright, title: "版权归原方", desc: "所有内容版权归原平台 / 版权方", tone: "gold" },
  { icon: Database, title: "不存内容", desc: "平台不存储、不上传任何视频", tone: "mute" },
]

const ALLOW = [
  "观看与学习自己有权限访问的内容",
  "研究音视频解析、网络请求等技术实现",
  "在个人设备上回放自己的解析记录",
  "向管理员反馈线路失效或侵权问题",
]

const DENY = [
  "将解析服务用于任何商业目的",
  "传播、转售、二次分发解析结果",
  "批量抓取、绕过原平台访问控制",
  "下载、传播受版权保护的内容",
]

/* ---- 已阅读确认：状态持久化在本机 localStorage ---- */
const ACK_KEY = "vh-disclaimer-ack"
const ackedAt = ref("")
onMounted(() => {
  try {
    ackedAt.value = localStorage.getItem(ACK_KEY) || ""
  } catch {
    /* 隐私模式下读取失败视为未确认 */
  }
})

function acknowledge() {
  const now = new Date()
  const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
    now.getDate(),
  ).padStart(2, "0")}`
  ackedAt.value = stamp
  try {
    localStorage.setItem(ACK_KEY, stamp)
  } catch {
    /* 写入失败不影响当次展示 */
  }
}
</script>

<template>
  <div class="vh-page disclaimer">
    <div class="vh-aurora-wrap" aria-hidden="true"><VhAurora variant="hero" :intensity="0.5" /></div>

    <header class="vh-head">
      <h1 class="vh-head-title">
        <Scroll size="22" weight="regular" />
        免责声明
      </h1>
      <p class="vh-head-sub">最后更新：2026-09-04 · 请在使用前仔细阅读</p>
    </header>

    <!-- ================= 要点速览 ================= -->
    <div class="sum-grid vh-stagger">
      <div v-for="s in SUMMARIES" :key="s.title" class="sum" :class="`tone-${s.tone}`">
        <span class="sum-icon"><component :is="s.icon" size="18" weight="regular" /></span>
        <span class="sum-title">{{ s.title }}</span>
        <span class="sum-desc">{{ s.desc }}</span>
      </div>
    </div>

    <section class="card">
      <div class="banner" role="note">
        <WarningCircle size="18" weight="fill" />
        <p>
          本平台（VideoHub，下称"本平台"）<strong>仅供个人学习和研究使用</strong>，
          <strong>切勿用于任何商业用途</strong>。下载、注册或使用本平台即表示您已阅读并同意本声明的全部内容。
        </p>
      </div>

      <!-- ================= 允许 / 禁止对照 ================= -->
      <div class="dd">
        <div class="dd-col allow">
          <header class="dd-head">
            <span class="dd-icon ok"><CheckCircle size="15" weight="fill" /></span>
            <span class="dd-title">允许这样做</span>
          </header>
          <ul>
            <li v-for="a in ALLOW" :key="a">
              <Check size="12" weight="bold" class="li-ok" />
              {{ a }}
            </li>
          </ul>
        </div>
        <div class="dd-col deny">
          <header class="dd-head">
            <span class="dd-icon bad"><XCircle size="15" weight="fill" /></span>
            <span class="dd-title">请不要这样做</span>
          </header>
          <ul>
            <li v-for="d in DENY" :key="d">
              <X size="12" weight="bold" class="li-bad" />
              {{ d }}
            </li>
          </ul>
        </div>
      </div>

      <article class="clause">
        <h2><BookOpen size="17" weight="regular" /> 一、平台性质与用途限制</h2>
        <p>1. 本平台是一个个人开发的技术学习与研究工具，用于学习音视频解析、网络请求、Web 开发等技术知识，所有功能仅面向<strong>个人非商业性学习与研究</strong>场景。</p>
        <p>2. 您承诺不将本平台用于任何商业目的，包括但不限于：售卖解析服务、嵌入商业产品、广告变现、收费引流、二次分发给第三方用于营利等。</p>
        <p>3. 您承诺不利用本平台从事任何违反法律法规、侵害他人合法权益的活动，包括但不限于侵犯知识产权、传播违法违规内容等。</p>
      </article>

      <article class="clause">
        <h2><Copyright size="17" weight="regular" /> 二、内容版权归属</h2>
        <p>1. 本平台本身不存储、不上传、不制作、不传播任何视频、音频、图文等内容；平台展示与解析的内容均来源于第三方公开网站。</p>
        <p>2. 所有视频、音频、图片、字幕等内容的版权归<strong>原权利方（原平台 / 版权方）所有</strong>，本平台与相关内容不存在任何隶属或合作关系。</p>
        <p>3. 您通过本平台接触到的内容，仅可作为个人学习与研究之用，不得下载、复制、传播、篡改或用于其他任何用途。</p>
      </article>

      <article class="clause">
        <h2><XCircle size="17" weight="regular" /> 三、责任限制</h2>
        <p>1. 本平台按"现状"提供，不对解析结果的可用性、完整性、准确性作任何明示或默示的保证；第三方线路与内容随时可能变更或失效。</p>
        <p>2. 对于因使用或无法使用本平台而产生的任何直接或间接损失（包括但不限于数据丢失、账号封禁、法律纠纷），本平台不承担责任。</p>
        <p>3. 若本平台的内容或服务侵犯了您的合法权益，请及时联系管理员，我们将在核实后第一时间停止相关解析与展示。</p>
      </article>

      <article class="clause">
        <h2><ShieldCheck size="17" weight="regular" /> 四、账号与违规处理</h2>
        <p>1. 对于违反本声明的账号，管理员有权视情节采取提醒、禁用或删除等措施。</p>
        <p>2. 因违规使用引发的账号封禁、法律纠纷等后果，由使用者自行承担。</p>
        <p>3. 平台保留在发现违规行为时立即停止相关解析与展示、并保留相关证据的权利。</p>
      </article>

      <article class="clause">
        <h2><Info size="17" weight="regular" /> 五、其他</h2>
        <p>1. 本声明未尽事宜，参照国家有关法律法规执行。若本声明与法律法规相抵触，以法律法规为准。</p>
        <p>2. 本平台保留随时更新本声明的权利，更新后的声明将在本页面公布，继续使用即视为接受更新后的声明。</p>
        <p>3. 本声明的解释权归本平台开发者所有。</p>
      </article>

      <p class="agree-line">—— 如您不同意上述条款，请立即停止使用并注销账号；如您继续使用，即视为已阅读并同意本声明的全部内容。——</p>

      <!-- ================= 反馈入口 ================= -->
      <p class="feedback">
        <Lifebuoy size="15" weight="regular" />
        发现线路失效、内容侵权或功能异常？请联系平台管理员处理，我们会在核实后尽快跟进。
      </p>
    </section>

    <!-- ================= 已阅读确认 ================= -->
    <div class="ack-row">
      <button v-if="!ackedAt" class="vh-btn vh-btn-primary" type="button" @click="acknowledge">
        <CheckCircle size="15" weight="fill" />
        我已阅读并同意以上内容
      </button>
      <span v-else class="ack-chip vh-scale-in">
        <CheckCircle size="15" weight="fill" />
        已确认阅读 · {{ ackedAt }}
      </span>
      <span class="ack-hint">确认结果仅保存在本机浏览器</span>
    </div>

    <router-link to="/" class="vh-btn vh-btn-ghost back">
      <ArrowLeft size="14" weight="bold" />
      返回首页
    </router-link>
  </div>
</template>

<script>
export default { name: "Disclaimer" }
</script>

<style scoped>
.disclaimer { max-width: 820px; position: relative; }

.vh-aurora-wrap {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.vh-head-title {
  display: inline-flex;
  align-items: center;
  gap: 9px;
}
.vh-head-title :deep(svg) { color: var(--accent); }

/* ================= 要点速览卡片 ================= */
.sum-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.sum {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border-radius: var(--r-md);
  background: var(--surface);
  border: 1px solid var(--line);
  transition: transform 0.25s var(--ease-out), box-shadow 0.25s ease, border-color 0.2s ease,
    background 0.2s ease;
}
.sum:hover {
  transform: translateY(-3px);
  background: var(--surface-2);
  border-color: var(--line-strong);
  box-shadow: var(--shadow-2);
}
.sum-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  transition: transform var(--dur-3) var(--ease-spring);
}
.sum:hover .sum-icon { transform: scale(1.12) rotate(-6deg); }
.sum.tone-ok .sum-icon { background: var(--ok-soft); color: var(--ok); }
.sum.tone-danger .sum-icon { background: var(--danger-soft); color: var(--danger); }
.sum.tone-gold .sum-icon { background: var(--gold-soft); color: var(--gold-bright); }
.sum.tone-mute .sum-icon { background: var(--tint); color: var(--text-2); }
.sum-title { font-size: 14px; font-weight: 700; color: var(--text-1); }
.sum-desc { font-size: 12.5px; line-height: 1.55; color: var(--text-3); }

.card {
  position: relative;
  padding: 26px 30px 24px;
  border-radius: 16px;
  background: var(--glass-bg);
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
  border: 1px solid var(--glass-line);
  box-shadow: var(--shadow-2);
}

.banner {
  display: flex;
  gap: 10px;
  padding: 14px 16px;
  border-radius: var(--r-sm);
  background: var(--gold-soft);
  border: 1px solid rgba(255, 164, 43, 0.35);
  margin-bottom: 22px;
}
.banner :deep(svg) { color: var(--gold-bright); flex-shrink: 0; margin-top: 2px; }
.banner p { margin: 0; color: var(--text-1); font-size: 13.5px; line-height: 1.7; }
.banner strong { color: var(--gold-bright); }

/* ================= 允许 / 禁止对照 ================= */
.dd {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.dd-col {
  padding: 16px 18px;
  border-radius: var(--r-md);
  background: var(--bg-raise);
  border: 1px solid var(--line);
  transition: border-color 0.2s ease, box-shadow 0.25s ease, transform 0.25s var(--ease-out);
}
.dd-col:hover { transform: translateY(-2px); box-shadow: var(--shadow-1); }
.dd-col.allow:hover { border-color: rgba(30, 215, 96, 0.35); }
.dd-col.deny:hover { border-color: rgba(243, 114, 127, 0.35); }
.dd-head { display: flex; align-items: center; gap: 9px; margin-bottom: 10px; }
.dd-icon {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
}
.dd-icon.ok { background: var(--ok-soft); color: var(--ok); }
.dd-icon.bad { background: var(--danger-soft); color: var(--danger); }
.dd-title { font-size: 14px; font-weight: 700; color: var(--text-1); }
.dd-col ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.dd-col li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-2);
}
.dd-col li + li { border-top: 1px solid var(--line); }
.li-ok { color: var(--ok); flex-shrink: 0; margin-top: 4px; }
.li-bad { color: var(--danger); flex-shrink: 0; margin-top: 4px; }

.clause { margin-bottom: 20px; }
.clause h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-1);
}
.clause h2 :deep(svg) { color: var(--accent); }
.clause p {
  margin: 0 0 8px;
  padding-left: 12px;
  color: var(--text-2);
  font-size: 13.5px;
  line-height: 1.8;
  border-left: 2px solid var(--line);
  transition: border-color 0.2s ease;
}
.clause:hover p { border-left-color: rgba(30, 215, 96, 0.45); }
.clause strong { color: var(--text-1); }

.agree-line {
  margin: 26px 0 0;
  padding-top: 18px;
  border-top: 1px dashed var(--line);
  text-align: center;
  color: var(--text-3);
  font-size: 12.5px;
  line-height: 1.7;
}

/* ================= 反馈入口 ================= */
.feedback {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 20px 0 0;
  padding: 12px 16px;
  border-radius: var(--r-sm);
  background: var(--accent-soft);
  border: 1px solid rgba(30, 215, 96, 0.28);
  color: var(--text-2);
  font-size: 13px;
  line-height: 1.6;
}
.feedback :deep(svg) { color: var(--accent); flex-shrink: 0; }

/* ================= 已阅读确认 ================= */
.ack-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 18px;
}
.ack-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 15px;
  border-radius: var(--r-pill);
  background: var(--ok-soft);
  border: 1px solid rgba(30, 215, 96, 0.35);
  color: var(--ok);
  font-size: 13px;
  font-weight: 600;
}
.ack-hint { color: var(--text-3); font-size: 12px; }

.back { margin-top: 18px; height: 38px; }

@media (max-width: 560px) {
  .card { padding: 20px 18px; }
  .dd { grid-template-columns: 1fr; }
}
</style>
