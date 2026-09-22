"""videohub VIP 解析线路爬取工具（基于 Scrapling）

数据源：牛导航 VIP 视频解析页 https://www.niudh.cn/tools/vip/
页面 <select id="jiekou"> 里静态列出全部解析线路（名称 + 接口前缀），
无需浏览器渲染，用 Scrapling 的 Fetcher 即可拿到。

用法（在 backend 目录下，用装有 scrapling 的 python 执行）：

    python scripts/scrape_vip_routes.py scrape            # 爬取并打印线路 JSON
    python scripts/scrape_vip_routes.py merge             # 爬取并合并进 videohub.db 的 vip_routes
    python scripts/scrape_vip_routes.py merge --reset     # 用爬取结果整体替换 vip_routes（默认合并去重）
    python scripts/scrape_vip_routes.py merge --from-stdin # 从 stdin 读 JSON 合并（WSL 内无 scrapling 时用：
                                                           #   Windows 爬取 | 管道进 wsl python3 本脚本）

说明：
    vip_routes 存在 settings 表（key='vip_routes'），格式为 [{"name": ..., "prefix": ...}, ...]。
    合并时按 prefix 去重：数据库里已有的线路保持原名原顺序，页面上新出现的线路追加到末尾；
    这样不会打乱用户在管理后台自定义过的线路顺序。
"""

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "videohub.db"
VIP_PAGE_URL = "https://www.niudh.cn/tools/vip/"


def scrape_routes() -> list[dict]:
    """从牛导航 VIP 页面爬取解析线路，返回 [{"name", "prefix"}, ...]"""
    from scrapling.fetchers import Fetcher  # 延迟导入：--from-stdin 模式下无需安装 scrapling

    page = Fetcher.get(VIP_PAGE_URL, stealthy_headers=True)
    options = page.css("#jiekou option")
    if not options:
        sys.exit(f"[x] 未在页面中找到线路列表（#jiekou option），页面结构可能已变化: {VIP_PAGE_URL}")
    routes = []
    for opt in options:
        prefix = (opt.attrib.get("value") or "").strip()
        name = (opt.text or "").strip()
        if prefix and name:
            routes.append({"name": name, "prefix": prefix})
    return routes


def load_db_routes(con: sqlite3.Connection) -> list[dict]:
    row = con.execute("SELECT value FROM settings WHERE key = 'vip_routes'").fetchone()
    if row is None or row["value"] is None:
        return []
    value = row["value"]
    return json.loads(value) if isinstance(value, str) else value


def cmd_scrape() -> None:
    routes = scrape_routes()
    print(json.dumps(routes, ensure_ascii=False, indent=2))
    print(f"\n共爬取到 {len(routes)} 条线路", file=sys.stderr)


def cmd_merge(reset: bool, from_stdin: bool = False) -> None:
    routes = scrape_routes() if not from_stdin else json.load(sys.stdin)
    if reset:
        merged = routes
        added = routes
    else:
        with sqlite3.connect(DB_PATH) as con:
            con.row_factory = sqlite3.Row
            db_routes = load_db_routes(con)
        seen = {r["prefix"] for r in db_routes}
        added = [r for r in routes if r["prefix"] not in seen]
        merged = db_routes + added
    if not merged:
        sys.exit("[x] 合并后线路列表为空，放弃写入")
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO settings (key, value) VALUES ('vip_routes', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(merged, ensure_ascii=False),),
        )
        con.commit()
    print(f"✔ 已写入 vip_routes：共 {len(merged)} 条（新增 {len(added)} 条）")
    for r in merged:
        mark = "+" if r in added else " "
        print(f" {mark} {r['name']:<8} {r['prefix']}")


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "scrape"
    rest = args[1:]
    if cmd == "scrape" and not rest:
        cmd_scrape()
    elif cmd == "merge" and all(a in ("--reset", "--from-stdin") for a in rest) and len(rest) <= 1:
        cmd_merge(reset="--reset" in rest, from_stdin="--from-stdin" in rest)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
