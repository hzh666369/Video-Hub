from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting

DEFAULT_VIP_ROUTES: list[dict] = [
    # 顺序即无 vip_default_route 时的回退顺序。2026-09-08 实测（腾讯视频同一链接，
    # 首帧耗时）：线路1(.cc，Cloudflare 多线 CDN 入口) ~20s 显著快于 虾米(.com，单机
    # 84.32.44.11 直连) ~118s，故线路1排首位；其余顺序不变，播放页可随时切换线路。
    {"name": "线路1", "prefix": "https://jx.xmflv.cc/?url="},
    {"name": "虾米", "prefix": "https://jx.xmflv.com/?url="},
    {"name": "万能稳定", "prefix": "https://jx.m3u8.tv/jiexi/?url="},
    # 以下 4 条爬取自 https://www.niudh.cn/tools/vip/（牛导航），可用
    # scripts/scrape_vip_routes.py scrape 随时重新爬取
    {"name": "线路2", "prefix": "https://z1.m1907.top/?jx="},
    {"name": "线路3", "prefix": "https://jx.77flv.cc/?url="},
    {"name": "线路4", "prefix": "https://jx.playerjy.com/?url="},
    {"name": "线路5", "prefix": "https://jx.xymp4.cc/?url="},
]


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    return row.value if row is not None else default


def is_https_prefix(prefix: object) -> bool:
    """线路 prefix 仅允许 https:// 开头。

    prefix 会拼进 embed_url 绑到播放页的 <iframe :src>：javascript: 等协议
    会以站点身份执行脚本（存储型 XSS）；http:// 在 https 站点下也会被浏览器
    混合内容策略拦截。scheme 不区分大小写，故统一小写后判定。
    """
    return isinstance(prefix, str) and prefix.strip().lower().startswith("https://")


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()


def get_vip_routes(db: Session) -> list[dict]:
    routes = get_setting(db, "vip_routes")
    if routes is None:
        set_setting(db, "vip_routes", DEFAULT_VIP_ROUTES)
        routes = DEFAULT_VIP_ROUTES
    return routes
