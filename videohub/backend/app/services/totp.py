"""TOTP 两步验证（RFC 6238）：纯标准库实现 + 一次性恢复代码（S19）。

- 时间步 30s、SHA1、6 位 —— 三大认证器 App（Google/Microsoft Authenticator、
  1Password 等）的默认兼容组合；
- secret 与恢复代码一律用 secrets 生成（红线 3.2），比较走 hmac.compare_digest；
- 校验窗口 ±1 个时间步（容忍客户端时钟漂移），已用过的 step 单调拒绝重放
  （users.totp_last_step）；
- 恢复代码格式 XXXX-XXXX（去混淆字符表），库里只存加盐 SHA-256，明文仅在
  启用成功时回传一次；
- QR 码用 qrcode 库（复用已装的 Pillow）渲染成 data URI PNG，前端 <img> 直接
  展示，不经过 v-html（红线 3.5）。
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1  # 允许 ±1 个时间步
RECOVERY_COUNT = 10
# 恢复代码字符表：去掉 0/O、1/I/L 等易混淆字符
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_RECOVERY_PREFIX = "vh-recovery-v1:"


def generate_secret() -> str:
    """生成 160 位熵的 base32 密钥（RFC 4226 推荐长度）。"""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _pad_b32(secret: str) -> str:
    return secret + "=" * ((8 - len(secret) % 8) % 8)


def code_at(secret: str, step_index: int) -> str:
    """按时间步序号推导 6 位 HOTP 值（RFC 4226），供校验与测试使用。"""
    key = base64.b32decode(_pad_b32(secret), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step_index), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return f"{number:0{DIGITS}d}"


def verify(secret: str, code: str, *, last_step: int = 0,
           now: int | None = None) -> int | None:
    """校验 6 位动态码。

    通过则返回命中的时间步序号（调用方需把它单调写回 totp_last_step 防重放），
    失败返回 None。格式非法（非数字/长度不对）直接失败，不进入比较。
    """
    if not secret or not isinstance(code, str):
        return None
    code = code.strip()
    if len(code) != DIGITS or not code.isdigit():
        return None
    ts = int(time.time()) if now is None else now
    current = ts // STEP_SECONDS
    # 顺序：先精确命中当前步，再容忍前后各 1 步的时钟漂移
    for delta in (0, -DRIFT_STEPS, DRIFT_STEPS):
        step = current + delta
        if step <= last_step:
            continue  # 已消费过的验证码一律拒绝（重放防护）
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, username: str, issuer: str = "VideoHub") -> str:
    """生成 otpauth:// 协议串，认证器 App 扫码或手动录入均可用。"""
    return (f"otpauth://totp/{quote(issuer)}:{quote(username)}"
            f"?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}")


def generate_recovery_codes(count: int = RECOVERY_COUNT) -> list[str]:
    """生成一次性恢复代码（XXXX-XXXX）；明文只回传一次，库里只存哈希。"""
    codes = []
    for _ in range(count):
        left = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))
        right = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))
        codes.append(f"{left}-{right}")
    return codes


def recovery_hash(code: str) -> str:
    """恢复代码 → 加盐 SHA-256（代码本身 32^8 熵，无需慢哈希）。"""
    return hashlib.sha256(
        (_RECOVERY_PREFIX + (code or "").strip().upper()).encode("utf-8")
    ).hexdigest()


def qr_png_data_uri(payload: str) -> str:
    """把 otpauth 串渲染成二维码 PNG 的 data URI（前端 <img :src> 直用）。"""
    import io

    import qrcode

    image = qrcode.make(payload, box_size=8, border=2)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
