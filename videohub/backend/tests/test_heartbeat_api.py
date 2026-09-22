"""在线心跳端点 + 看板实时在线人数口径回归（2026-09-15）。

口径：online_users = 近 120 秒内有心跳的去重登录用户（presence 内存表），
不再从 AccessLog 活动推断。
"""
from fastapi.testclient import TestClient

from app.main import app
from app.models import AccessLog


def test_heartbeat_requires_auth(client):
    assert client.post("/api/heartbeat").status_code == 401


def test_heartbeat_marks_user_online(auth_client):
    # 未心跳时在线为 0（即使刚登录过、AccessLog 里有 login 记录）
    assert auth_client.get("/api/admin/dashboard").json()["online_users"] == 0
    assert auth_client.post("/api/heartbeat").status_code == 200
    assert auth_client.get("/api/admin/dashboard").json()["online_users"] == 1


def test_heartbeat_rate_limited(auth_client):
    # 12 次/分/用户：阈值要按「每标签页 2 次/分钟」的乘数留量（原先取 4 漏算了多标签），
    # 前 12 次 200，第 13 次 429（conftest 已登记 reset）
    for _ in range(12):
        assert auth_client.post("/api/heartbeat").status_code == 200
    assert auth_client.post("/api/heartbeat").status_code == 429


def test_online_users_counts_distinct_users(client, auth_client):
    """两个登录用户各自心跳 → 在线 2；同一用户重复心跳不重复计数。

    注意 auth_client 与 client 是同一会话对象（conftest 复用）：alice 必须用
    独立的第二个 TestClient 登录，否则会把 admin 的会话顶掉导致看板 403。
    """
    auth_client.post("/api/users", json={"username": "alice", "password": "pw123456"})
    assert auth_client.post("/api/heartbeat").status_code == 200
    assert auth_client.post("/api/heartbeat").status_code == 200  # admin 重复打仍算 1
    with TestClient(app) as alice:
        assert alice.post("/api/auth/login", json={"username": "alice", "password": "pw123456"}).status_code == 200
        assert alice.post("/api/heartbeat").status_code == 200
    assert auth_client.get("/api/admin/dashboard").json()["online_users"] == 2


def test_access_log_activity_does_not_count_as_online(client, db, auth_client):
    """口径回归：AccessLog 活动（visit/login/parse）不再让「没打心跳」的用户算在线。"""
    db.add(AccessLog(user_id=1, username="admin", action="visit", ip="8.8.8.8"))
    db.commit()
    assert auth_client.get("/api/admin/dashboard").json()["online_users"] == 0
