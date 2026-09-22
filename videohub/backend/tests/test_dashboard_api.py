"""管理员数据看板聚合端点：认证/授权/限流/数据口径回归。"""

from datetime import datetime, timedelta

from app.models import AccessLog, Record, Setting


def _purge_api_login_logs(db):
    """清掉 API 登录/注册副作用写入的 AccessLog（auth.py 的 login/register 真实写日志）。

    auth_client 夹具登录 admin 必留一条 login 日志；造数类用例在手动造数前调用，
    使断言口径只覆盖用例自己造的数，不受夹具副作用污染（真实-本地时间戳还会
    破坏 recent 排序的确定性）。
    """
    db.query(AccessLog).filter(AccessLog.action.in_(("login", "register"))).delete()
    db.commit()


# ---------- 认证 / 授权 / 限流 ----------

def test_dashboard_requires_admin(client):
    assert client.get("/api/admin/dashboard").status_code == 401
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    # admin 通过，说明 401 来自未登录而非路由缺失
    assert client.get("/api/admin/dashboard").status_code == 200


def test_dashboard_forbids_normal_user(client):
    # 建用户是管理端接口（require_admin），先登 admin 再造 alice
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    client.post("/api/users", json={"username": "alice", "password": "pw123456"})
    client.post("/api/auth/login", json={"username": "alice", "password": "pw123456"})
    assert client.get("/api/admin/dashboard").status_code == 403


def test_dashboard_rate_limited(auth_client):
    # 60 次/分/用户：前 60 次 200，第 61 次 429（conftest 已登记 reset，测试间不污染）
    for _ in range(60):
        assert auth_client.get("/api/admin/dashboard").status_code == 200
    assert auth_client.get("/api/admin/dashboard").status_code == 429


# ---------- 空库结构 ----------

def test_dashboard_empty_database_shape(client, db, auth_client):
    _purge_api_login_logs(db)  # 夹具的 admin 登录也算访问类，清掉才是真空库
    data = auth_client.get("/api/admin/dashboard").json()
    assert set(data) == {"generated_at", "online_users", "kpis", "trend",
                         "platforms", "top_users", "recent", "system"}
    k = data["kpis"]
    # 空库下只有 admin 一个用户；计数类全 0
    assert set(k) == {"today_visits", "yesterday_visits", "today_parses", "yesterday_parses",
                      "total_users", "week_new_users", "total_parses", "total_records",
                      "total_visits"}
    assert k["total_users"] == 1
    assert k["week_new_users"] == 1  # admin 是夹具启动时刚播种的，created_at 在 7 天内
    for key in ("today_visits", "yesterday_visits", "today_parses",
                "yesterday_parses", "total_parses", "total_records", "total_visits"):
        assert k[key] == 0, key
    assert data["online_users"] == 0
    assert len(data["trend"]["days"]) == 90
    assert len(data["trend"]["visits"]) == 90 and len(data["trend"]["parses"]) == 90
    assert all(v == 0 for v in data["trend"]["visits"] + data["trend"]["parses"])
    assert data["platforms"] == [] and data["top_users"] == [] and data["recent"] == []
    s = data["system"]
    assert set(s) == {"db_latency_ms", "uptime_minutes", "events_per_min", "today_events",
                      "week_parses", "captions", "db_size_mb", "via_tunnel"}
    assert s["db_latency_ms"] >= 0
    assert isinstance(s["uptime_minutes"], int) and s["uptime_minutes"] >= 0
    assert s["events_per_min"] == 0 and s["today_events"] == 0 and s["week_parses"] == 0
    assert s["captions"] == 0
    assert s["via_tunnel"] is False  # TestClient 请求不带 Cloudflare 头
    assert isinstance(s["db_size_mb"], (int, float)) and s["db_size_mb"] > 0


# ---------- 数据口径 ----------

def _at(days_ago: int, hour: int = 12) -> datetime:
    """构造 days_ago 天前 hour 点的本地时间（AccessLog.created_at 存本地时间）。"""
    d = datetime.now() - timedelta(days=days_ago)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


def _add_log(db, *, username, action, days_ago=0, user_id=None, detail=None):
    db.add(AccessLog(user_id=user_id, username=username, action=action,
                     detail=detail, ip="8.8.8.8", created_at=_at(days_ago)))


def _add_record(db, *, user_id, platform):
    db.add(Record(user_id=user_id, source_type="vip", platform=platform,
                  source_url="https://example.com/watch/1", title="测试片"))


def test_dashboard_kpis_values(client, db, auth_client):
    # 造数：admin(id=1) + alice(id=2)；auth_client 已登 admin，直接走管理端 API 建 alice
    auth_client.post("/api/users", json={"username": "alice", "password": "pw123456"})
    _purge_api_login_logs(db)
    _add_log(db, username="admin", action="visit", days_ago=0)
    _add_log(db, username="admin", action="visit", days_ago=0)
    _add_log(db, username="alice", action="login", days_ago=0, user_id=2)
    _add_log(db, username="admin", action="visit", days_ago=1)
    _add_log(db, username="alice", action="visit", days_ago=1, user_id=2)
    _add_log(db, username="admin", action="visit", days_ago=3)  # 昨天(1)与今天(0)之外不计
    _add_log(db, username="alice", action="parse", days_ago=0, user_id=2, detail="三体")
    _add_log(db, username="admin", action="parse", days_ago=1)
    _add_log(db, username="admin", action="parse", days_ago=1)
    # 大前天的一次解析操作：无对应 Record —— 用于区分「操作数」与「记录存量」两个口径
    _add_log(db, username="admin", action="parse", days_ago=2)
    db.add(Setting(key="visit_total", value=88412))  # 旧计数器已废弃，接口不再读取
    _add_record(db, user_id=2, platform="bilibili")
    _add_record(db, user_id=2, platform="bilibili")
    _add_record(db, user_id=1, platform="tencent")
    db.commit()

    k = auth_client.get("/api/admin/dashboard").json()["kpis"]
    assert k["today_visits"] == 3        # 2 visit + 1 login（登录也算访问类）
    assert k["yesterday_visits"] == 2
    assert k["today_parses"] == 1
    assert k["yesterday_parses"] == 2
    assert k["total_users"] == 2         # admin + alice
    assert k["week_new_users"] == 2      # 两者都是刚创建（7 天内）
    # 累计解析 = 解析操作总数（AccessLog 口径，4 次操作；删除记录不影响）
    assert k["total_parses"] == 4
    # 解析记录存量 = Record 当前行数（3 条；与操作数是两个口径）
    assert k["total_records"] == 3
    # 累计访问 = 访问类活动总数（AccessLog 口径 5 visit + 1 login；旧计数器 88412 被忽略）
    assert k["total_visits"] == 6


def test_dashboard_trend_and_recent(client, db, auth_client):
    auth_client.post("/api/users", json={"username": "alice", "password": "pw123456"})
    _purge_api_login_logs(db)
    _add_log(db, username="admin", action="visit", days_ago=0)
    _add_log(db, username="admin", action="visit", days_ago=0)
    _add_log(db, username="alice", action="visit", days_ago=1, user_id=2)
    _add_log(db, username="alice", action="parse", days_ago=2, user_id=2, detail="狂飙")
    _add_log(db, username="alice", action="parse", days_ago=2, user_id=2, detail="流浪地球2")
    _add_log(db, username="alice", action="register", days_ago=29, user_id=2)
    db.commit()

    data = auth_client.get("/api/admin/dashboard").json()
    trend = data["trend"]
    assert len(trend["days"]) == 90
    assert trend["days"][-1] == datetime.now().strftime("%m-%d")   # 最后一天是今天
    assert trend["visits"][-1] == 2 and trend["visits"][-2] == 1   # 今天 2 / 昨天 1
    assert trend["parses"][-3] == 2                                 # 前天 2 次解析
    assert trend["visits"][-30] == 1                                # 29 天前(第 61 天)注册算访问类
    assert data["recent"][0]["action"] in ("visit", "parse", "register")
    assert len(data["recent"]) == 6
    assert all(set(item) == {"id", "user_id", "username", "action", "detail", "ip", "created_at"}
               for item in data["recent"])


def test_dashboard_trend_sums_visit_class_actions(client, db, auth_client):
    """回归（2026-09-15）：趋势图访问量必须把 visit/login/register 三类动作求和。

    旧实现按 (日期, 动作) 分组后直接赋值 visits_map[day]，同一天出现多类访问
    动作时后一类覆盖前一类，访问量被低估（真实库当天 38 条活动只显示 30）。
    """
    _purge_api_login_logs(db)
    _add_log(db, username="admin", action="visit", days_ago=0)
    _add_log(db, username="admin", action="visit", days_ago=0)
    _add_log(db, username="admin", action="login", days_ago=0, user_id=1)
    _add_log(db, username="admin", action="register", days_ago=1, user_id=1)
    _add_log(db, username="admin", action="parse", days_ago=1, user_id=1)
    db.commit()

    trend = auth_client.get("/api/admin/dashboard").json()["trend"]
    assert trend["visits"][-1] == 3        # 今天 = 2 visit + 1 login 之和
    assert trend["visits"][-2] == 1        # 昨天 = 1 register
    assert trend["parses"][-1] == 0 and trend["parses"][-2] == 1


def test_dashboard_platforms_top_and_other_merge(client, db, auth_client):
    platforms = ["bilibili", "bilibili", "bilibili", "tencent", "youku", "iqiyi", "mgtv",
                 "douyin", "kuaishou", "xiaohongshu", "unknown"]
    for p in platforms:
        _add_record(db, user_id=1, platform=p)
    db.commit()

    data = auth_client.get("/api/admin/dashboard").json()["platforms"]
    # 端点直接按前端展示口径返回：降序取前 5，同量按平台名字典序（order_by(count desc, platform)）；
    # bilibili(3) + douyin/iqiyi/kuaishou/mgtv(各1)；其余 tencent/unknown/xiaohongshu/youku 合并 other(4)
    assert [item["platform"] for item in data] == ["bilibili", "douyin", "iqiyi", "kuaishou", "mgtv", "other"]
    assert data[0]["count"] == 3 and data[-1]["count"] == 4
    # 全部为刚插入的记录 → 今天有新增、昨天为 0 → 按约定「从无到有」一律 +100
    assert all(item["delta_pct"] == 100.0 for item in data)


def _add_dated_record(db, *, user_id, platform, days_ago):
    db.add(Record(user_id=user_id, source_type="vip", platform=platform,
                  source_url=f"https://example.com/w/{platform}-{days_ago}",
                  title="测试片", created_at=_at(days_ago)))


def test_dashboard_platforms_other_delta_recomputed_from_counts(client, db, auth_client):
    """回归（2026-09-15）：合并段 other 的涨跌必须用「窗口计数求和后重算」。

    旧实现由前端把各段百分比直接相加，数学上不成立。本例：合并段含 douyin
    （今 1 / 昨 1 → +0%）与 kuaishou（今 2 / 昨 0 → +100%），合计今 3 / 昨 1，
    正确合并涨幅 +200%；旧「百分比相加」会错算成 +100%。
    """
    # 五个大平台各 3 条（全在昨天）占满前五；douyin/kuaishou 各 2 条落入合并段
    for p in ("youku", "mgtv", "tencent", "bilibili", "iqiyi"):
        for _ in range(3):
            _add_dated_record(db, user_id=1, platform=p, days_ago=1)
    _add_dated_record(db, user_id=1, platform="douyin", days_ago=0)    # 今 1
    _add_dated_record(db, user_id=1, platform="douyin", days_ago=1)    # 昨 1 → +0%
    _add_dated_record(db, user_id=1, platform="kuaishou", days_ago=0)  # 今 2
    _add_dated_record(db, user_id=1, platform="kuaishou", days_ago=0)  # 昨 0 → +100%
    db.commit()

    rows = {r["platform"]: r for r in auth_client.get("/api/admin/dashboard").json()["platforms"]}
    assert set(rows) == {"bilibili", "iqiyi", "mgtv", "tencent", "youku", "other"}
    assert rows["youku"]["count"] == 3 and rows["youku"]["delta_pct"] == -100.0  # 今 0 / 昨 3
    assert rows["other"]["count"] == 4               # douyin 2 + kuaishou 2
    assert rows["other"]["delta_pct"] == 200.0       # 今 3 / 昨 1（相加百分比会错算成 100）


def test_dashboard_platform_delta_pct(client, db, auth_client):
    """平台涨跌口径：今日新增记录 vs 昨日新增记录。"""
    _add_record(db, user_id=1, platform="bilibili")
    _add_record(db, user_id=1, platform="bilibili")
    db.add(Record(user_id=1, source_type="vip", platform="bilibili",
                  source_url="https://example.com/w/2", title="昨日片", created_at=_at(1)))
    db.add(Record(user_id=1, source_type="vip", platform="tencent",
                  source_url="https://example.com/w/3", title="昨日片", created_at=_at(1)))
    db.commit()

    rows = {r["platform"]: r for r in auth_client.get("/api/admin/dashboard").json()["platforms"]}
    assert rows["bilibili"]["count"] == 3 and rows["bilibili"]["delta_pct"] == 100.0   # 今 2 / 昨 1
    assert rows["tencent"]["count"] == 1 and rows["tencent"]["delta_pct"] == -100.0    # 今 0 / 昨 1


def test_dashboard_top_users_ranking(client, db, auth_client):
    auth_client.post("/api/users", json={"username": "alice", "password": "pw123456"})
    auth_client.post("/api/users", json={"username": "bob", "password": "pw123456"})
    for _ in range(3):
        _add_log(db, username="alice", action="parse", days_ago=0, user_id=2)
    for _ in range(2):
        _add_log(db, username="bob", action="parse", days_ago=1, user_id=3)
    _add_log(db, username="admin", action="parse", days_ago=1, user_id=1)
    db.commit()

    top = auth_client.get("/api/admin/dashboard").json()["top_users"]
    # delta_pct：alice 全在今日（昨日 0 → 按约定「从无到有」+100）；bob / admin 全在昨日（→ -100%）
    assert top == [{"user_id": 2, "username": "alice", "parse_count": 3, "delta_pct": 100.0},
                   {"user_id": 3, "username": "bob", "parse_count": 2, "delta_pct": -100.0},
                   {"user_id": 1, "username": "admin", "parse_count": 1, "delta_pct": -100.0}]


def test_dashboard_online_users_and_system_counters(client, db, auth_client):
    """在线人数为心跳口径（AccessLog 活动不再计入，见 test_heartbeat_api.py）；
    系统计数器为真实统计。"""
    auth_client.post("/api/users", json={"username": "alice", "password": "pw123456"})
    _purge_api_login_logs(db)
    now = datetime.now()
    recent = now - timedelta(minutes=5)
    db.add(AccessLog(user_id=1, username="admin", action="visit", ip="8.8.8.8", created_at=recent))
    db.add(AccessLog(user_id=2, username="alice", action="visit", ip="8.8.8.8", created_at=recent))
    db.add(AccessLog(user_id=None, username="anonymous", action="visit", ip="8.8.8.8", created_at=recent))
    db.add(AccessLog(user_id=2, username="alice", action="parse", ip="8.8.8.8",
                     detail="bilibili | https://example.com/w/1", created_at=_at(5)))
    db.commit()

    data = auth_client.get("/api/admin/dashboard").json()
    # 2026-09-15 起在线人数只看 presence 心跳表：AccessLog 再活跃、只要没打心跳就是 0
    assert data["online_users"] == 0
    s = data["system"]
    assert s["events_per_min"] == 0      # 事件都在 5 分钟前，60 秒窗口为空
    assert s["today_events"] == 3        # 今天 3 条 visit（5 天前的解析不计）
    assert s["week_parses"] == 1         # 7 天窗口含那条解析
    assert s["captions"] == 0


def test_dashboard_events_per_min_whitelists_known_actions(client, db, auth_client):
    """回归（2026-09-15）：事件速率只统计 visit/login/register/parse 四类动作。

    旧实现不过滤动作类型，未来新增动作（如心跳/导出）会静默混入「事件速率」，
    与 DashStatus 面板注释承诺的口径（仅四类动作）不符。
    """
    _purge_api_login_logs(db)
    now = datetime.now()
    db.add(AccessLog(user_id=1, username="admin", action="visit", ip="8.8.8.8", created_at=now))
    db.add(AccessLog(user_id=1, username="admin", action="parse", ip="8.8.8.8", created_at=now))
    # 未知/未来动作：落在 60 秒窗口内也不计入事件速率与今日事件
    db.add(AccessLog(user_id=1, username="admin", action="heartbeat", ip="8.8.8.8", created_at=now))
    db.commit()

    s = auth_client.get("/api/admin/dashboard").json()["system"]
    assert s["events_per_min"] == 2      # visit + parse，heartbeat 不计
    assert s["today_events"] == 2        # today_events 同为四类白名单
