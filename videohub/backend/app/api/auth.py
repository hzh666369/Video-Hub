import base64
import hmac
import random
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, password_fingerprint
from app.database import get_db
from app.models import AccessLog, Record, RecoveryCode, User
from app.services.access_log import record_access
from app.services.auth import MAX_PASSWORD_BYTES, hash_password, verify_password
from app.services.captcha import new_captcha, verify_captcha
from app.services.client_ip import get_client_ip, rate_limit_key
from app.services.password_tier import MIN_VALID_LEVEL, classify_password
from app.services import totp as totp_svc
from app.services.ratelimit import (
    account_delete_limiter,
    captcha_limiter,
    login_fail_limiter,
    login_lock_limiter,
    login_user_limiter,
    password_verify_limiter,
    register_attempt_limiter,
    register_success_limiter,
    totp_limiter,
    username_check_limiter,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 用户名：3-32 位，字母开头，仅字母 / 数字 / 下划线
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,31}$")
PASSWORD_MIN_LEN = 8

# 登录失败随机延迟（2026-09-18 安全评估加固建议）：错密码/错动态码统一加抖动延迟，
# 拖慢批量尝试节拍；正常用户单次失败无感。延迟量是时长而非安全值，用 random 合规；
# 测试环境由 conftest 置零避免拖慢套件
LOGIN_FAIL_DELAY = (0.15, 0.45)


def _throttle_failed_login() -> None:
    time.sleep(random.uniform(*LOGIN_FAIL_DELAY))


class LoginIn(BaseModel):
    username: str
    password: str
    # 账号维度被锁时用于解锁的人机验证（S6）。仅在 login_user_limiter 命中后才会被要求，
    # 平时可缺省——不要求旧客户端同步升级，契约保持向后兼容。
    captcha_id: str | None = None
    captcha_text: str | None = None
    # TOTP 两步验证（S19）：仅已开启两步验证的账户在密码通过后被要求，
    # 可缺省——契约向后兼容
    totp_code: str | None = None


class RegisterIn(BaseModel):
    username: str
    password: str
    captcha_id: str
    captcha_text: str


class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str


class AccountDeleteIn(BaseModel):
    password: str


class TotpEnableIn(BaseModel):
    code: str


class TotpDisableIn(BaseModel):
    password: str
    code: str


def _user_dict(user: User) -> dict:
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin,
            "onboarding_completed": bool(user.onboarding_completed),
            "permissions": sorted(user.permission_set),
            "totp_enabled": bool(user.totp_enabled)}


def _consume_recovery_code(db: Session, user: User, code: str) -> bool:
    """匹配并消费一枚未用过的恢复代码（命中即置 used，常数时间比较）。

    格式先做硬校验（XXXX-XXXX），不匹配直接返回，避免无谓的逐行比较。
    """
    text = (code or "").strip()
    if len(text) != 9 or text[4] != "-":
        return False
    digest = totp_svc.recovery_hash(text)
    rows = db.scalars(select(RecoveryCode).where(
        RecoveryCode.user_id == user.id, RecoveryCode.used.is_(False))).all()
    for row in rows:
        if hmac.compare_digest(row.code_hash, digest):
            row.used = True
            db.commit()
            return True
    return False


def _count_login_failure(bucket: str, user_key: str) -> None:
    """登录失败统一记账：IP 维 + 账号维第二级（验证码闸门）+ 第三级（临时锁定）。"""
    login_fail_limiter.allow(f"login:{bucket}")
    login_user_limiter.allow(user_key)
    login_lock_limiter.allow(user_key)


def _client_ip(request: Request) -> str:
    return get_client_ip(request)


def _check_password_strength(password: str) -> None:
    """密码段位校验：最低有效段位为青铜（详见 docs/密码段位说明书.md）。"""
    # bcrypt 上限 72 字节：超限会在 hash/verify 处抛 ValueError 变 500，先在入口拒掉
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise HTTPException(status_code=400, detail=f"密码最长 {MAX_PASSWORD_BYTES} 字节")
    level = classify_password(password)
    if level < MIN_VALID_LEVEL:
        raise HTTPException(status_code=400, detail=f"密码至少 {PASSWORD_MIN_LEN} 位")


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    # 限流桶经 rate_limit_key 收敛（IPv6 → /64，S16）：防旋转接口标识符重置计数；
    # 日志仍记完整 IP
    bucket = rate_limit_key(request)
    # 只统计失败次数：先查后记，成功登录永不计数，避免共享出口 IP 的正常用户被误伤
    retry = login_fail_limiter.check(f"login:{bucket}")
    if retry:
        raise HTTPException(status_code=429, detail=f"失败次数过多，请 {int(retry) + 1} 秒后再试")
    user = db.scalar(select(User).where(func.lower(User.username) == body.username.lower()))
    # 账号维度第二道限流（2026-09-15 审计 M-2）：IP 维管不住多 /64 或代理池对单一
    # 账号的分布式爆破，这里跨 IP 汇总失败数兜底；阈值 20 高于 IP 维的 10，正常用户
    # 极少连续失败 20 次。只对已注册用户名计数
    if user is not None:
        user_key = f"login-user:{user.username.lower()}"
        # 账号维度第三级（2026-09-18 安全评估"未见账户锁定"修复）：失败 50 次/10min
        # → 临时锁定该账户，锁定期间验证码也不放行（先于第二级判定）。解锁通道 =
        # 等待窗口滑出；阈值 50 意味着攻击者必须先逐次通过已加固的验证码（第 20 次
        # 起）再连错 50 次密码，才能维持锁定——"免费锁死任意账号"的 DoS 不成立
        locked = login_lock_limiter.check(user_key)
        if locked:
            raise HTTPException(
                status_code=429,
                detail=f"该账户失败次数过多，已临时锁定，请 {int(locked) + 1} 秒后再试",
                headers={"Retry-After": str(int(locked) + 1)},
            )
        retry = login_user_limiter.check(user_key)
        if retry:
            # 命中账号维锁定时**不再一律硬拒**：硬拒意味着任意第三方只要凑够 20 次失败，
            # 就能让受害者在整段窗口内连正确密码都用不了——2 个 IP 出口（或一个 IPv6 /48）
            # 即可持续锁死 admin 账号，这是 M-2 引入的定向账号锁死 DoS。
            # 改为要求人机验证（S6）后才放行到密码校验：
            #   · 攻击者仍必须逐次过验证码，IP 维 10 次/10min 照旧生效，爆破成本不降；
            #   · 持有正确密码的本人总能进来，锁死 DoS 被消除；
            #   · bcrypt 开销被转移到「验证码通过」之后，CPU 放大攻击依旧被挡住。
            if not verify_captcha(body.captcha_id or "", body.captcha_text or ""):
                # 措辞区分「客户端还没带验证码」与「带了但码错/过期/复用」：两者返回
                # 同一个 429 + 同一枚标记（前端行为一致，也不泄露任何信息），但用户
                # 能看懂自己卡在哪一步。判定依据只是"请求里有没有带码"，不涉及服务端状态
                detail = ("验证码错误或已过期，请重新输入"
                          if (body.captcha_id or body.captcha_text)
                          else "该账号失败次数过多，请完成人机验证后重试")
                raise HTTPException(
                    status_code=429,
                    detail=detail,
                    headers={"X-Videohub-Captcha": "required"},
                )
    # 区分"未注册/密码错误"是维护者批准的例外（用户名存在性本就经
    # username-available 端点公开，增量风险≈0）；两种失败仍同样计入限流
    if user is None:
        login_fail_limiter.allow(f"login:{bucket}")
        _throttle_failed_login()
        raise HTTPException(status_code=401, detail="该用户名未注册")
    if not verify_password(body.password, user.password_hash):
        _count_login_failure(bucket, user_key)
        _throttle_failed_login()
        raise HTTPException(status_code=401, detail="密码错误")
    # ---- 第二因子（S19）：已开启 TOTP 的账户，密码通过后还须动态码/恢复代码 ----
    if user.totp_enabled:
        code = (body.totp_code or "").strip()
        step = totp_svc.verify(user.totp_secret or "", code,
                               last_step=user.totp_last_step) if code else None
        used_recovery = _consume_recovery_code(db, user, code) if (step is None and code) else False
        if step is None and not used_recovery:
            # 动态码失败与密码失败同口径记账（三级限流）+ 同样的随机延迟，
            # 否则拿到密码的攻击者可以绕开限流专门爆破 6 位动态码
            _count_login_failure(bucket, user_key)
            _throttle_failed_login()
            raise HTTPException(
                status_code=401,
                detail="请输入验证器中的动态验证码" if not code else "动态验证码错误",
                headers={"X-Videohub-Totp": "required"},
            )
        if step is not None and step > user.totp_last_step:
            # 单调推进已消费时间步：同一验证码在下一请求中重放会被拒
            user.totp_last_step = step
            db.commit()
    request.session["user_id"] = user.id
    request.session["pw_pv"] = password_fingerprint(user.password_hash)
    record_access(db, user, "login", ip=_client_ip(request))
    return _user_dict(user)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_dict(user)


@router.get("/captcha")
def captcha(request: Request):
    # 无需登录的渲染接口（Pillow 画图吃 CPU）：不设限会被公网刷爆；
    # 桶键经 rate_limit_key 收敛（IPv6 → /64，S16）
    retry = captcha_limiter.allow(f"captcha:{rate_limit_key(request)}")
    if retry:
        raise HTTPException(status_code=429, detail="获取验证码过于频繁，请稍后再试")
    captcha_id, png = new_captcha()
    return {
        "captcha_id": captcha_id,
        "image": "data:image/png;base64," + base64.b64encode(png).decode(),
    }


@router.get("/username-available")
def username_available(username: str, request: Request, db: Session = Depends(get_db)):
    """注册前的用户名查重：格式非法或已被占用都返回 available=False。"""
    # 限流必须按真实访客 IP 分桶：cloudflared 隧道下 request.client.host 是
    # 内网地址，全站会共享同一个桶（一人刷接口，全站 429）；
    # IPv6 再经 rate_limit_key 收敛到 /64，防旋转接口标识符绕过（S16）
    retry = username_check_limiter.allow(f"check:{rate_limit_key(request)}")
    if retry:
        raise HTTPException(status_code=429, detail="查询过于频繁，请稍后再试")
    username = username.strip()
    if not USERNAME_RE.match(username):
        return {"available": False}
    exists = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    return {"available": exists is None}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    # 限流桶键经 rate_limit_key 收敛（IPv6 → /64，S16）；record_access 仍记完整 IP
    bucket = rate_limit_key(request)

    # 第一道闸门：限制接口调用频率，防验证码爆破
    retry = register_attempt_limiter.allow(f"attempt:{bucket}")
    if retry:
        raise HTTPException(status_code=429, detail=f"操作过于频繁，请 {int(retry) + 1} 秒后再试")

    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="用户名需为 3-32 位，字母开头，仅含字母、数字、下划线")
    _check_password_strength(body.password)
    if not verify_captcha(body.captcha_id, body.captcha_text):
        raise HTTPException(status_code=400, detail="验证码错误或已过期，请重新输入")

    # 第二道闸门：验证码通过后才计数，限制成功注册频率与总量
    retry = register_success_limiter.allow(f"success:{bucket}")
    if retry:
        minutes = int(retry // 60) + 1
        raise HTTPException(status_code=429, detail=f"注册过于频繁，请约 {minutes} 分钟后再试")

    # 预检查（大小写不敏感）+ 数据库唯一约束兜底并发
    exists = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if exists:
        raise HTTPException(status_code=409, detail="该用户名已被注册")
    user = User(username=username, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该用户名已被注册") from None

    # 注册成功即视为登录
    request.session["user_id"] = user.id
    request.session["pw_pv"] = password_fingerprint(user.password_hash)
    record_access(db, user, "register", ip=_client_ip(request))
    return _user_dict(user)


@router.post("/password")
def change_password(body: PasswordChangeIn, request: Request,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    # 改密是登录态下唯一的密码核验闸门：会话被盗后可在线爆破原密码（破坏性操作，
    # 对齐 account_delete_limiter 口径——按用户分桶、只统计失败次数，成功不计数）
    retry = password_verify_limiter.check(f"pw:{user.id}")
    if retry:
        raise HTTPException(status_code=429, detail=f"尝试次数过多，请 {int(retry) + 1} 秒后再试")
    if not verify_password(body.old_password, user.password_hash):
        password_verify_limiter.allow(f"pw:{user.id}")
        raise HTTPException(status_code=400, detail="原密码错误")
    _check_password_strength(body.new_password)
    if body.old_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    # 改密后全端下线（含当前设备）：直接清空会话，前端引导用新密码重新登录。
    # 其他设备的旧会话本就随 pw_pv 指纹失配失效，这里连本人会话一起清掉，口径更严格
    request.session.clear()
    return {"ok": True}


@router.delete("/account")
def delete_account(body: AccountDeleteIn, request: Request,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """用户自助注销：密码二次确认后删除账户及其名下全部解析记录。"""
    # 管理员不可自助注销：防止最后一个管理员把自己删掉导致系统失管（与 L-2 管理员保护同源）
    if user.is_admin:
        raise HTTPException(status_code=403, detail="管理员账户不支持自助注销，请联系维护者处理")
    # 破坏性操作限流：按用户分桶，只统计密码错误次数（对齐 login 的 check/allow 口径，成功不计数）
    retry = account_delete_limiter.check(f"del:{user.id}")
    if retry:
        raise HTTPException(status_code=429, detail=f"尝试次数过多，请 {int(retry) + 1} 秒后再试")
    if not verify_password(body.password, user.password_hash):
        account_delete_limiter.allow(f"del:{user.id}")
        raise HTTPException(status_code=400, detail="密码错误")
    # 访问日志靠用户名快照保留可读性，删除用户前解除 user_id 外键引用（对齐管理员删除用户的写法）
    db.execute(sa_update(AccessLog).where(AccessLog.user_id == user.id).values(user_id=None))
    # 名下解析记录整体清除；captions 经 FK ON DELETE CASCADE 联动清理（SQLite foreign_keys=ON 已开）
    db.execute(sa_delete(Record).where(Record.user_id == user.id))
    db.delete(user)
    db.commit()
    # 注销即登出：清空当前会话，前端跳转登录页
    request.session.clear()
    return {"ok": True}


@router.post("/onboarding/complete")
def complete_onboarding(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """标记当前用户已完成新手引导（注册后首次登录时前端自动调用）。"""
    if not user.onboarding_completed:
        user.onboarding_completed = True
        db.commit()
    return {"ok": True}


# ---- TOTP 两步验证管理（S19）：全部需登录，共用 totp_limiter 按用户限流 ----


@router.post("/totp/setup")
def totp_setup(request: Request, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """生成待确认的 TOTP 密钥：返回扫码二维码（data URI PNG）与手动录入串。

    secret 写库待 enable 确认；此接口可重复调用覆盖旧密钥（未 enable 前）。
    每次调用都写 users 行且下发可入号密钥，故挂限流。
    """
    retry = totp_limiter.allow(f"totp:{user.id}")
    if retry:
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="两步验证已开启，如需更换请先关闭")
    user.totp_secret = totp_svc.generate_secret()
    user.totp_enabled = False
    user.totp_last_step = 0
    db.commit()
    uri = totp_svc.provisioning_uri(user.totp_secret, user.username)
    return {"secret": user.totp_secret, "otpauth_uri": uri,
            "qr_png": totp_svc.qr_png_data_uri(uri)}


@router.post("/totp/enable")
def totp_enable(body: TotpEnableIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """确认开启：验证一枚动态码通过后置位，并签发一次性恢复代码（明文仅此一次回传）。"""
    retry = totp_limiter.allow(f"totp:{user.id}")
    if retry:
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="两步验证已开启")
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="请先获取密钥（setup）")
    step = totp_svc.verify(user.totp_secret, body.code, last_step=user.totp_last_step)
    if step is None:
        raise HTTPException(status_code=400, detail="动态验证码错误，请校准时间后重试")
    user.totp_enabled = True
    user.totp_last_step = step
    codes = totp_svc.generate_recovery_codes()
    db.execute(sa_delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    for code in codes:
        db.add(RecoveryCode(user_id=user.id, code_hash=totp_svc.recovery_hash(code)))
    db.commit()
    return {"recovery_codes": codes}


@router.post("/totp/disable")
def totp_disable(body: TotpDisableIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """关闭两步验证：密码 + 动态码（或恢复代码）双重确认后清除密钥与恢复代码。"""
    retry = totp_limiter.allow(f"totp:{user.id}")
    if retry:
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="两步验证未开启")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="密码错误")
    step = totp_svc.verify(user.totp_secret or "", body.code, last_step=user.totp_last_step)
    if step is None and not _consume_recovery_code(db, user, body.code):
        raise HTTPException(status_code=400, detail="动态验证码错误")
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_last_step = 0
    db.execute(sa_delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.commit()
    return {"ok": True}
