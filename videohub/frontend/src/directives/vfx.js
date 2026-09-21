/*
 * vfx.js · 全站动效指令集（GSAP 驱动）
 *
 * v-reveal —— 滚动入场：元素进入视口时「上浮 + 模糊聚焦」依次显现。
 *   用法：v-reveal 或 v-reveal="{ children: true, stagger: 0.08 }"
 *   children 模式会把入场拆给直接子元素，形成逐卡片交错入场。
 *
 * v-glow —— 卡片聚光：鼠标在卡片上移动时，一圈主题色径向光晕
 *   （内部辉光 + 边框亮段）跟随鼠标。只负责把坐标写进 CSS 变量
 *   --gx/--gy，渲染完全交给 tokens.css 里的 .vh-glow 伪元素，零逐帧 JS。
 *
 * 降级：prefers-reduced-motion 下两个指令都不生效，内容直接可见。
 */
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

gsap.registerPlugin(ScrollTrigger)

function prefersReduced() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

/* ---------------- v-reveal：滚动入场 ---------------- */
export const vReveal = {
  mounted(el, binding) {
    if (prefersReduced()) return

    const opts = binding.value || {}
    const targets = opts.children ? Array.from(el.children) : [el]
    if (!targets.length) return

    const tween = gsap.fromTo(
      targets,
      { autoAlpha: 0, y: 28, filter: "blur(10px)" },
      {
        autoAlpha: 1,
        y: 0,
        filter: "blur(0px)",
        duration: 0.75,
        ease: "power3.out",
        stagger: opts.children ? (opts.stagger ?? 0.08) : 0,
        delay: opts.delay || 0,
        /* 入场完成后清掉内联样式：否则 transform/opacity/filter 被永久钉住，
           卡片的 CSS hover 浮起与焦点切换动画都会失效 */
        onComplete: () => gsap.set(targets, { clearProps: "all" }),
        scrollTrigger: {
          trigger: el,
          start: opts.start || "top 84%",
          once: true,
        },
      },
    )

    el.__vhReveal = () => {
      if (tween.scrollTrigger) tween.scrollTrigger.kill()
      tween.kill()
      gsap.set(targets, { clearProps: "all" })
    }
  },
  unmounted(el) {
    el.__vhReveal && el.__vhReveal()
  },
}

/* ---------------- v-glow：卡片聚光 ---------------- */
export const vGlow = {
  mounted(el) {
    /* 触屏没有 hover 语义，聚光无意义，直接跳过 */
    if (!window.matchMedia("(hover: hover)").matches) return

    el.classList.add("vh-glow")
    const move = (e) => {
      const r = el.getBoundingClientRect()
      el.style.setProperty("--gx", `${e.clientX - r.left}px`)
      el.style.setProperty("--gy", `${e.clientY - r.top}px`)
    }
    el.__vhGlowMove = move
    el.addEventListener("pointermove", move, { passive: true })
  },
  unmounted(el) {
    if (el.__vhGlowMove) el.removeEventListener("pointermove", el.__vhGlowMove)
    el.classList.remove("vh-glow")
    el.style.removeProperty("--gx")
    el.style.removeProperty("--gy")
  },
}
