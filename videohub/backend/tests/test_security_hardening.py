"""2026-09-18 外部安全评估修复项回归：验证码抗 OCR、安全响应头、账户临时锁定。

评估报告（对线上部署域名的被动侦察）三个发现对应本文件：
- 高危：验证码复杂度极低（前 2KB 仅 23 种唯一字节值，ddddocr/tesseract 可破）；
- 中危：缺 CSP / HSTS / X-Frame-Options / Permissions-Policy / COOP / CORP；
- 中危：未见账户锁定机制（现有第二级是"过码放行"，本批补第三级时间锁）。
"""
import base64
import re
from pathlib import Path

from app.services import captcha as captcha_svc


# ---------- 验证码抗 OCR（高危项） ----------

def test_captcha_png_has_high_entropy_signature(client):
    """反例回归：旧实现"纯色背景 + 平直文字"压缩后前 2KB 仅 23 种唯一字节值，
    OCR 预处理可直接二值化。加固后（背景色斑 + 弧线 + 噪点 + 正弦扭曲）
    压缩流必须是高熵的，且 PNG 尺寸显著大于纯色底版本。"""
    r = client.get("/api/auth/captcha")
    assert r.status_code == 200
    payload = r.json()
    assert payload["captcha_id"]

    image_b64 = payload["image"].split(",", 1)[1]
    png = base64.b64decode(image_b64)
    # PNG 魔数 + 尺寸下限：噪点/扭曲使压缩体积明显大于纯色底的 ~5.4KB 低熵样本
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 2500
    # 前 2KB 唯一字节值：旧样本 23 种，加固后压缩流高熵（经验值 > 100，阈值留余量取 60）
    assert len(set(png[:2048])) > 60


def test_captcha_verify_roundtrip_still_works():
    """正例：加固只动渲染层，签发/一次性校验契约不变（答案仍可正常比对）。"""
    captcha_id, code = (lambda p: (p[0], captcha_svc._store[p[0]][0]))(
        captcha_svc.new_captcha())
    assert captcha_svc.verify_captcha(captcha_id, code.lower()) is True
    # 一次性：第二校验必失败
    assert captcha_svc.verify_captcha(captcha_id, code) is False


# ---------- 安全响应头（中危项，S17 扩展） ----------

def test_security_headers_present_on_api(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy", "")
    # CSP 关键指令：禁外域脚本/连接、禁被嵌、禁 object
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    # HSTS：评估实测 Cloudflare 边缘未下发，改由应用层补发
    assert r.headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains"
    assert r.headers.get("x-frame-options") == "DENY"
    pp = r.headers.get("permissions-policy", "")
    assert "camera=()" in pp and "geolocation=()" in pp
    # 全屏/自动播放**不得**进 Permissions-Policy：VIP 播放器是跨域 iframe，
    # 头策略限 (self) 会掐掉 iframe 内的全屏与自动播放
    assert "fullscreen" not in pp and "autoplay" not in pp
    assert r.headers.get("cross-origin-opener-policy") == "same-origin"
    assert r.headers.get("cross-origin-resource-policy") == "same-origin"
    # 原有基础头不回退
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_frontend_index_has_no_inline_script():
    """CSP script-src 'self' 禁内联脚本：index.html 里的主题预载脚本必须外置为
    同源文件（public/theme-init.js），任何新增内联 <script> 都会让 CSP 打挂 SPA。"""
    index = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(
        encoding="utf-8")
    inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", index)
    assert not inline_scripts, f"index.html 存在无 src 的内联 script: {inline_scripts}"
    assert 'src="/theme-init.js"' in index
    assert (Path(__file__).resolve().parents[2] / "frontend" / "public"
            / "theme-init.js").exists()


# ---------- 账户临时锁定第三级（中危项） ----------
#
# 攻击场景：分布式爆破单一账号。每请求换 IP 让 IP 维限流失效；第 20 次失败起
# 第二级要求人机验证——攻击者逐次过码继续错密码，到 50 次触发第三级时间锁。

def _fresh_captcha():
    captcha_id, _png = captcha_svc.new_captcha()
    return captcha_id, captcha_svc._store[captcha_id][0]


def _brute_force_with_captchas(client, username: str, count: int, ip_prefix: str):
    """模拟"能过验证码的攻击者"：每请求换 IP + 带正确验证码 + 错密码。"""
    for i in range(count):
        captcha_id, code = _fresh_captcha()
        r = client.post(
            "/api/auth/login",
            json={"username": username, "password": "bad",
                  "captcha_id": captcha_id, "captcha_text": code},
            headers={"CF-Connecting-IP": f"{ip_prefix}{i}"})
        assert r.status_code == 401, f"第 {i + 1} 次应仍为密码错误: {r.text}"


def test_temporal_lockout_triggers_at_50_failures(client):
    from app.services.ratelimit import login_lock_limiter

    # 前 20 次无需验证码；20 次后走"过码"通道继续失败
    for i in range(20):
        r = client.post("/api/auth/login",
                        json={"username": "admin", "password": "bad"},
                        headers={"CF-Connecting-IP": f"203.0.130.{i}"})
        assert r.status_code == 401
    _brute_force_with_captchas(client, "admin", 30, "203.0.131.")

    # 第 51 次（继续错密码）→ 临时锁定，带 Retry-After
    captcha_id, code = _fresh_captcha()
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "bad",
              "captcha_id": captcha_id, "captcha_text": code},
        headers={"CF-Connecting-IP": "203.0.132.7"})
    assert r.status_code == 429
    assert "临时锁定" in r.json()["detail"]
    assert "retry-after" in r.headers


def test_temporal_lockout_blocks_even_correct_password_with_captcha(client):
    """反例：锁定期间，本人（正确密码 + 过码）也被拒——时间锁优先于验证码闸门。
    这是有意行为：解锁通道 = 等待窗口滑出（见 docs/SECURITY.md 红线 3.2 论证）。"""
    from app.services.ratelimit import login_lock_limiter

    _brute_force_with_captchas(client, "admin", 50, "203.0.133.")
    captcha_id, code = _fresh_captcha()
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123",
              "captcha_id": captcha_id, "captcha_text": code},
        headers={"CF-Connecting-IP": "203.0.134.9"})
    assert r.status_code == 429
    assert "临时锁定" in r.json()["detail"]

    # 正例：窗口滑出（reset 模拟时间流逝）后，本人过码 + 正确密码立即可进
    login_lock_limiter.reset()
    captcha_id, code = _fresh_captcha()
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123",
              "captcha_id": captcha_id, "captcha_text": code},
        headers={"CF-Connecting-IP": "203.0.135.9"})
    assert r.status_code == 200


def test_temporal_lockout_is_per_account(client):
    """正例：admin 被临时锁定不影响其他账户正常登录（桶键按用户名隔离）。"""
    _brute_force_with_captchas(client, "admin", 50, "203.0.136.")
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"},
                    headers={"CF-Connecting-IP": "203.0.137.1"})
    assert r.status_code == 401  # 常规"未注册"401，而非 admin 桶的 429 锁定
