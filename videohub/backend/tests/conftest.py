import os
import tempfile

# 必须在导入 app 之前设置环境变量
os.environ["VIDEOHUB_DB_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["VIDEOHUB_ADMIN_PASSWORD"] = "admin123"
# 访问日志落盘目录同样指向临时目录，避免测试写入真实 backend/logs
os.environ["VIDEOHUB_LOG_DIR"] = tempfile.mkdtemp()

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.database import Base, SessionLocal, engine
from app.main import app
from app.services import presence
from app.services.ratelimit import (
    account_delete_limiter,
    captcha_limiter,
    dashboard_limiter,
    health_limiter,
    heartbeat_limiter,
    login_fail_limiter,
    login_lock_limiter,
    login_user_limiter,
    parse_daily_limiter,
    parse_limiter,
    password_verify_limiter,
    register_attempt_limiter,
    register_success_limiter,
    totp_limiter,
    username_check_limiter,
    visit_limiter,
)

# 登录失败随机延迟（LOGIN_FAIL_DELAY）只影响失败响应的时延节拍，无行为断言意义，
# 置零避免几十次失败登录的用例把套件拖慢数秒；生产默认值见 app/api/auth.py
auth_api.LOGIN_FAIL_DELAY = (0.0, 0.0)


@pytest.fixture(autouse=True)
def _reset_limiters():
    # 限流器是模块级单例，测试间共享同一 client IP / 用户，必须每个用例前后清零
    limiters = (login_fail_limiter, captcha_limiter, visit_limiter,
                username_check_limiter, register_attempt_limiter, register_success_limiter,
                account_delete_limiter, health_limiter, dashboard_limiter,
                parse_limiter, parse_daily_limiter, login_user_limiter, heartbeat_limiter,
                login_lock_limiter, totp_limiter, password_verify_limiter)
    for limiter in limiters:
        limiter.reset()
    # 在线心跳表同为模块级全局态，必须随用例清零，否则在线数断言互相污染
    presence.reset()
    yield
    for limiter in limiters:
        limiter.reset()
    presence.reset()


@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    return client
