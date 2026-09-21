"""注册 / 验证码 / 限流 / 修改密码 的接口测试。"""
import pytest

from app.models import User
from app.services import captcha as captcha_svc
from app.services.ratelimit import register_attempt_limiter, register_success_limiter


@pytest.fixture(autouse=True)
def _clean_guard_state():
    captcha_svc._reset()
    register_attempt_limiter.reset()
    register_success_limiter.reset()
    yield
    captcha_svc._reset()
    register_attempt_limiter.reset()
    register_success_limiter.reset()


def _fresh_captcha():
    captcha_id, _png = captcha_svc.new_captcha()
    code = captcha_svc._store[captcha_id][0]
    return captcha_id, code


def _register(client, username, password="password123", captcha_id=None, captcha_text=None):
    if captcha_id is None:
        captcha_id, captcha_text = _fresh_captcha()
    return client.post("/api/auth/register", json={
        "username": username, "password": password,
        "captcha_id": captcha_id, "captcha_text": captcha_text,
    })


def test_captcha_endpoint(client):
    r = client.get("/api/auth/captcha")
    assert r.status_code == 200
    data = r.json()
    assert data["captcha_id"] and data["image"].startswith("data:image/png;base64,")


def test_register_success_auto_login(client, db):
    r = _register(client, "alice")
    assert r.status_code == 201
    assert r.json()["username"] == "alice" and r.json()["is_admin"] is False
    # 注册成功即登录
    assert client.get("/api/auth/me").json()["username"] == "alice"
    assert db.query(User).filter(User.username == "alice").first() is not None


def test_register_duplicate_username(client):
    assert _register(client, "bob").status_code == 201
    register_success_limiter.reset()  # 清掉频率限制，专注测唯一性
    r = _register(client, "BOB")  # 大小写不同也算重复
    assert r.status_code == 409
    assert "已被注册" in r.json()["detail"]


def test_register_wrong_captcha(client):
    captcha_id, _ = _fresh_captcha()
    r = _register(client, "carol", captcha_id=captcha_id, captcha_text="XXXX")
    assert r.status_code == 400
    assert "验证码" in r.json()["detail"]


def test_register_captcha_one_time(client):
    captcha_id, code = _fresh_captcha()
    assert _register(client, "dave", captcha_id=captcha_id, captcha_text=code).status_code == 201
    register_success_limiter.reset()
    # 同一个验证码不能再用
    r = _register(client, "dave2", captcha_id=captcha_id, captcha_text=code)
    assert r.status_code == 400


def test_register_invalid_username_and_weak_password(client):
    assert _register(client, "1abc").status_code == 400  # 数字开头
    assert _register(client, "ab").status_code == 400    # 太短
    assert _register(client, "a b").status_code == 400   # 非法字符
    r = _register(client, "erin", password="short")
    assert r.status_code == 400 and "密码" in r.json()["detail"]


def test_register_success_rate_limit(client):
    assert _register(client, "user_one").status_code == 201
    # 60 秒间隔内第二次成功注册被拦
    r = _register(client, "user_two")
    assert r.status_code == 429 and "频繁" in r.json()["detail"]


def test_register_attempt_rate_limit(client):
    # 连续 10 次错误验证码后，第 11 次触发 429
    for i in range(10):
        captcha_id, _ = _fresh_captcha()
        _register(client, f"x{i}", captcha_id=captcha_id, captcha_text="XXXX")
    r = _register(client, "x_final")
    assert r.status_code == 429


def test_change_password_flow(client):
    _register(client, "frank", password="oldpassword1")
    r = client.post("/api/auth/password", json={
        "old_password": "wrong", "new_password": "newpassword2"})
    assert r.status_code == 400
    r = client.post("/api/auth/password", json={
        "old_password": "oldpassword1", "new_password": "newpassword2"})
    assert r.status_code == 200
    # 改密即登出：本人当前会话也被清除
    assert client.get("/api/auth/me").status_code == 401
    client.post("/api/auth/logout")
    # 旧密码失效，新密码可登录
    assert client.post("/api/auth/login", json={
        "username": "frank", "password": "oldpassword1"}).status_code == 401
    assert client.post("/api/auth/login", json={
        "username": "frank", "password": "newpassword2"}).status_code == 200


def test_change_password_requires_login(client):
    r = client.post("/api/auth/password", json={
        "old_password": "a", "new_password": "bbbbbbbb"})
    assert r.status_code == 401


def test_change_password_rate_limited(client):
    # 反例：同一用户连续 5 次原密码错误后，第 6 次触发 429（会话被盗在线爆破的唯一闸门）
    _register(client, "grace", password="correctpassword1")
    for i in range(5):
        r = client.post("/api/auth/password", json={
            "old_password": f"wrongguess{i}", "new_password": "newpassword2"})
        assert r.status_code == 400
    r = client.post("/api/auth/password", json={
        "old_password": "wrongguess5", "new_password": "newpassword2"})
    assert r.status_code == 429


def test_change_password_success_not_counted(client):
    # 正例：先错 4 次（未触顶），随后用正确原密码改密成功——成功不计数、不锁本人
    _register(client, "heidi", password="oldpassword9")
    for i in range(4):
        client.post("/api/auth/password", json={
            "old_password": f"wrong{i}", "new_password": "newpassword2"})
    r = client.post("/api/auth/password", json={
        "old_password": "oldpassword9", "new_password": "newpassword2"})
    assert r.status_code == 200


def test_username_available_endpoint(client):
    assert client.get("/api/auth/username-available", params={"username": "newuser"}).json()["available"] is True
    _register(client, "taken_user")
    r = client.get("/api/auth/username-available", params={"username": "TAKEN_user"})
    assert r.json()["available"] is False  # 大小写不敏感
    # 格式非法直接不可用
    assert client.get("/api/auth/username-available", params={"username": "1x"}).json()["available"] is False
