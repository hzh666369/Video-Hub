import re
from typing import NamedTuple
from urllib.parse import urlparse

# 域名按主机名精确（或子域）匹配，避免平台名出现在 query/fragment 里被误判（SSRF 面）
SHORT_PLATFORMS: dict[str, tuple[str, ...]] = {
    "douyin": ("douyin.com",),
    "kuaishou": ("kuaishou.com",),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
}

VIP_PLATFORMS: dict[str, tuple[str, ...]] = {
    "bilibili": ("bilibili.com", "b23.tv"),
    "tencent": ("qq.com",),
    "youku": ("youku.com",),
    "iqiyi": ("iqiyi.com",),
    "mgtv": ("mgtv.com",),
}

_HOME_HINT = re.compile(r"/user/")


class DetectResult(NamedTuple):
    kind: str
    platform: str | None
    is_homepage: bool


def _hostname(url: str) -> str:
    try:
        parts = urlparse(url)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https"):
        return ""
    return (parts.hostname or "").lower().rstrip(".")


def detect(url: str) -> DetectResult:
    host = _hostname(url)
    if not host:
        return DetectResult("unknown", None, False)
    for kind, table in (("short", SHORT_PLATFORMS), ("vip", VIP_PLATFORMS)):
        for platform, domains in table.items():
            if any(host == d or host.endswith("." + d) for d in domains):
                homepage = kind == "short" and bool(_HOME_HINT.search(url))
                return DetectResult(kind, platform, homepage)
    return DetectResult("unknown", None, False)
