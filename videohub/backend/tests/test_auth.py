from app.models import User


def _fresh_captcha():
    """签发一张验证码并回读答案（仅在测试内使用内部表，生产路径不外泄答案）。"""
    from app.services import captcha as captcha_svc

    captcha_id, _png = captcha_svc.new_captcha()
    return captcha_id, captcha_svc._store[captcha_id][0]


def _lock_account(client, username="admin", ip_prefix="203.0.120."):
    """用 20 个不同 IP 打满账号维度失败额度（每请求换 IP，让 IP 维限流不参与）。"""
    for i in range(20):
        r = client.post("/api/auth/login", json={"username": username, "password": "bad"},
                        headers={"CF-Connecting-IP": f"{ip_prefix}{i}"})
        assert r.status_code == 401


def test_seed_admin_created_on_startup(client, db):
    admin = db.query(User).filter(User.username == "admin").first()
    assert admin is not None and admin.is_admin is True


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    assert r.status_code == 401
    assert r.json()["detail"] == "密码错误"


def test_login_unregistered_username(client):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "bad"})
    assert r.status_code == 401
    assert r.json()["detail"] == "该用户名未注册"


def test_me_requires_login(client):
    assert client.get("/api/auth/me").status_code == 401


def test_login_me_logout_flow(auth_client):
    r = auth_client.get("/api/auth/me")
    assert r.status_code == 200 and r.json()["username"] == "admin" and r.json()["is_admin"] is True
    assert auth_client.post("/api/auth/logout").status_code == 200
    assert auth_client.get("/api/auth/me").status_code == 401


def test_login_fail_rate_limited(client):
    # 连续 10 次失败后触发限流（H1），且带正确密码也会被拦
    for _ in range(10):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 429 and "失败次数过多" in r.json()["detail"]


def test_login_success_not_counted(client):
    # 成功登录不消耗失败额度：9 次失败 + 1 次成功后，仍有 1 次尝试机会
    for _ in range(9):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 429


# ---------- 账号维度防爆破（2026-09-15 审计 M-2） ----------

def test_login_brute_force_blocked_per_account_across_ips(client):
    # 攻击场景回归：分布式爆破单一账号——每请求换 IP 让 IP 维限流失效，
    # 账号维度跨 IP 汇总失败数后仍拦得住（第 21 次带正确密码也拒绝）
    for i in range(20):
        r = client.post("/api/auth/login",
                        json={"username": "admin", "password": "bad"},
                        headers={"CF-Connecting-IP": f"203.0.114.{i}"})
        assert r.status_code == 401
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "admin123"},
                    headers={"CF-Connecting-IP": "203.0.115.99"})
    assert r.status_code == 429
    assert "账号" in r.json()["detail"]


def test_login_user_dim_does_not_affect_other_accounts(client):
    # 正例：admin 触发账号维度限流，不影响其他用户名的正常判定
    for i in range(20):
        client.post("/api/auth/login", json={"username": "admin", "password": "bad"},
                    headers={"CF-Connecting-IP": f"203.0.116.{i}"})
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"},
                    headers={"CF-Connecting-IP": "203.0.117.1"})
    assert r.status_code == 401  # 未注册的常规 401，而非共享账号桶的 429


# ---------- 账号锁定的离场通道：人机验证解锁（2026-09-15 审查 M-2-F1） ----------
#
# 原实现命中账号维限流后一律硬拒 → 任意第三方凑够 20 次失败即可让受害者连正确
# 密码都用不了（2 个 IP 出口持续锁死 admin）。现改为要求人机验证（S6）后才放行
# 到密码校验：攻击者仍需逐次过码且 IP 维照旧生效，爆破成本不降；本人能进来。

def test_account_lock_without_captcha_is_rejected_with_marker(client):
    # 反例：不带验证码 → 429，且响应头显式告知前端"需人机验证"（用于就地展开验证码）
    _lock_account(client)
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"},
                    headers={"CF-Connecting-IP": "203.0.121.99"})
    assert r.status_code == 429
    assert r.headers["x-videohub-captcha"] == "required"


def test_account_lock_captcha_unlocks_owner_with_correct_password(client):
    # 正例：本人过码 + 正确密码 → 200（锁定不再把本人挡在门外）
    _lock_account(client)
    captcha_id, code = _fresh_captcha()
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "admin123",
                          "captcha_id": captcha_id, "captcha_text": code},
                    headers={"CF-Connecting-IP": "203.0.122.1"})
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_account_lock_captcha_does_not_bypass_password(client):
    # 反例：过码但密码错 → 仍是 401，验证码不是绕过密码的通道
    _lock_account(client)
    captcha_id, code = _fresh_captcha()
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "bad",
                          "captcha_id": captcha_id, "captcha_text": code},
                    headers={"CF-Connecting-IP": "203.0.123.1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "密码错误"


def test_account_lock_captcha_is_one_time(client):
    # 反例：同一张验证码二次使用无效（S6 一次性），仍被锁在门外
    _lock_account(client)
    captcha_id, code = _fresh_captcha()
    payload = {"username": "admin", "password": "bad",
               "captcha_id": captcha_id, "captcha_text": code}
    assert client.post("/api/auth/login", json=payload,
                       headers={"CF-Connecting-IP": "203.0.124.1"}).status_code == 401
    r = client.post("/api/auth/login", json=payload,
                    headers={"CF-Connecting-IP": "203.0.125.1"})
    assert r.status_code == 429
    assert r.headers["x-videohub-captcha"] == "required"


# ---------- 用户名比较口径统一（2026-09-15 审查 F3） ----------

def test_login_username_is_case_insensitive(client, auth_client):
    # 用户名唯一性本就是大小写不敏感（NOCASE 唯一索引），登录查找必须同口径，
    # 否则用户输错大小写会误报"该用户名未注册"
    assert auth_client.post("/api/users",
                            json={"username": "CaseUser", "password": "pw123456"}).status_code == 200
    assert client.post("/api/auth/login",
                       json={"username": "caseuser", "password": "pw123456"}).status_code == 200
    assert client.post("/api/auth/login",
                       json={"username": "CASEUSER", "password": "pw123456"}).status_code == 200

