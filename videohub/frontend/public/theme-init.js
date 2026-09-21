/* 首帧前应用已保存的主题，避免浅色用户看到暗色闪烁（FOUC）。
 * 外置为同源静态文件以兼容 CSP script-src 'self'（禁止内联脚本，S17） */
(function () {
  try {
    if (localStorage.getItem("vh-theme") === "light") {
      document.documentElement.setAttribute("data-theme", "light")
    }
  } catch (e) {}
})()
