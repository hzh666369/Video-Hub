from datetime import datetime

from app.models import AccessLog


def _purge_logs(db):
    """清掉夹具/登录副作用写入的 AccessLog，让断言口径只覆盖用例自己造的数。"""
    db.query(AccessLog).delete()
    db.commit()


def _add_activity(db, *, action="visit", created_at=None):
    db.add(AccessLog(user_id=1, username="admin", action=action, ip="8.8.8.8",
                     created_at=created_at or datetime.now()))
    db.commit()


def test_visits_require_login(client):
    assert client.post("/api/visits").status_code == 401


def test_admin_visit_counts_and_returns_stats(auth_client, db):
    # 今日/累计 = AccessLog 中 visit+login+register 活动数（与数据看板同口径）
    _purge_logs(db)  # 去掉 auth_client 登录留下的 login 日志
    assert auth_client.post("/api/visits").json() == {"today": 1, "total": 1}
    auth_client.post("/api/visits")
    assert auth_client.post("/api/visits").json() == {"today": 3, "total": 3}


def test_visits_counts_include_login_and_register(auth_client, db):
    """登录/注册活动与页面访问同口径计入（看板 KPI「今日访问」同一口径）。"""
    _purge_logs(db)
    db.add(AccessLog(user_id=1, username="admin", action="login", ip="8.8.8.8",
                     created_at=datetime.now()))
    db.add(AccessLog(user_id=1, username="admin", action="register", ip="8.8.8.8",
                     created_at=datetime.now()))
    db.commit()
    assert auth_client.post("/api/visits").json() == {"today": 3, "total": 3}


def test_non_admin_records_but_gets_no_numbers(client, db):
    # 计数面向所有登录用户，但数字只回馈给管理员，避免向普通用户泄露
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    client.post("/api/users", json={"username": "alice", "password": "pw123456"})
    _purge_logs(db)  # 之后只剩 alice/admin 各自的登录日志，口径可控
    client.post("/api/auth/login", json={"username": "alice", "password": "pw123456"})
    r = client.post("/api/visits")
    assert r.status_code == 200
    assert r.json() == {"today": None, "total": None}
    # 管理员随后能看到普通用户那次访问被计入（alice 登录+访问 + admin 登录+访问 = 4）
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert client.post("/api/visits").json() == {"today": 4, "total": 4}


def test_visit_today_resets_on_new_day(auth_client, db):
    # 跨天后今日归零重计，历史累计继续叠加
    _purge_logs(db)
    old_day = datetime(2000, 1, 1, 12, 0, 0)
    for _ in range(7):
        _add_activity(db, created_at=old_day)
    assert auth_client.post("/api/visits").json() == {"today": 1, "total": 8}


def test_visit_today_continues_same_day(auth_client, db):
    _purge_logs(db)
    for _ in range(7):
        _add_activity(db)  # 默认 now → 今天
    assert auth_client.post("/api/visits").json() == {"today": 8, "total": 8}
