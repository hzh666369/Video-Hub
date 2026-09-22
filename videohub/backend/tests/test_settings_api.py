from sqlalchemy import func, select

from app.models import AccessLog, Caption, Record, User


def test_settings_require_admin(client):
    assert client.get("/api/settings").status_code == 401
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    # admin 通过，说明 401 来自未登录而非路由缺失
    assert client.get("/api/settings").status_code == 200


def test_non_admin_forbidden_on_admin_routes(client):
    # 权限回归：把 require_admin 换成 get_current_user 时这里必须失败
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert client.post("/api/users", json={"username": "alice", "password": "pw123456"}).status_code == 200
    admin_id = client.get("/api/auth/me").json()["id"]
    client.post("/api/auth/login", json={"username": "alice", "password": "pw123456"})
    me = client.get("/api/auth/me").json()
    assert me["username"] == "alice" and me["is_admin"] is False
    assert client.get("/api/settings").status_code == 403
    assert client.put("/api/settings", json={"vip_routes": [{"name": "X", "prefix": "https://jx.example.com/?url="}]}).status_code == 403
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users", json={"username": "eve", "password": "pw123456"}).status_code == 403
    assert client.delete(f"/api/users/{admin_id}").status_code == 403


def test_vip_routes_default_seeded_and_editable(auth_client):
    data = auth_client.get("/api/settings").json()
    assert data["vip_routes"][0]["name"] == "线路1"
    routes = [{"name": "自定义", "prefix": "https://jx.example.com/?url="}]
    auth_client.put("/api/settings", json={"vip_routes": routes, "vip_default_route": "自定义"})
    data = auth_client.get("/api/settings").json()
    assert data["vip_routes"] == routes and data["vip_default_route"] == "自定义"


def test_put_settings_rejects_malformed_routes(auth_client):
    # 坏结构线路会让 VIP 解析 KeyError 500，必须在入库前拦截
    bad_payloads = [
        [{"name": "X"}],                                              # 缺 prefix
        [{"name": "", "prefix": "https://jx.example.com/?url="}],     # 空 name
        [{"name": "X", "prefix": "https://jx.example.com/?url="},
         {"name": "X", "prefix": "https://jx2.example.com/?url="}],   # 重名
    ]
    for payload in bad_payloads:
        r = auth_client.put("/api/settings", json={"vip_routes": payload})
        assert r.status_code == 400, payload
    r = auth_client.put("/api/settings", json={
        "vip_routes": [{"name": "X", "prefix": "https://jx.example.com/?url="}],
        "vip_default_route": "不存在的线路"})
    assert r.status_code == 400
    # 拒绝后不应写入任何一半数据
    data = auth_client.get("/api/settings").json()
    assert data["vip_routes"][0]["name"] == "线路1"


def test_user_management(auth_client):
    r = auth_client.post("/api/users", json={"username": "alice", "password": "pw123456"})
    assert r.status_code == 200
    users = auth_client.get("/api/users").json()
    assert any(u["username"] == "alice" and u["is_admin"] is False for u in users)
    uid = next(u["id"] for u in users if u["username"] == "alice")
    assert auth_client.delete(f"/api/users/{uid}").status_code == 200


def test_create_user_rejects_duplicate_username(auth_client):
    # 管理员新增用户只要求用户名唯一：大小写不敏感 + 去首尾空格（与注册判重口径一致）
    assert auth_client.post("/api/users", json={"username": "alice", "password": "pw123456"}).status_code == 200
    for dup in ("alice", "Alice", "ALICE", " alice ", "alice "):
        r = auth_client.post("/api/users", json={"username": dup, "password": "pw123456"})
        assert r.status_code == 409, dup
        assert "已存在" in r.json()["detail"]
    # 空白用户名直接拒绝
    assert auth_client.post("/api/users", json={"username": "   ", "password": "pw123456"}).status_code == 400
    # 不做注册页格式限制：非法字符、超短密码均允许，由管理员自行决定
    assert auth_client.post("/api/users", json={"username": "a b!", "password": "1"}).status_code == 200
    # 提交时首尾空格被去除后入库
    users = auth_client.get("/api/users").json()
    assert all(u["username"] == u["username"].strip() for u in users)


def test_delete_user_purges_records_with_cascade(client, db):
    # 行为对齐自助注销：管理员删除有解析记录的用户不再拒绝，而是连带清除记录（captions 级联）
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert client.post("/api/users", json={"username": "bob", "password": "pw123456"}).status_code == 200
    user = db.scalar(select(User).where(User.username == "bob"))
    rec = Record(user_id=user.id, source_url="https://v.douyin.com/x1", platform="douyin")
    db.add(rec)
    db.commit()
    db.add(Caption(record_id=rec.id, text_content="caption"))
    db.commit()

    # list_users 带出 record_count，供前端删除确认弹窗提示连带清除数量
    users = client.get("/api/users").json()
    bob = next(u for u in users if u["username"] == "bob")
    assert bob["record_count"] == 1

    uid, rid = user.id, rec.id  # expire_all 后 rec 对象不可再取属性（行已删，刷新即抛），先存裸值
    r = client.delete(f"/api/users/{uid}")
    assert r.status_code == 200, r.text
    db.expire_all()  # 本会话缓存了 user/record 对象，须失效后重查才能真正反映删除
    assert db.get(User, uid) is None
    assert db.scalar(select(func.count()).select_from(Record).where(Record.user_id == uid)) == 0
    assert db.get(Caption, rid) is None
    # 删除后其余用户的记录不受影响
    assert db.scalar(select(func.count()).select_from(Record)) == 0


def test_delete_user_with_access_logs(client, db):
    # 回归：access_logs.user_id 外键曾在删除用户时触发 FOREIGN KEY constraint failed；
    # 修复后日志解除引用（user_id 置 NULL），用户可正常删除且日志凭用户名快照保留
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert client.post("/api/users", json={"username": "carol", "password": "pw123456"}).status_code == 200
    user = db.scalar(select(User).where(User.username == "carol"))
    from app.services import access_log as al
    al.record_access(db, user, "visit", detail="解析首页")

    uid = user.id
    r = client.delete(f"/api/users/{uid}")
    assert r.status_code == 200, r.text
    db.expire_all()  # 本会话缓存了 user 对象，须失效后重查才能真正反映删除
    assert db.get(User, uid) is None
    log = db.scalar(select(AccessLog).where(AccessLog.username == "carol"))
    assert log is not None and log.user_id is None and log.username == "carol"


def test_reset_user_password(client, auth_client, db):
    # 管理员重置普通用户密码：返回新密码，且新密码可登录、旧密码失效
    assert client.post("/api/users", json={"username": "dave", "password": "pw123456"}).status_code == 200
    user = db.scalar(select(User).where(User.username == "dave"))
    r = auth_client.post(f"/api/users/{user.id}/reset-password")
    assert r.status_code == 200
    payload = r.json()
    assert payload["username"] == "dave"
    new_password = payload["new_password"]
    assert len(new_password) == 12
    assert client.post("/api/auth/login", json={"username": "dave", "password": new_password}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "dave", "password": "pw123456"}).status_code != 200


def test_reset_user_password_requires_admin(client, db):
    # 普通用户无权调用重置接口
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert client.post("/api/users", json={"username": "erin", "password": "pw123456"}).status_code == 200
    user = db.scalar(select(User).where(User.username == "erin"))
    client.post("/api/auth/logout")
    assert client.post(f"/api/users/{user.id}/reset-password").status_code in (401, 403)
    assert client.post("/api/users/999/reset-password").status_code in (401, 403)


def test_reset_user_password_not_found(auth_client):
    assert auth_client.post("/api/users/999/reset-password").status_code == 404
