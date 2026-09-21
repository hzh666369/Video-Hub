"""细粒度功能点授权:攻击场景回归测试(正例放行 + 反例拒绝)。"""
from sqlalchemy import select

from app.models import User


# ---------- 模型层:permission_set / has_perm ----------

def test_permission_set_parses_json(db):
    u = User(username="p1", password_hash="x", permissions='["dashboard","access"]')
    assert u.permission_set == {"dashboard", "access"}


def test_permission_set_tolerates_bad_json(db):
    for raw in (None, "", "not-json", '{"a":1}'):
        u = User(username="p2", password_hash="x", permissions=raw)
        assert isinstance(u.permission_set, set), raw
    # 非字符串成员丢弃,不抛异常
    u = User(username="p3", password_hash="x", permissions='["dashboard", 3]')
    assert u.permission_set == {"dashboard"}


def test_has_perm_admin_always_true(db):
    admin = User(username="pa", password_hash="x", is_admin=True, permissions="[]")
    assert admin.has_perm("dashboard") is True


def test_has_perm_by_code(db):
    u = User(username="pu", password_hash="x", permissions='["dashboard"]')
    assert u.has_perm("dashboard") is True
    assert u.has_perm("users") is False


def test_default_permission_is_empty(db):
    u = User(username="p4", password_hash="x")
    assert u.permissions == "[]"
    assert u.permission_set == set()
    assert u.has_perm("dashboard") is False


# ---------- 依赖与 /me ----------

def test_me_returns_empty_permissions(auth_client):
    body = auth_client.get("/api/auth/me").json()
    assert body["permissions"] == []


def test_require_perm_factory_builds(auth_client):
    # has_perm 已由模型层测试覆盖;此处验证工厂可构造、依赖可被 FastAPI 解析链接受
    from app.api.deps import require_perm
    assert callable(require_perm("dashboard"))


# ---------- 端点权限重划:攻击场景 ----------

def _login_as(auth_client, db, perms, username="alice"):
    """用管理员建普通用户 → 赋权 → 切换会话为该用户(TestClient 共用 cookie jar)。"""
    from app.services.auth import hash_password
    db.add(User(username=username, password_hash=hash_password("alice12345"),
                permissions=perms))
    db.commit()
    r = auth_client.post("/api/auth/login",
                         json={"username": username, "password": "alice12345"})
    assert r.status_code == 200
    return auth_client


def test_plain_user_blocked_from_all_admin_reads(auth_client, db):
    c = _login_as(auth_client, db, "[]")
    for path in ("/api/settings", "/api/users", "/api/admin/access/summary",
                 "/api/admin/access/logs", "/api/admin/dashboard"):
        assert c.get(path).status_code == 403, path


def test_perm_dashboard_allows_dashboard_only(auth_client, db):
    c = _login_as(auth_client, db, '["dashboard"]')
    assert c.get("/api/admin/dashboard").status_code == 200
    assert c.get("/api/settings").status_code == 403
    assert c.get("/api/users").status_code == 403
    assert c.get("/api/admin/access/summary").status_code == 403


def test_perm_routes_read_only(auth_client, db):
    c = _login_as(auth_client, db, '["routes"]')
    assert c.get("/api/settings").status_code == 200
    # 只读授权必须挡住写通道
    r = c.put("/api/settings",
              json={"vip_routes": [{"name": "x", "prefix": "https://jx.example.com/?url="}]})
    assert r.status_code == 403


def test_perm_users_read_only(auth_client, db):
    c = _login_as(auth_client, db, '["users"]')
    assert c.get("/api/users").status_code == 200
    assert c.post("/api/users", json={"username": "eve", "password": "eve12345"}).status_code == 403
    assert c.delete("/api/users/2").status_code == 403
    assert c.post("/api/users/2/reset-password").status_code == 403


def test_perm_access_read_only(auth_client, db):
    c = _login_as(auth_client, db, '["access"]')
    assert c.get("/api/admin/access/summary").status_code == 200
    assert c.get("/api/admin/access/logs").status_code == 200


def test_admin_unaffected(auth_client):
    # has_perm 管理员恒真:全部读端点照常
    for path in ("/api/settings", "/api/users", "/api/admin/access/summary",
                 "/api/admin/access/logs", "/api/admin/dashboard"):
        assert auth_client.get(path).status_code == 200, path


def test_perm_denied_detail_exact(auth_client, db):
    # T2 审查补充:require_perm 端点级回归缺 detail 精确串断言
    c = _login_as(auth_client, db, "[]")
    r = c.get("/api/admin/dashboard")
    assert r.status_code == 403
    assert r.json()["detail"] == "没有访问该功能的权限"


# ---------- 管理端点:设置用户权限 ----------

def _mk_alice(auth_client, db, username="alice"):
    from app.services.auth import hash_password
    db.add(User(username=username, password_hash=hash_password("alice12345")))
    db.commit()
    return db.scalar(select(User).where(User.username == username))


def test_set_permissions_roundtrip(auth_client, db):
    u = _mk_alice(auth_client, db)
    r = auth_client.put(f"/api/users/{u.id}/permissions",
                        json={"permissions": ["dashboard", "access"]})
    assert r.status_code == 200
    assert r.json()["permissions"] == ["access", "dashboard"]  # 排序去重后回显
    db.expire_all()
    assert db.get(User, u.id).permission_set == {"dashboard", "access"}
    # 空数组 = 清空授权
    assert auth_client.put(f"/api/users/{u.id}/permissions",
                           json={"permissions": []}).json()["permissions"] == []


def test_set_permissions_rejects_unknown_code(auth_client, db):
    u = _mk_alice(auth_client, db)
    r = auth_client.put(f"/api/users/{u.id}/permissions",
                        json={"permissions": ["dashboard", "superadmin"]})
    assert r.status_code == 400
    assert "superadmin" in r.json()["detail"]


def test_set_permissions_on_admin_403(auth_client, db):
    admin = db.scalar(select(User).where(User.is_admin.is_(True)))
    r = auth_client.put(f"/api/users/{admin.id}/permissions", json={"permissions": []})
    assert r.status_code == 403


def test_set_permissions_requires_admin(auth_client, db):
    u = _mk_alice(auth_client, db)
    # 已被授权的普通用户也不能给他人授权(只有管理员可以)
    c = _login_as(auth_client, db, '["dashboard"]', username="bob")
    r = c.put(f"/api/users/{u.id}/permissions", json={"permissions": ["users"]})
    assert r.status_code == 403


def test_users_list_includes_permissions(auth_client, db):
    u = _mk_alice(auth_client, db)
    auth_client.put(f"/api/users/{u.id}/permissions", json={"permissions": ["routes"]})
    items = {i["username"]: i for i in auth_client.get("/api/users").json()}
    assert items["alice"]["permissions"] == ["routes"]
