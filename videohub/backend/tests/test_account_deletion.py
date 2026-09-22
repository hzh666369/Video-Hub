"""用户自助注销账户的接口测试（正例放行 + 攻击场景反例拒绝）。"""
import pytest

from app.models import AccessLog, Caption, Record, User
from app.services import captcha as captcha_svc


@pytest.fixture(autouse=True)
def _clean_captcha():
    captcha_svc._reset()
    yield
    captcha_svc._reset()


def _register(client, username, password="password123"):
    captcha_id, _png = captcha_svc.new_captcha()
    code = captcha_svc._store[captcha_id][0]
    r = client.post("/api/auth/register", json={
        "username": username, "password": password,
        "captcha_id": captcha_id, "captcha_text": code,
    })
    assert r.status_code == 201
    return r


def _user_with_data(db, username):
    """为已注册用户塞入解析记录/字幕/访问日志，返回 (user, record)。"""
    user = db.query(User).filter_by(username=username).first()
    rec = Record(user_id=user.id, source_url="https://www.bilibili.com/video/BV1xx",
                 platform="bilibili", title="测试视频")
    db.add(rec)
    db.flush()
    db.add(Caption(record_id=rec.id, text_content="hello"))
    db.add(AccessLog(user_id=user.id, username=username, action="login", ip="8.8.8.8"))
    db.commit()
    return user, rec


def test_delete_account_success_wipes_data(client, db):
    _register(client, "byeuser")
    user, rec = _user_with_data(db, "byeuser")

    # 攻击场景反例：密码错误 → 拒绝，账户与数据原封不动
    r = client.request("DELETE", "/api/auth/account", json={"password": "wrongpass1"})
    assert r.status_code == 400
    assert db.query(User).filter_by(username="byeuser").first() is not None
    assert db.query(Record).filter(Record.user_id == user.id).first() is not None

    # 正例：密码正确 → 注销成功，当前会话即失效
    r = client.request("DELETE", "/api/auth/account", json={"password": "password123"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 401

    # 用户与名下解析记录、字幕全部清除（captions 经 FK ON DELETE CASCADE 联动）
    assert db.query(User).filter_by(username="byeuser").first() is None
    assert db.query(Record).filter(Record.user_id == user.id).first() is None
    assert db.query(Caption).filter(Caption.record_id == rec.id).first() is None

    # 访问日志保留可读性：user_id 解除引用，用户名快照仍在
    log = db.query(AccessLog).filter(AccessLog.username == "byeuser").first()
    assert log is not None and log.user_id is None

    # 账户已不存在，旧凭据无法再登录
    assert client.post("/api/auth/login", json={
        "username": "byeuser", "password": "password123"}).status_code == 401


def test_delete_account_requires_login(client):
    r = client.request("DELETE", "/api/auth/account", json={"password": "whatever1"})
    assert r.status_code == 401


def test_admin_cannot_self_delete(auth_client):
    # 管理员保护（L-2 同源）：防止最后一个管理员把自己删掉导致系统失管
    r = auth_client.request("DELETE", "/api/auth/account", json={"password": "admin123"})
    assert r.status_code == 403
    assert "管理员" in r.json()["detail"]
    assert auth_client.get("/api/auth/me").status_code == 200


def test_delete_account_rate_limited(client, db):
    _register(client, "trydel")
    for _ in range(5):
        r = client.request("DELETE", "/api/auth/account", json={"password": "wrongpass1"})
        assert r.status_code == 400
    # 第 6 次触发限流：即使密码正确也拒绝（防会话被盗后暴力试密码删库）
    r = client.request("DELETE", "/api/auth/account", json={"password": "password123"})
    assert r.status_code == 429
    assert db.query(User).filter_by(username="trydel").first() is not None
