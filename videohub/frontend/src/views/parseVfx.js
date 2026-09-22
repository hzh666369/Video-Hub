/*
 * parseVfx.js · 解析页专属动效（GSAP + ScrollTrigger + SplitText）
 *
 * 「高级感来自克制」——本页只保留两类动效：
 *
 *   1. 滚动入场：区块标题 SplitText 逐字翻起、卡片组交错上浮（无 3D 翻牌、无模糊）；
 *   2. 悬浮点缀：平台卡品牌图标弹性弹跳、FAQ 图标点亮。
 *
 * 已移除（历史上存在、刻意收敛）：波浪 dock、幽灵水印数字漂移、区块头
 * 横向视差、进度线生长、能力卡聚光倾角、磁吸横移——同时运行的动效系统
 * 过多会导致视觉无焦点，整页只保留一处舞台感即可。
 *
 * 全部装进 gsap.matchMedia：prefers-reduced-motion 下整组跳过（内容直接可见），
 * 触屏设备跳过悬浮部分；组件卸载时 mm.revert() 统一回收动画、监听与内联样式。
 */
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { SplitText } from "gsap/SplitText"

gsap.registerPlugin(ScrollTrigger, SplitText)

export function initParseVfx(root) {
  if (!root) return { destroy() {}, refresh() {} }

  const mm = gsap.matchMedia()

  mm.add(
    {
      motionOK: "(prefers-reduced-motion: no-preference)",
      fine: "(hover: hover) and (pointer: fine)",
    },
    (ctx) => {
      const { motionOK, fine } = ctx.conditions
      if (!motionOK) return

      const q = gsap.utils.selector(root)
      const cleanups = []
      const listen = (el, type, fn, opts) => {
        el.addEventListener(type, fn, opts)
        cleanups.push(() => el.removeEventListener(type, fn))
      }

      /* ============ 1. 滚动入场编排 ============ */
      q(".section").forEach((section) => {
        const head = section.querySelector(".sec-head")
        const grid = section.querySelector(".platforms, .faq")
        const foot = section.querySelector(".faq-foot")

        const tl = gsap.timeline({
          defaults: { ease: "power3.out" },
          scrollTrigger: { trigger: section, start: "top 82%", once: true },
        })

        const eyebrow = head && head.querySelector(".sec-eyebrow")
        const title = head && head.querySelector(".sec-title")
        const desc = head && head.querySelector(".sec-desc")

        if (eyebrow) tl.from(eyebrow, { autoAlpha: 0, y: -8, duration: 0.4 }, 0)
        if (title) {
          const split = new SplitText(title, { type: "chars" })
          tl.from(
            split.chars,
            {
              autoAlpha: 0,
              y: 22,
              duration: 0.55,
              stagger: 0.028,
              ease: "back.out(1.6)",
            },
            0.05,
          )
        }
        if (desc) tl.from(desc, { autoAlpha: 0, y: 10, duration: 0.45 }, 0.2)

        /* 卡片组：交错上浮；结束后清内联样式，把舞台让给悬浮动效 */
        if (grid && grid.children.length) {
          tl.from(
            grid.children,
            {
              autoAlpha: 0,
              y: 36,
              duration: 0.7,
              stagger: 0.08,
              clearProps: "all",
            },
            0.15,
          )
        }
        if (foot) tl.from(foot, { autoAlpha: 0, y: 12, duration: 0.45 }, 0.35)
      })

      /* ============ 2. 悬浮点缀（仅精确指针设备） ============ */
      if (!fine) return () => cleanups.forEach((fn) => fn())

      /* --- 平台卡：品牌图标弹性弹跳（相邻卡方向交替），保留唯一一处舞台感 --- */
      q(".pf").forEach((card, i) => {
        const svg = card.querySelector(".pf-icon svg")
        const enter = () =>
          svg &&
          gsap.to(svg, {
            scale: 1.12,
            rotation: i % 2 ? -5 : 5,
            duration: 0.55,
            ease: "elastic.out(1, 0.5)",
            overwrite: true,
          })
        const leave = () =>
          svg &&
          gsap.to(svg, { scale: 1, rotation: 0, duration: 0.4, ease: "power3.out", overwrite: true })
        listen(card, "pointerenter", enter)
        listen(card, "pointerleave", leave)
      })

      /* --- FAQ：问号图标点亮旋转 --- */
      q(".faq .vhx").forEach((card) => {
        const icon = card.querySelector(".fq-icon svg")
        const enter = () =>
          icon &&
          gsap.to(icon, { rotation: -10, scale: 1.12, duration: 0.4, ease: "back.out(2)", overwrite: true })
        const leave = () =>
          icon &&
          gsap.to(icon, { rotation: 0, scale: 1, duration: 0.35, ease: "power3.out", overwrite: true })
        listen(card, "pointerenter", enter)
        listen(card, "pointerleave", leave)
      })

      return () => cleanups.forEach((fn) => fn())
    },
    root,
  )

  return {
    destroy() {
      mm.revert()
    },
    refresh() {
      ScrollTrigger.refresh()
    },
  }
}
