"""访问记录（汇总/明细）与新手引导接口测试。"""
from sqlalchemy import select

from app.models import User
from app.services import access_log as al


def _make_user(client, auth_client, username: str) -> User:
    """管理员建号 + 该用户登录（会话切到该用户），返回登录响应体。

    注意：auth_client 与 client 是同一个 TestClient，登录后管理员会话被顶掉；
    后续要调管理端接口的用例需先调用 _relogin_admin 切回管理员。
    """
    r = auth_client.post("/api/users", json={"username": username, "password": "pw123456"})
    assert r.status_code == 200
    r = client.post("/api/auth/login", json={"username": username, "password": "pw123456"})
    assert r.status_code == 200
    return r.json()


def _relogin_admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200


# ---------- 权限 ----------

def test_access_endpoints_require_login(client):
    assert client.get("/api/admin/access/summary").status_code == 401
    assert client.get("/api/admin/access/logs").status_code == 401


def test_access_endpoints_require_admin(client, auth_client):
    _make_user(client, auth_client, "bob")
    assert client.get("/api/admin/access/summary").status_code == 403
    assert client.get("/api/admin/access/logs").status_code == 403


# ---------- 汇总 ----------

def test_summary_counts_login_and_visits(auth_client):
    r = auth_client.get("/api/admin/access/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] and body["date"]
    admin = next(i for i in body["items"] if i["username"] == "admin")
    # 登录即计一次访问；seed 管理员已完成引导
    assert admin["today_count"] >= 1
    assert admin["total_count"] >= 1
    assert admin["parse_count"] == 0
    assert admin["last_visit_at"]
    assert admin["is_admin"] is True


def test_summary_parse_count(auth_client, db):
    admin = db.scalar(select(User).where(User.username == "admin"))
    al.record_access(db, admin, "parse", detail="爱奇艺 | https://example.com/v/1")
    r = auth_client.get("/api/admin/access/summary")
    admin_row = next(i for i in r.json()["items"] if i["username"] == "admin")
    assert admin_row["parse_count"] == 1
    # parse 不计入「访问次数」
    total_before = admin_row["total_count"]
    al.record_access(db, admin, "parse", detail="second")
    r = auth_client.get("/api/admin/access/summary")
    admin_row = next(i for i in r.json()["items"] if i["username"] == "admin")
    assert admin_row["parse_count"] == 2
    assert admin_row["total_count"] == total_before


# ---------- 明细 ----------

def test_logs_filter_by_user_and_action(auth_client, client, db):
    _make_user(client, auth_client, "carol")
    _relogin_admin(client)  # _make_user 把会话切到了 carol，管理端接口需切回管理员
    carol = db.scalar(select(User).where(User.username == "carol"))
    al.record_access(db, carol, "visit", detail="解析首页")
    al.record_access(db, carol, "parse", detail="腾讯视频 | https://example.com/v/2")

    r = auth_client.get("/api/admin/access/logs", params={"user_id": carol.id})
    body = r.json()
    # _make_user 里 carol 登录记 1 条 login，加上 visit / parse 各 1 条
    assert body["total"] == 3
    assert {i["action"] for i in body["items"]} == {"login", "visit", "parse"}
    # 倒序：最新的 parse 在前
    assert body["items"][0]["action"] == "parse"
    assert body["items"][0]["username"] == "carol"

    r = auth_client.get("/api/admin/access/logs", params={"user_id": carol.id, "action": "parse"})
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["detail"] == "腾讯视频 | https://example.com/v/2"


def test_logs_pagination(auth_client, client, db):
    _make_user(client, auth_client, "dave")
    _relogin_admin(client)
    dave = db.scalar(select(User).where(User.username == "dave"))
    for i in range(25):
        al.record_access(db, dave, "visit", detail=f"page-{i}")
    r = auth_client.get("/api/admin/access/logs",
                        params={"user_id": dave.id, "page": 1, "page_size": 10})
    body = r.json()
    # 25 条 visit + 登录时记的 1 条 login
    assert body["total"] == 26
    assert len(body["items"]) == 10
    r2 = auth_client.get("/api/admin/access/logs",
                         params={"user_id": dave.id, "page": 3, "page_size": 10})
    assert len(r2.json()["items"]) == 6
    # 越界页返回空但不报错
    r3 = auth_client.get("/api/admin/access/logs",
                         params={"user_id": dave.id, "page": 9, "page_size": 10})
    assert r3.json()["items"] == []


# ---------- 本地文件日志 ----------

def test_file_log_written(auth_client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(al, "LOG_DIR", tmp_path)
    admin = db.scalar(select(User).where(User.username == "admin"))
    al.record_access(db, admin, "parse", detail="爱奇艺 | https://example.com/v/9", ip="1.2.3.4")
    files = list(tmp_path.glob("access_*.log"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "admin" in content
    assert "解析视频" in content
    assert "ip=1.2.3.4" in content


# ---------- 新手引导 ----------

def test_seed_admin_onboarding_completed(auth_client):
    assert auth_client.get("/api/auth/me").json()["onboarding_completed"] is True


def test_onboarding_flow_for_new_user(auth_client, client):
    data = _make_user(client, auth_client, "erin")
    # 管理员后台建的号默认未完成引导，注册/登录响应都携带该字段
    assert data["onboarding_completed"] is False
    assert client.get("/api/auth/me").json()["onboarding_completed"] is False

    r = client.post("/api/auth/onboarding/complete")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert client.get("/api/auth/me").json()["onboarding_completed"] is True

    # 幂等：重复标记不报错
    r = client.post("/api/auth/onboarding/complete")
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["onboarding_completed"] is True


def test_onboarding_requires_login(client):
    assert client.post("/api/auth/onboarding/complete").status_code == 401


def test_ensure_columns_idempotent():
    from app.main import _ensure_columns

    _ensure_columns()  # 列已存在时应静默跳过
    _ensure_columns()
