"""Extract the real client IP behind the Cloudflare tunnel.

Deployment (docker-compose) funnels ALL public traffic through the cloudflared
container, so request.client.host is always cloudflared's Docker-internal
address — every visitor would share one rate-limit bucket and one log IP.
cloudflared (both named and quick tunnels) overwrites CF-Connecting-IP with
the real visitor address, which cannot be forged through Cloudflare.

Trusting this header is safe ONLY because the app port is never exposed
directly (compose binds 127.0.0.1:8000). If the app is ever reachable
without a trusted proxy in front, header-based IP detection must be
revisited (e.g. nginx fronts also need their own header policy here).
"""
import ipaddress

from starlette.requests import Request


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def get_client_ip(request: Request) -> str:
    """Real visitor IP: CF-Connecting-IP first, transport peer as fallback."""
    ip = _valid_ip(request.headers.get("cf-connecting-ip", ""))
    if ip:
        return ip
    return request.client.host if request.client else "unknown"


def _bucket_key(ip: str) -> str:
    """限流桶键：IPv4 原样；IPv6 收敛到 /64 前缀；非 IP 字面量原样返回。"""
    try:
        obj = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if obj.version == 6:
        return str(ipaddress.ip_network(f"{obj}/64", strict=False))
    return ip


def rate_limit_key(request: Request) -> str:
    """限流分桶标识：IPv6 收敛到 /64 前缀，IPv4 与回退地址原样。

    与 get_client_ip() 的分工：日志/溯源保留完整地址，只有防爆破/防刷的
    计数桶收敛——IPv6 隐私扩展（RFC 4941）默认在单个 /64 内随机化接口
    标识符，完整地址作 key 时攻击者旋转地址即可让每个请求都命中新桶、
    从零计数，IP 维限流整体失效（2026-09-15 审计 H-1）。Cloudflare 会
    透传访客真实 IPv6 地址，该攻击向量经隧道合法可达，无需绕过网络层。
    """
    ip = _valid_ip(request.headers.get("cf-connecting-ip", ""))
    if not ip:
        ip = request.client.host if request.client else "unknown"
    return _bucket_key(ip)
