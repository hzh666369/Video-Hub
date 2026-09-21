"""图形验证码：Pillow 渲染 4 位字符 PNG，答案存服务端内存，一次性使用。

- 答案不落 captcha_id，防止脚本直接从响应里解码绕过；
- 单进程部署（SQLite 场景）足够，重启后已签发的验证码全部失效；
- 每个验证码校验后即销毁，过期自动清理；
- 渲染针对 OCR 做多层对抗（2026-09-18 外部安全评估"高危"项修复）：
  背景色斑抬高底噪熵 + 字符逐位旋转/错位/重叠 + 贝塞尔干扰弧线覆盖在
  字形之上 + 椒盐噪点 + 整幅正弦扭曲，不再出现"纯色背景 + 平直文字"
  的低熵样本（旧样本前 2KB 仅 23 种唯一字节值，可被 ddddocr 秒破）。
  干扰元素属视觉用途，用 random；答案本身仍只用 secrets（红线 3.2）。
"""
import io
import math
import random
import secrets
import threading
import time

from PIL import Image, ImageDraw, ImageFont

_TTL_SECONDS = 300  # 验证码 5 分钟内有效
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉 0/O、1/I 等易混淆字符
_SIZE = (160, 60)
_BG = (246, 248, 251)

_store: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()

_FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",  # Windows
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
)


_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """按字号缓存字体对象，避免每次渲染都从磁盘反复加载 TTF。"""
    if size not in _font_cache:
        for path in _FONT_CANDIDATES:
            try:
                _font_cache[size] = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        else:
            _font_cache[size] = ImageFont.load_default(size=size)
    return _font_cache[size]


def _wave_distort(img: Image.Image) -> Image.Image:
    """整幅正弦扭曲：每列独立垂直位移，打断字形笔画连通性。

    幅度刻意压在 3-5px：OCR 需要先做几何校正，而人眼仍可正常辨认。
    """
    w, h = img.size
    amp = random.uniform(3.0, 5.0)
    cycles = random.uniform(1.5, 2.5)
    phase = random.uniform(0, 2 * math.pi)
    out = Image.new("RGB", (w, h), _BG)
    for x in range(w):
        dy = int(round(amp * math.sin(2 * math.pi * cycles * x / w + phase)))
        out.paste(img.crop((x, 0, x + 1, h)), (x, dy))
    return out


def _render_png(code: str) -> bytes:
    w, h = _SIZE
    img = Image.new("RGB", _SIZE, _BG)
    draw = ImageDraw.Draw(img)

    # 背景层：柔和色斑抬高背景熵，OCR 预处理难以二值化出"干净底"
    for _ in range(7):
        cx, cy = random.randint(0, w), random.randint(0, h)
        r = random.randint(16, 40)
        shade = random.randint(222, 242)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     fill=(shade, min(255, shade + 2), min(255, shade + 6)))

    # 底层细干扰线（画在字形之下，破坏连通域分析）
    for _ in range(3):
        pts = [(random.randint(0, w), random.randint(0, h)) for _ in range(4)]
        draw.line(pts, fill=tuple(random.randint(130, 200) for _ in range(3)), width=1)

    # 逐字符绘制：随机字号/颜色/旋转/上下错位，相邻字符允许少量重叠
    cell = 56
    step = (w - 24 - cell) // max(1, len(code) - 1)
    for i, ch in enumerate(code):
        font = _load_font(random.randint(34, 42))
        color = (
            random.randint(15, 80),
            random.randint(15, 80),
            random.randint(70, 150),
        )
        glyph = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((4, 2), ch, font=font, fill=color)
        glyph = glyph.rotate(random.uniform(-30, 30), expand=False,
                             resample=Image.BICUBIC)
        img.paste(glyph, (10 + step * i + random.randint(-3, 3),
                          random.randint(2, 8)), glyph)

    # 上层贝塞尔干扰弧线（覆盖在字形之上，对 OCR 是最有效的一层）：
    # 三次贝塞尔均匀采样 25 点连成弧线，随机穿过文字主区
    for _ in range(5):
        color = tuple(random.randint(60, 170) for _ in range(3))
        p0 = (random.randint(-10, 30), random.randint(8, h - 8))
        p1 = (random.randint(20, w - 20), random.randint(-20, h + 20))
        p2 = (random.randint(20, w - 20), random.randint(-20, h + 20))
        p3 = (random.randint(w - 30, w + 10), random.randint(8, h - 8))
        pts = []
        for k in range(25):
            t = k / 24
            x = ((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0]
                 + 3 * (1 - t) * t * t * p2[0] + t ** 3 * p3[0])
            y = ((1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1]
                 + 3 * (1 - t) * t * t * p2[1] + t ** 3 * p3[1])
            pts.append((x, y))
        draw.line(pts, fill=color, width=2)

    # 椒盐噪点 + 短划痕
    for _ in range(280):
        x, y = random.randint(0, w - 1), random.randint(0, h - 1)
        draw.point((x, y), fill=tuple(random.randint(90, 220) for _ in range(3)))
    for _ in range(50):
        x, y = random.randint(0, w - 4), random.randint(0, h - 1)
        dx, dy = random.randint(2, 4), random.choice((-1, 0, 1))
        draw.line((x, y, x + dx, y + dy),
                  fill=tuple(random.randint(90, 200) for _ in range(3)), width=1)

    img = _wave_distort(img)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def new_captcha() -> tuple[str, bytes]:
    """签发验证码，返回 (captcha_id, png_bytes)。"""
    # 答案属于安全敏感值，用加密随机；干扰线/噪点等视觉元素仍可用 random
    code = "".join(secrets.choice(_ALPHABET) for _ in range(4))
    token = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        for key, (_, expiry) in list(_store.items()):
            if expiry < now:
                del _store[key]
        _store[token] = (code, now + _TTL_SECONDS)
    return token, _render_png(code)


def verify_captcha(captcha_id: str, text: str) -> bool:
    """校验并销毁验证码（一次性），过期或答案不符均返回 False。"""
    with _lock:
        entry = _store.pop(captcha_id or "", None)
    if entry is None:
        return False
    code, expiry = entry
    if expiry < time.time():
        return False
    return bool(text) and text.strip().upper() == code


def _reset() -> None:
    """仅供测试：清空全部已签发验证码。"""
    with _lock:
        _store.clear()
