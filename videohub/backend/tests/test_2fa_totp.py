"""TOTP 两步验证（S19）攻击场景回归。

覆盖：未登录不可管理、启用流程（错码拒/对码过）、登录缺码/错码拒 + 标记头、
验证码一次性（重放拒）、恢复代码单次有效、关闭需密码+动态码双确认、
管理端点限流。
"""
import time

from app.services import totp as totp_svc


def _current_code(secret: str) -> str:
    return totp_svc.code_at(secret, int(time.time()) // totp_svc.STEP_SECONDS)


def _next_code(secret: str) -> str:
    """下一时间步的码：verify 容忍 +1 漂移，无需真实等待 30s。"""
    return totp_svc.code_at(secret, int(time.time()) // totp_svc.STEP_SECONDS + 1)


def _login(client, password="admin123", totp_code=None, ip="203.0.140.1"):
    body = {"username": "admin", "password": password}
    if totp_code is not None:
        body["totp_code"] = totp_code
    return client.post("/api/auth/login", json=body,
                       headers={"CF-Connecting-IP": ip})


def _enable_totp(auth_client):
    """走完整启用流程，返回 (secret, recovery_codes)。"""
    r = auth_client.post("/api/auth/totp/setup")
    assert r.status_code == 200
    data = r.json()
    assert data["secret"] and data["otpauth_uri"].startswith("otpauth://totp/")
    assert data["qr_png"].startswith("data:image/png;base64,")
    r = auth_client.post("/api/auth/totp/enable", json={"code": _current_code(data["secret"])})
    assert r.status_code == 200
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10
    return data["secret"], codes


# ---------- 管理端点鉴权与限流 ----------

def test_totp_setup_requires_login(client):
    # 反例：未登录 → 401，不给任何密钥材料
    assert client.post("/api/auth/totp/setup").status_code == 401


def test_totp_setup_rate_limited(auth_client):
    # 反例：同一用户每分钟最多 10 次管理调用（setup 下发可入号密钥，防脚本刷）
    for _ in range(10):
        assert auth_client.post("/api/auth/totp/setup").status_code == 200
    r = auth_client.post("/api/auth/totp/setup")
    assert r.status_code == 429


# ---------- 启用流程 ----------

def test_totp_enable_with_wrong_code_rejected(auth_client):
    # 反例：动态码错 → 不置位、不签发恢复代码
    r = auth_client.post("/api/auth/totp/setup")
    assert r.status_code == 200
    r = auth_client.post("/api/auth/totp/enable", json={"code": "314159"})
    assert r.status_code == 400
    me = auth_client.get("/api/auth/me").json()
    assert me["totp_enabled"] is False


def test_totp_full_flow_enable_then_login(auth_client, client):
    secret, codes = _enable_totp(auth_client)

    # 状态随账户下发（前端菜单徽标数据源）
    me = auth_client.get("/api/auth/me").json()
    assert me["totp_enabled"] is True

    # 注销后：缺动态码 → 401 + 标记头（前端就地展开二步输入）
    auth_client.post("/api/auth/logout")
    r = _login(client)
    assert r.status_code == 401
    assert r.headers["x-videohub-totp"] == "required"

    # 错码 → 401
    r = _login(client, totp_code="000001")
    assert r.status_code == 401

    # 对码（下一时间步，容忍 +1 漂移）→ 200
    r = _login(client, totp_code=_next_code(secret))
    assert r.status_code == 200


def test_totp_code_is_not_replayable(auth_client, client):
    # 反例：同一枚动态码二次使用无效（totp_last_step 单调推进，防重放）。
    # 注：启用流程已消费"当前步"的码，首登用下一时间步的码（±1 漂移容忍）
    secret, _codes = _enable_totp(auth_client)
    auth_client.post("/api/auth/logout")

    code = _next_code(secret)
    assert _login(client, totp_code=code, ip="203.0.141.1").status_code == 200
    auth_client.post("/api/auth/logout")
    r = _login(client, totp_code=code, ip="203.0.141.2")
    assert r.status_code == 401


def test_recovery_code_single_use_and_fallback(auth_client, client):
    # 恢复代码：可作为动态码替代登录，但每枚只用一次
    _secret, codes = _enable_totp(auth_client)
    auth_client.post("/api/auth/logout")

    assert _login(client, totp_code=codes[0], ip="203.0.142.1").status_code == 200
    auth_client.post("/api/auth/logout")
    # 同一枚复用 → 拒；格式伪装成 6 位数字 → 拒
    assert _login(client, totp_code=codes[0], ip="203.0.142.2").status_code == 401
    assert _login(client, totp_code=codes[1].replace("-", "")[:6],
                  ip="203.0.142.3").status_code == 401


# ---------- 关闭流程 ----------

def test_totp_disable_requires_password_and_code(auth_client, client):
    secret, codes = _enable_totp(auth_client)

    # 反例：密码错 → 拒（会话被盗也不能凭一枚动态码关掉第二因子）
    r = auth_client.post("/api/auth/totp/disable",
                         json={"password": "wrong-pw", "code": _current_code(secret)})
    assert r.status_code == 400

    # 正例：密码 + 动态码 → 关闭成功，登录回到单因子
    r = auth_client.post("/api/auth/totp/disable",
                         json={"password": "admin123", "code": _next_code(secret)})
    assert r.status_code == 200
    assert auth_client.get("/api/auth/me").json()["totp_enabled"] is False

    auth_client.post("/api/auth/logout")
    assert _login(client, ip="203.0.143.1").status_code == 200


def test_totp_disable_accepts_recovery_code(auth_client, client):
    # 正例：设备丢失场景——用恢复代码替代动态码完成关闭（自救通道）
    _secret, codes = _enable_totp(auth_client)
    r = auth_client.post("/api/auth/totp/disable",
                         json={"password": "admin123", "code": codes[2]})
    assert r.status_code == 200
    auth_client.post("/api/auth/logout")
    assert _login(client, ip="203.0.144.1").status_code == 200
