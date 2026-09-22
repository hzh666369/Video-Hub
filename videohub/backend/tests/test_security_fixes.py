"""2026-09 安全审计修复的回归测试。

覆盖：真实客户端 IP 提取、代理目标 SSRF 校验、会话密码指纹（改密踢旧会话）、
管理员账户保护、分页参数约束、验证码/访问计数限流。
"""
import ipaddress

import httpx
import pytest
import respx

from app.models import Record
from app.services import urlguard
from app.services.client_ip import get_client_ip, rate_limit_key
from starlette.requests import Request


# ---------- 真实客户端 IP（VULN-001） ----------

def _req(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "headers": raw, "client": ("127.0.0.1", 12345)}
    return Request(scope)


def test_client_ip_prefers_cf_connecting_ip():
    assert get_client_ip(_req({"CF-Connecting-IP": "203.0.113.9"})) == "203.0.113.9"


def test_client_ip_ignores_garbage_cf_header():
    # 非法值（含注入尝试）不得进入限流 key / 日志，回退到传输层地址
    req = _req({"CF-Connecting-IP": "not-an-ip\r\nFORGED"})
    assert get_client_ip(req) == "127.0.0.1"


def test_client_ip_falls_back_to_peer():
    assert get_client_ip(_req()) == "127.0.0.1"


# ---------- 代理目标校验（VULN-002） ----------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x.mp4",
    "http://10.0.0.5/x.mp4",
    "http://192.168.1.10/x.mp4",
    "http://172.16.0.1/x.mp4",
    "http://169.254.169.254/latest/meta-data/",  # 云元数据
    "http://100.64.0.1/x.mp4",                    # CGNAT
    "http://[::1]/x.mp4",
    "ftp://example.com/x.mp4",
    "file:///etc/passwd",
])
async def test_urlguard_rejects_non_public_targets(url):
    with pytest.raises(urlguard.ForbiddenUpstreamError):
        await urlguard.validate_proxy_target(url)


async def test_urlguard_allows_public_ip_literal():
    await urlguard.validate_proxy_target("https://8.8.8.8/v.mp4")


async def test_urlguard_rejects_domain_resolving_private(monkeypatch):
    async def fake_resolve(host):
        return ["93.184.216.34", "10.0.0.7"]  # 混入内网记录 → 整体拒绝
    monkeypatch.setattr(urlguard, "_resolve_host", fake_resolve)
    with pytest.raises(urlguard.ForbiddenUpstreamError):
        await urlguard.validate_proxy_target("https://evil.example.com/v.mp4")


async def test_urlguard_allows_domain_resolving_public(monkeypatch):
    async def fake_resolve(host):
        return ["93.184.216.34"]
    monkeypatch.setattr(urlguard, "_resolve_host", fake_resolve)
    await urlguard.validate_proxy_target("https://cdn.example.com/v.mp4")


async def test_urlguard_dns_failure_allows_through(monkeypatch):
    async def fake_resolve(host):
        return []  # 解析失败：放行，让代理请求自然报错
    monkeypatch.setattr(urlguard, "_resolve_host", fake_resolve)
    await urlguard.validate_proxy_target("https://offline.example.com/v.mp4")


def _mk_stream_record(db, user_id, **kw):
    rec = Record(user_id=user_id,
                 source_url=kw.pop("source_url", "https://www.douyin.com/video/1"),
                 platform=kw.pop("platform", "douyin"),
                 parse_status="parsed", **kw)
    db.add(rec)
    db.commit()
    return rec


def test_stream_proxy_refuses_internal_target(auth_client, db):
    rec = _mk_stream_record(db, 1, video_url="http://127.0.0.1:8000/steal.mp4")
    r = auth_client.get(f"/api/stream/{rec.id}")
    assert r.status_code == 403
    assert "受限" in r.json()["detail"]


def test_stream_cover_refuses_internal_target(auth_client, db):
    rec = _mk_stream_record(db, 1, video_url="https://www.douyin.com/a.mp4",
                            cover_url="http://169.254.169.254/meta")
    r = auth_client.get(f"/api/stream/{rec.id}/cover")
    assert r.status_code == 403


# ---------- 会话密码指纹（L-1） ----------

def test_password_change_invalidates_session(auth_client):
    r = auth_client.post("/api/auth/password",
                         json={"old_password": "admin123", "new_password": "newpass123"})
    assert r.status_code == 200
    # 改密后全端下线（含本人当前会话），需用新密码重新登录
    assert auth_client.get("/api/auth/me").status_code == 401
    assert auth_client.post("/api/auth/login",
                            json={"username": "admin", "password": "newpass123"}).status_code == 200


def test_stale_session_kicked_after_password_change(client, db):
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    # 模拟另一处（管理员重置/他端改密）改掉密码，旧会话未刷新指纹
    from app.services.auth import hash_password
    from app.models import User
    u = db.query(User).filter_by(username="admin").first()
    u.password_hash = hash_password("hacked12345")
    db.commit()
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert "失效" in r.json()["detail"]
    # 旧密码已不可登录，新密码可正常登录
    assert client.post("/api/auth/login",
                       json={"username": "admin", "password": "admin123"}).status_code == 401
    assert client.post("/api/auth/login",
                       json={"username": "admin", "password": "hacked12345"}).status_code == 200


# ---------- 管理员账户保护（L-2） ----------

def test_admin_cannot_reset_admin_password(auth_client, db):
    from app.models import User
    admin = db.query(User).filter_by(username="admin").first()
    r = auth_client.post(f"/api/users/{admin.id}/reset-password")
    assert r.status_code == 403


def test_admin_cannot_delete_other_admin(auth_client, db):
    # 建第二个管理员：一个被盗的 admin 不得删除/接管另一个 admin
    auth_client.post("/api/users", json={"username": "root2", "password": "pw123456",
                                         "is_admin": True})
    from app.models import User
    root2 = db.query(User).filter_by(username="root2").first()
    r = auth_client.delete(f"/api/users/{root2.id}")
    assert r.status_code == 403
    # 普通用户仍可正常删除（返回 200 或 400 取决于名下记录，此处无记录 → 200）
    auth_client.post("/api/users", json={"username": "temp", "password": "pw123456"})
    temp = db.query(User).filter_by(username="temp").first()
    assert auth_client.delete(f"/api/users/{temp.id}").status_code == 200


def test_reset_password_kicks_target_sessions(auth_client, db):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models import User
    auth_client.post("/api/users", json={"username": "bob", "password": "pw123456"})
    # 用独立客户端模拟 bob 在自己设备上的会话
    with TestClient(app) as bob_client:
        assert bob_client.post("/api/auth/login",
                               json={"username": "bob", "password": "pw123456"}).status_code == 200
        assert bob_client.get("/api/auth/me").status_code == 200
        bob = db.query(User).filter_by(username="bob").first()
        # 管理员重置 bob 密码（auth_client 始终是 admin 会话）
        r = auth_client.post(f"/api/users/{bob.id}/reset-password")
        assert r.status_code == 200
        new_pw = r.json()["new_password"]
        # bob 的旧会话立即失效（密码指纹失配），新密码可重新登录
        assert bob_client.get("/api/auth/me").status_code == 401
        assert bob_client.post("/api/auth/login",
                               json={"username": "bob", "password": new_pw}).status_code == 200


# ---------- 分页约束（L-3） ----------

def test_records_reject_oversized_page(auth_client):
    assert auth_client.get("/api/records", params={"page_size": 1000}).status_code == 422
    assert auth_client.get("/api/records", params={"page": 0}).status_code == 422
    assert auth_client.get("/api/records", params={"page_size": 100}).status_code == 200


# ---------- 限流（VULN-003 / VULN-004） ----------

def test_captcha_endpoint_rate_limited(client):
    codes = [client.get("/api/auth/captcha").status_code for _ in range(31)]
    assert codes[:-1] == [200] * 30
    assert codes[-1] == 429


def test_visits_endpoint_rate_limited_per_user(auth_client):
    codes = [auth_client.post("/api/visits").status_code for _ in range(31)]
    assert codes[:-1] == [200] * 30
    assert codes[-1] == 429


# ---------- 密码 72 字节上限（bcrypt 5.x 超长抛 ValueError → 500） ----------

# 104 字节，强度段位足够高——没有上限校验时会通过强度检查，在 hash/verify 处炸 500
LONG_PASSWORD = "Aa1!" + "x" * 100


def test_verify_password_overlong_returns_false():
    from app.services.auth import hash_password, verify_password
    assert verify_password(LONG_PASSWORD, hash_password("admin123")) is False


def test_hash_password_overlong_raises_value_error():
    from app.services.auth import hash_password
    with pytest.raises(ValueError, match="72"):
        hash_password(LONG_PASSWORD)


def test_login_overlong_password_401_not_500(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": LONG_PASSWORD})
    assert r.status_code == 401


def test_register_overlong_password_400(client):
    # _check_password_strength 在验证码校验之前，超长直接 400
    r = client.post("/api/auth/register", json={
        "username": "newbie1", "password": LONG_PASSWORD,
        "captcha_id": "x", "captcha_text": "x"})
    assert r.status_code == 400
    assert "72" in r.json()["detail"]


def test_register_overlong_multibyte_password_400(client):
    # 30 个汉字 = 90 字节 > 72：按 UTF-8 字节数判定，而非字符数
    r = client.post("/api/auth/register", json={
        "username": "newbie1", "password": "密" * 30,
        "captcha_id": "x", "captcha_text": "x"})
    assert r.status_code == 400
    assert "72" in r.json()["detail"]


def test_change_password_overlong_400(auth_client):
    r = auth_client.post("/api/auth/password", json={
        "old_password": "admin123", "new_password": LONG_PASSWORD})
    assert r.status_code == 400


def test_admin_create_user_overlong_password_400(auth_client):
    # 管理员建站内账号不做强度规则，但 bcrypt 硬上限必须守
    r = auth_client.post("/api/users", json={"username": "longpw", "password": LONG_PASSWORD})
    assert r.status_code == 400


# ---------- 解析线路 prefix 协议校验（存储型 XSS / 盲 SSRF） ----------

def test_settings_reject_non_https_route_prefix(auth_client):
    for prefix in ("javascript:alert(1)//", "http://jx.example.com/?url=", "data:text/html,x//"):
        r = auth_client.put("/api/settings", json={"vip_routes": [{"name": "x", "prefix": prefix}]})
        assert r.status_code == 400, prefix
    # 合法 https（含 scheme 大小写混合）正常放行
    assert auth_client.put("/api/settings", json={
        "vip_routes": [{"name": "x", "prefix": "HTTPS://jx.example.com/?url="}]}).status_code == 200


def _mk_vip_record(db, user_id=1, route_name=None):
    rec = Record(user_id=user_id, source_type="vip", parse_status="parsed", platform="tencent",
                 source_url="https://v.qq.com/x/cover/abc",
                 video_url="https://v.qq.com/x/cover/abc", route_name=route_name)
    db.add(rec)
    db.commit()
    return rec


def test_embed_rejects_stored_javascript_prefix(auth_client, db):
    # 直改库写入恶意线路（绕过 PUT 校验）：使用时必须复验，不得进 iframe
    from app.services.settings import set_setting
    set_setting(db, "vip_routes", [{"name": "evil", "prefix": "javascript:alert(1)//"}])
    rec = _mk_vip_record(db)
    r = auth_client.get(f"/api/records/{rec.id}/embed")
    assert r.status_code == 400
    assert "https" in r.json()["detail"]


def test_parse_vip_rejects_stored_javascript_prefix(auth_client, db):
    from app.services.settings import set_setting
    set_setting(db, "vip_routes", [{"name": "evil", "prefix": "javascript:alert(1)//"}])
    r = auth_client.post("/api/parse/vip", json={"url": "https://v.qq.com/x/cover/abc"})
    assert r.status_code == 400


def test_embed_check_rejects_internal_prefix(auth_client, db):
    # https 协议合法但指向内网：服务器端 HEAD 探测前必须过 SSRF 校验
    from app.services.settings import set_setting
    set_setting(db, "vip_routes", [{"name": "internal", "prefix": "https://192.168.1.1/parse?u="}])
    rec = _mk_vip_record(db)
    r = auth_client.get(f"/api/records/{rec.id}/embed-check")
    assert r.status_code == 403
    assert "受限" in r.json()["detail"]


@respx.mock
def test_embed_check_public_prefix_passes_guard(auth_client, db, monkeypatch):
    # 这条测的是 guard 的设计行为「DNS 解析失败 → 放行」（urlguard docstring 明示），
    # 随后 HEAD 失败 → embeddable 未知（None）。
    # 原实现依赖 .invalid 在本机 DNS 必然解析失败，但运营商/路由器 DNS 劫持可能把它
    # 解析到网关等私网地址（guard 403）或让 HEAD 意外成功，行为随网络环境漂移。
    # 改为显式 mock：解析返回空（DNS 失败）+ HEAD 连接失败，任何环境都稳定。
    async def fake_resolve(host):
        return []
    monkeypatch.setattr("app.services.urlguard._resolve_host", fake_resolve)
    respx.head(host="jx.nonexistent.invalid").mock(
        side_effect=httpx.ConnectError("mocked DNS failure"))

    from app.services.settings import set_setting
    set_setting(db, "vip_routes", [{"name": "ok", "prefix": "https://jx.nonexistent.invalid/?u="}])
    rec = _mk_vip_record(db)
    r = auth_client.get(f"/api/records/{rec.id}/embed-check")
    assert r.status_code == 200
    assert r.json()["embeddable"] is None


# ---------- 用户名查重限流按真实访客 IP 分桶 ----------

def test_username_check_rate_limited_per_real_ip(client):
    headers = {"CF-Connecting-IP": "203.0.113.77"}
    codes = [client.get("/api/auth/username-available",
                        params={"username": "abc"}, headers=headers).status_code
             for _ in range(31)]
    assert codes[:-1] == [200] * 30
    assert codes[-1] == 429


def test_username_check_buckets_by_cf_ip(client):
    # cloudflared 隧道下 request.client.host 是内网地址：若用它分桶，全站共享一个桶，
    # 一人刷接口全站 429；按 CF-Connecting-IP 分桶则各访客互不影响
    h_a = {"CF-Connecting-IP": "203.0.113.10"}
    h_b = {"CF-Connecting-IP": "203.0.113.11"}
    for _ in range(30):
        client.get("/api/auth/username-available", params={"username": "abc"}, headers=h_a)
    assert client.get("/api/auth/username-available",
                      params={"username": "abc"}, headers=h_a).status_code == 429
    assert client.get("/api/auth/username-available",
                      params={"username": "abc"}, headers=h_b).status_code == 200


# ---------- 限流桶 IPv6 /64 收敛 + 空桶回收（2026-09-15 审计 H-1） ----------

def test_rate_limit_key_collapses_ipv6_to_prefix():
    # 同一 /64 内旋转接口标识符（RFC 4941 隐私扩展）→ 同一个限流桶
    assert rate_limit_key(_req({"CF-Connecting-IP": "2001:db8:1:2::1"})) == "2001:db8:1:2::/64"
    assert rate_limit_key(_req({"CF-Connecting-IP": "2001:db8:1:2:ffff:aaaa:bbbb:cccc"}
                               )) == "2001:db8:1:2::/64"
    # 不同 /64 互不影响；IPv4 原样；无头回退传输层地址
    assert rate_limit_key(_req({"CF-Connecting-IP": "2001:db8:1:3::1"})) == "2001:db8:1:3::/64"
    assert rate_limit_key(_req({"CF-Connecting-IP": "203.0.113.9"})) == "203.0.113.9"
    assert rate_limit_key(_req()) == "127.0.0.1"


def test_get_client_ip_keeps_full_address_for_logs():
    # 日志/溯源口径不受限流收敛影响：仍返回完整地址
    assert get_client_ip(_req({"CF-Connecting-IP": "2001:db8:1:2::dead:beef"})
                         ) == "2001:db8:1:2::dead:beef"


def test_captcha_rate_limit_blocks_ipv6_rotation_within_prefix(client):
    # 攻击场景回归（反例拒绝）：/64 内轮换 IPv6 接口标识符不再各自从零计数
    codes = [client.get("/api/auth/captcha",
                        headers={"CF-Connecting-IP": f"2001:db8:aa:bb::{i:x}"}).status_code
             for i in range(31)]
    assert codes[:-1] == [200] * 30
    assert codes[-1] == 429


def test_captcha_rate_limit_independent_across_prefixes(client):
    # 正例放行：不同 /64 的正常访客互不误伤
    for _ in range(30):
        client.get("/api/auth/captcha", headers={"CF-Connecting-IP": "2001:db8:aa:bb::1"})
    assert client.get("/api/auth/captcha",
                      headers={"CF-Connecting-IP": "2001:db8:aa:bb::1"}).status_code == 429
    assert client.get("/api/auth/captcha",
                      headers={"CF-Connecting-IP": "2001:db8:cc:dd::1"}).status_code == 200


def test_rate_limiter_sweeps_expired_keys(monkeypatch):
    # 内存回收：过期空桶在全表清扫时删除，_hits 不随独立 key 数无限增长
    from app.services import ratelimit as rl
    t = 1000.0
    monkeypatch.setattr(rl.time, "monotonic", lambda: t)
    limiter = rl.RateLimiter(window_seconds=60, max_hits=5)
    for i in range(50):
        limiter.allow(f"k{i}")
    assert len(limiter._hits) == 50
    t += 121  # 越过窗口 60s + 清扫节律 60s
    limiter.allow("fresh")  # 触发清扫：50 个过期桶全部回收，只留新桶
    assert len(limiter._hits) == 1


def test_rate_limiter_check_creates_no_entry():
    # check() 只读探测：不得为每个未知 key 永久留下空桶（登录每次都先 check）
    from app.services.ratelimit import RateLimiter
    limiter = RateLimiter(window_seconds=60, max_hits=5)
    assert limiter.check("never-seen") == 0.0
    assert "never-seen" not in limiter._hits


# ---------- 用户名 NOCASE 唯一约束（2026-09-15 审计 M-5） ----------

def test_username_nocase_unique_constraint(client, db):
    # DB 层兜底红线 3.1：大小写变体不得同时入库（预检查窗口外的并发竞态由此拦截）
    from sqlalchemy.exc import IntegrityError

    from app.models import User
    db.add(User(username="CaseDup", password_hash="x"))
    db.commit()
    db.add(User(username="casedup", password_hash="y"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_create_user_case_variant_conflict_409(auth_client):
    # 管理员建号撞已注册用户名的大小写变体 → 409（并发窗口由 NOCASE 索引兜底）
    r = auth_client.post("/api/users", json={"username": "ADMIN", "password": "pw123456"})
    assert r.status_code == 409


# ---------- API 文档端点默认关闭（L-1） ----------

def test_docs_endpoints_disabled_by_default(client):
    # 公网暴露下不送全量 API 地图；本地调试可设 VIDEOHUB_DOCS=1 开启。
    # 关闭后 /docs 落到 SPA 回退（返回 index.html 而非文档内容）
    for path in ("/docs", "/redoc", "/openapi.json"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")


def test_docs_env_flag_enables_docs_endpoints():
    # L-1 开启路径：VIDEOHUB_DOCS=1 时文档端点恢复。app 在本进程已按默认（关闭）
    # 初始化，环境变量无法追溯生效，故用子进程以干净环境验证
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    code = ("from app.main import app; "
            "assert app.docs_url == '/docs' and app.redoc_url == '/redoc' "
            "and app.openapi_url == '/openapi.json'")
    env = {**os.environ, "VIDEOHUB_DOCS": "1"}
    result = subprocess.run([sys.executable, "-c", code], cwd=backend, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


# ---------- 基础安全响应头（S17） ----------

def test_security_headers_on_responses(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
