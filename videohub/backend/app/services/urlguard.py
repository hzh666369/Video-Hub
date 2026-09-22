"""Guard the streaming proxy against SSRF targets.

Records created by the retired 92k pipeline may carry arbitrary
video_url/cover_url values. Before proxying, the target host is resolved and
non-public addresses (loopback / private / link-local / CGNAT / reserved)
are refused — a logged-in record owner must not be able to make the server
fetch internal-network or cloud-metadata URLs.

Notes:
- DNS resolution failures are ALLOWED THROUGH: the proxied request itself
  would fail anyway, and this keeps offline test runs working.
- Remaining (accepted) residual risk: DNS rebinding and cross-protocol
  redirects after the initial hop (the shared pool follows redirects).
"""
import asyncio
import ipaddress
from urllib.parse import urlparse

# Shared pools / carrier-grade NAT, not covered by ip.is_private
_CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")


class ForbiddenUpstreamError(Exception):
    """Proxy target is not a public address."""


def _is_forbidden_ip(ip: ipaddress._BaseAddress) -> bool:
    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified):
        return True
    return ip.version == 4 and ip in _CGNAT_NET


async def _resolve_host(host: str) -> list[str]:
    """Resolve a hostname to addresses without blocking the event loop."""
    try:
        infos = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, None), timeout=3)
    except (OSError, asyncio.TimeoutError):
        return []
    return [info[4][0] for info in infos]


async def validate_proxy_target(url: str) -> None:
    """Raise ForbiddenUpstreamError if the URL points at a non-public target."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ForbiddenUpstreamError("仅支持 http/https 直链")
    host = parts.hostname.strip().rstrip(".").lower()

    try:
        ip = ipaddress.ip_address(host)  # IP literal (v4/v6) → judge directly
    except ValueError:
        ip = None
    if ip is not None:
        if _is_forbidden_ip(ip):
            raise ForbiddenUpstreamError("直链指向受限地址") from None
        return

    # Domain: refuse if ANY resolved address is non-public (a rebinded or
    # dual-homed host mixing public/private records is treated as hostile).
    for addr in await _resolve_host(host):
        try:
            if _is_forbidden_ip(ipaddress.ip_address(addr)):
                raise ForbiddenUpstreamError("直链域名解析到受限地址") from None
        except ValueError:
            continue  # scoped v6 like fe80::1%eth0 fails parse; scope ids are link-local anyway
