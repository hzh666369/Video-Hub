import httpx
import respx
from sqlalchemy import func, select

from app.models import Record


def test_vip_routes_listed_for_normal_user(client):
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    r = client.get("/api/parse/vip-routes")
    assert r.status_code == 200
    data = r.json()
    assert data["default_route"] == "线路1"  # 无 vip_default_route 时回退到首条
    assert {route["name"] for route in data["routes"]} >= {"虾米", "万能稳定"}


def test_parse_vip_rejects_short_link(auth_client):
    r = auth_client.post("/api/parse/vip", json={"url": "https://www.douyin.com/video/1"})
    assert r.status_code == 400


def test_parse_vip_creates_record_and_embed(auth_client, db):
    r = auth_client.post("/api/parse/vip",
                         json={"url": "https://v.qq.com/x/cover/abc", "route_name": "万能稳定"})
    assert r.status_code == 200
    data = r.json()
    assert data["record"]["source_type"] == "vip"
    assert data["record"]["parse_status"] == "parsed"
    assert data["embed_url"] == "https://jx.m3u8.tv/jiexi/?url=" + "https%3A%2F%2Fv.qq.com%2Fx%2Fcover%2Fabc"


def test_parse_vip_stores_route_name_on_record(auth_client, db):
    auth_client.post("/api/parse/vip",
                     json={"url": "https://v.qq.com/x/cover/abc", "route_name": "万能稳定"})
    rec = db.scalar(select(Record).where(Record.source_type == "vip"))
    assert rec is not None
    assert rec.route_name == "万能稳定"


def test_parse_vip_unknown_route_falls_back_to_first(auth_client, db):
    r = auth_client.post("/api/parse/vip",
                         json={"url": "https://v.qq.com/x/cover/abc", "route_name": "不存在线路"})
    assert r.status_code == 200
    rec = db.scalar(select(Record).where(Record.source_type == "vip"))
    assert rec.route_name == "线路1"  # 静默回退到第一条并如实记录


# ---------- 写库防护：限流 + 判重 + 长度上限（2026-09-15 审计 M-4） ----------

def test_parse_vip_rate_limited_per_user(auth_client):
    # 每次调用写 Record+AccessLog 两行：30 次/分钟/用户，防脚本化刷库拖垮 SQLite
    codes = [auth_client.post("/api/parse/vip",
                              json={"url": "https://v.qq.com/x/cover/abc"}).status_code
             for _ in range(31)]
    assert codes[:-1] == [200] * 30
    assert codes[-1] == 429


def test_parse_vip_daily_quota_blocks_farming(auth_client):
    """反例（攻击场景）：登录账号被当作免费解析 API 农场低速率长跑——
    分钟级 30 次限制管得住瞬时频率，管不住全天累计，滚动 24h 第 301 次必须被拒。
    阈值 300 次经 HTTP 循环打太慢，直接预填限流桶（auth_client 登录 admin，id=1）。"""
    from app.services.ratelimit import parse_daily_limiter

    for _ in range(300):
        parse_daily_limiter.allow("parse:1")
    r = auth_client.post("/api/parse/vip", json={"url": "https://v.qq.com/x/cover/abc"})
    assert r.status_code == 429
    assert "每日上限" in r.json()["detail"]


def test_parse_vip_daily_quota_allows_normal_use(auth_client):
    """正例：配额内的正常使用不受影响——预填 299 次 + 本次 = 300，仍在窗口余量内。"""
    from app.services.ratelimit import parse_daily_limiter

    for _ in range(299):
        parse_daily_limiter.allow("parse:1")
    r = auth_client.post("/api/parse/vip", json={"url": "https://v.qq.com/x/cover/abc"})
    assert r.status_code == 200


def test_parse_vip_dedupes_same_url_within_day(auth_client, db):
    # 24h 内同链接复用既有记录：刷新重试/多标签重复提交不再堆重复行
    r1 = auth_client.post("/api/parse/vip", json={"url": "https://v.qq.com/x/cover/abc"})
    r2 = auth_client.post("/api/parse/vip", json={"url": "https://v.qq.com/x/cover/abc"})
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["record"]["id"] == r2.json()["record"]["id"]
    assert db.scalar(select(func.count()).select_from(Record)) == 1


def test_parse_vip_rejects_oversized_url(auth_client):
    # URL 入参上限 2048：超长串只消耗内存与日志空间
    r = auth_client.post("/api/parse/vip",
                         json={"url": "https://v.qq.com/x/cover/abc?pad=" + "a" * 3000})
    assert r.status_code == 422


def _vip_record(db, route_name=None):
    rec = Record(user_id=1, source_type="vip", parse_status="parsed", platform="tencent",
                 source_url="https://v.qq.com/x/cover/abc",
                 video_url="https://v.qq.com/x/cover/abc", route_name=route_name)
    db.add(rec)
    db.commit()
    return rec


def _dns_public(monkeypatch):
    """embed-check 的 SSRF guard 会真实解析线路域名（jx.m3u8.tv 是真实域名，
    本机 DNS/运营商劫持可能把它解析到私网段而被 guard 403）。这里固定解析为
    公网 IP，让测试只依赖 respx mock 的 HEAD 层，与本机网络环境无关。
    注意 mock 的是 _resolve_host 而非 validate_proxy_target：guard 的 IP 判定
    逻辑（_is_forbidden_ip）仍由本用例链路真实覆盖。"""
    async def fake_resolve(host):
        return ["93.184.216.34"]  # SECURITY.md §6 指定的公网测试 IP
    monkeypatch.setattr("app.services.urlguard._resolve_host", fake_resolve)


def test_embed_uses_route_saved_on_record(auth_client, db):
    rec = _vip_record(db, route_name="万能稳定")
    r = auth_client.get(f"/api/records/{rec.id}/embed")
    assert r.status_code == 200
    data = r.json()
    assert data["embed_url"].startswith("https://jx.m3u8.tv/jiexi/?url=")
    assert data["route_name"] == "万能稳定"


def test_embed_falls_back_to_default_when_record_has_no_route(auth_client, db):
    auth_client.put("/api/settings", json={"vip_default_route": "万能稳定"})
    rec = _vip_record(db)  # 历史记录没有线路
    r = auth_client.get(f"/api/records/{rec.id}/embed")
    assert r.status_code == 200
    assert r.json()["route_name"] == "万能稳定"


def test_embed_route_param_overrides_and_persists(auth_client, db):
    rec = _vip_record(db, route_name="万能稳定")
    r = auth_client.get(f"/api/records/{rec.id}/embed", params={"route": "虾米"})
    assert r.status_code == 200
    data = r.json()
    assert data["embed_url"].startswith("https://jx.xmflv.com/?url=")
    assert data["route_name"] == "虾米"
    db.refresh(rec)
    assert rec.route_name == "虾米"  # 切换写回记录，下次播放沿用


def test_embed_rejects_unknown_route(auth_client, db):
    rec = _vip_record(db)
    r = auth_client.get(f"/api/records/{rec.id}/embed", params={"route": "不存在线路"})
    assert r.status_code == 400


@respx.mock
def test_embed_makes_no_head_probe(auth_client, db):
    # embed 必须直接返回，不允许再对线路做同步 HEAD（原 8s 阻塞源）
    rec = _vip_record(db, route_name="万能稳定")
    head = respx.head(host="jx.m3u8.tv").mock(return_value=httpx.Response(200))
    r = auth_client.get(f"/api/records/{rec.id}/embed")
    assert r.status_code == 200
    assert not head.called


@respx.mock
def test_embed_check_deny(auth_client, db, monkeypatch):
    _dns_public(monkeypatch)
    rec = _vip_record(db, route_name="万能稳定")
    respx.head(host="jx.m3u8.tv").mock(
        return_value=httpx.Response(200, headers={"x-frame-options": "SAMEORIGIN"}))
    r = auth_client.get(f"/api/records/{rec.id}/embed-check")
    assert r.status_code == 200
    assert r.json()["embeddable"] is False


@respx.mock
def test_embed_check_allow(auth_client, db, monkeypatch):
    _dns_public(monkeypatch)
    rec = _vip_record(db, route_name="万能稳定")
    respx.head(host="jx.m3u8.tv").mock(return_value=httpx.Response(200))
    r = auth_client.get(f"/api/records/{rec.id}/embed-check")
    assert r.status_code == 200
    assert r.json()["embeddable"] is True
