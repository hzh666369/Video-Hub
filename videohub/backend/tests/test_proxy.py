import httpx
import pytest
import respx
from starlette.requests import Request

from app.models import Record, User
from app.services import proxy


def _request_with_range(range_value=None):
    headers = [(b"range", range_value.encode())] if range_value else []
    return Request({"type": "http", "headers": headers})


def test_build_upstream_headers_referer_and_range():
    h = proxy.build_upstream_headers("douyin", "bytes=0-100")
    assert h["Referer"] == "https://www.douyin.com/"
    assert h["Range"] == "bytes=0-100"
    assert "User-Agent" in h
    assert proxy.build_upstream_headers("unknown-platform", None).get("Referer") is None


async def test_stream_passthrough_body_and_headers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["referer"] == "https://www.douyin.com/"
        return httpx.Response(200, content=b"0123456789",
                              headers={"content-type": "video/mp4", "content-length": "10"})

    resp = await proxy.stream_response(_request_with_range(), "https://cdn/v.mp4", "douyin",
                                       transport=httpx.MockTransport(handler))
    body = b"".join([chunk async for chunk in resp.body_iterator])
    assert body == b"0123456789"
    assert resp.media_type == "video/mp4"


async def test_upstream_403_raises_expired():
    handler = lambda request: httpx.Response(403)  # noqa: E731
    with pytest.raises(proxy.ProxyExpiredError):
        await proxy.stream_response(_request_with_range(), "https://cdn/v.mp4", "douyin",
                                    transport=httpx.MockTransport(handler))


async def test_range_forwarded_returns_206():
    handler = lambda request: httpx.Response(206, content=b"zzz",
                                             headers={"content-range": "bytes 0-2/10"})  # noqa: E731
    resp = await proxy.stream_response(_request_with_range("bytes=0-2"), "https://cdn/v.mp4", "douyin",
                                       transport=httpx.MockTransport(handler))
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 0-2/10"


async def test_midstream_abort_closes_upstream_and_client(monkeypatch):
    seen = {}
    real_close = proxy._close

    async def spy_close(client, upstream):
        seen["client"], seen["upstream"] = client, upstream
        await real_close(client, upstream)

    monkeypatch.setattr(proxy, "_close", spy_close)

    async def broken_body():
        yield b"partial"
        raise httpx.RemoteProtocolError("connection lost mid-body")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=broken_body(), headers={"content-type": "video/mp4"})

    resp = await proxy.stream_response(_request_with_range(), "https://cdn/v.mp4", "douyin",
                                       transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.RemoteProtocolError):
        [chunk async for chunk in resp.body_iterator]
    assert seen["client"].is_closed and seen["upstream"].is_closed


def _mk_record(db, user_id, **kw):
    rec = Record(user_id=user_id,
                 source_url=kw.pop("source_url", "https://www.douyin.com/video/1"),
                 platform=kw.pop("platform", "douyin"), **kw)
    db.add(rec)
    db.commit()
    return rec


def test_stream_video_requires_login(client):
    assert client.get("/api/stream/1").status_code == 401


def test_stream_video_not_parsed_returns_400(auth_client, db):
    rec = _mk_record(db, 1, parse_status="link_only", video_url=None)
    r = auth_client.get(f"/api/stream/{rec.id}")
    assert r.status_code == 400
    assert r.json()["detail"] == "该条目尚未解析"


def test_stream_vip_record_rejected(auth_client, db):
    rec = _mk_record(db, 1, source_type="vip", platform="tencent", parse_status="parsed",
                     source_url="https://v.qq.com/x/cover/abc",
                     video_url="https://v.qq.com/x/cover/abc")
    r = auth_client.get(f"/api/stream/{rec.id}")
    assert r.status_code == 400
    assert r.json()["detail"] == "VIP 记录不支持流式代理"


def test_stream_missing_and_foreign_record_404(auth_client, db):
    db.add(User(username="other", password_hash="x"))
    db.commit()
    other = db.query(User).filter_by(username="other").first()
    rec = _mk_record(db, other.id, parse_status="parsed", video_url="https://www.douyin.com/a.mp4")
    r = auth_client.get(f"/api/stream/{rec.id}")
    assert r.status_code == 404
    assert r.json()["detail"] == "记录不存在"
    assert auth_client.get("/api/stream/99999").json()["detail"] == "记录不存在"


@respx.mock
def test_stream_video_expired_upstream_returns_410(auth_client, db):
    url = "https://www.douyin.com/aweme/v1/play/?video_id=abc"
    rec = _mk_record(db, 1, parse_status="parsed", video_url=url)
    respx.get(url).mock(return_value=httpx.Response(403))
    r = auth_client.get(f"/api/stream/{rec.id}")
    assert r.status_code == 410
    assert r.json()["detail"] == "视频直链已过期，请重新解析"


def test_stream_cover_missing_returns_404(auth_client, db):
    rec = _mk_record(db, 1, parse_status="parsed", video_url="https://www.douyin.com/a.mp4")
    r = auth_client.get(f"/api/stream/{rec.id}/cover")
    assert r.status_code == 404
    assert r.json()["detail"] == "无封面"


@respx.mock
def test_stream_cover_expired_upstream_returns_404(auth_client, db):
    url = "https://www.douyin.com/cover/abc.jpg"
    rec = _mk_record(db, 1, parse_status="parsed", video_url="https://www.douyin.com/a.mp4", cover_url=url)
    respx.get(url).mock(return_value=httpx.Response(404))
    r = auth_client.get(f"/api/stream/{rec.id}/cover")
    assert r.status_code == 404
    assert r.json()["detail"] == "封面不可用"
