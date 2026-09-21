import httpx
from starlette.requests import Request
from starlette.responses import StreamingResponse

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
REFERERS = {
    "douyin": "https://www.douyin.com/",
    "kuaishou": "https://www.kuaishou.com/",
    "xiaohongshu": "https://www.xiaohongshu.com/",
    "bilibili": "https://www.bilibili.com/",
}


class ProxyExpiredError(Exception):
    """上游直链已失效或不可达。"""


# 共享连接池：视频拖动进度条会产生高频 Range 请求，复用连接省去反复 TCP/TLS 握手
_shared_client: httpx.AsyncClient | None = None


def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30, read=120),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )
    return _shared_client


async def close_shared_client() -> None:
    """应用关闭时释放连接池（FastAPI lifespan 调用）。"""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None


def build_upstream_headers(platform: str | None, range_header: str | None) -> dict:
    headers = {"User-Agent": USER_AGENT, "Referer": REFERERS.get(platform or "", "")}
    headers = {k: v for k, v in headers.items() if v}
    if range_header:
        headers["Range"] = range_header
    return headers


async def _close(upstream: httpx.Response, client: httpx.AsyncClient | None = None):
    try:
        await upstream.aclose()
    finally:
        if client is not None:
            await client.aclose()


async def stream_response(request: Request, url: str, platform: str | None,
                          transport: httpx.AsyncBaseTransport | None = None) -> StreamingResponse:
    headers = build_upstream_headers(platform, request.headers.get("range"))
    # 传入 transport 的是测试路径：为 mock 传输独立建客户端并由本次请求负责关闭；
    # 生产路径复用共享连接池，只关上游响应，绝不能关池子。
    owns_client = transport is not None
    client = (httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30, read=120),
                                transport=transport)
              if owns_client else get_shared_client())
    try:
        req = client.build_request("GET", url, headers=headers)
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError:
        if owns_client:
            await client.aclose()
        raise ProxyExpiredError("上游直链请求失败") from None
    if upstream.status_code in (403, 404, 410):
        await _close(upstream, client if owns_client else None)
        raise ProxyExpiredError("上游直链已过期")

    async def relay():
        # Starlette 在 body 迭代抛错/客户端断开时不会执行 background 任务，
        # 因此清理必须放在迭代器自身的 finally 中，中断时也能释放连接。
        try:
            async for chunk in upstream.aiter_bytes(64 * 1024):
                yield chunk
        finally:
            await _close(upstream, client if owns_client else None)

    return StreamingResponse(
        relay(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers={k: upstream.headers[k] for k in ("content-length", "content-range", "accept-ranges")
                 if k in upstream.headers},
    )
