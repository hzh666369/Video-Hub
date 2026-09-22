"""内存滑动窗口限流：单进程部署下的轻量实现，用于注册防刷。

两道闸门配合：
- attempt：限制注册接口的调用频率，防验证码暴力破解；
- success：限制成功注册频率与总数，防批量建号。
服务重启后计数清零，与验证码内存存储的生命周期一致。
"""
import threading
import time
from collections import deque

# 全表清扫节律：桶内过期命中只在该 key 再次被触碰时清理，从不活跃的 key
# 会永久残留（公网独立 IP/前缀扫描下 _hits 只增不减，缓慢耗尽内存），
# 故按固定间隔全表回收一次（2026-09-15 审计 H-1）
_SWEEP_INTERVAL = 60.0


class RateLimiter:
    def __init__(self, *, window_seconds: int, max_hits: int, min_interval: int = 0):
        self.window = window_seconds
        self.max_hits = max_hits
        self.min_interval = min_interval
        # 普通 dict + 显式创建：defaultdict 会让 check() 这类只读探测也永久留下空桶
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def _prune(self, hits: deque[float], now: float) -> None:
        while hits and hits[0] <= now - self.window:
            hits.popleft()

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < _SWEEP_INTERVAL:
            return
        self._last_sweep = now
        for key in list(self._hits):
            hits = self._hits[key]
            self._prune(hits, now)
            if not hits:
                del self._hits[key]

    def allow(self, key: str) -> float:
        """放行返回 0 并记录一次命中；否则返回还需等待的秒数（不记录）。"""
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            hits = self._hits.get(key)
            if hits is None:
                hits = self._hits[key] = deque()
            self._prune(hits, now)
            if hits and self.min_interval and now - hits[-1] < self.min_interval:
                return self.min_interval - (now - hits[-1])
            if len(hits) >= self.max_hits:
                return hits[0] + self.window - now
            hits.append(now)
            return 0.0

    def check(self, key: str) -> float:
        """只查询不记录：返回 0 表示放行，否则为还需等待的秒数。

        不创建桶条目——login 每次请求（含成功登录）都先 check 一次，
        若像 defaultdict 那样访问即建键，每个唯一访客都会永久留下空桶。
        """
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                return 0.0
            self._prune(hits, now)
            if not hits:
                del self._hits[key]
                return 0.0
            if len(hits) >= self.max_hits:
                return hits[0] + self.window - now
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._last_sweep = 0.0


# 注册接口调用：同一 IP 10 分钟内最多 10 次（防验证码爆破）
register_attempt_limiter = RateLimiter(window_seconds=600, max_hits=10)
# 成功注册：同一 IP 两次至少间隔 60 秒，且 1 小时内最多 3 个账号（防批量建号）
register_success_limiter = RateLimiter(window_seconds=3600, max_hits=3, min_interval=60)
# 用户名可用性查询：同一 IP 每分钟最多 30 次（防用户名枚举）
username_check_limiter = RateLimiter(window_seconds=60, max_hits=30)
# 登录失败：同一 IP 10 分钟内最多 10 次失败尝试（防密码爆破，成功登录不计入）
login_fail_limiter = RateLimiter(window_seconds=600, max_hits=10)
# 验证码签发：同一 IP 每分钟最多 30 张（无需登录，每次都要 Pillow 渲染，防 CPU/内存刷爆）
captcha_limiter = RateLimiter(window_seconds=60, max_hits=30)
# 访问计数上报：同一用户每分钟最多 30 次（前端仅进入解析页上报一次；每次调用写库，防刷库拖垮 SQLite）
visit_limiter = RateLimiter(window_seconds=60, max_hits=30)
# 账户自助注销：同一用户每小时最多 5 次密码错误尝试（破坏性操作，防会话被盗后暴力试密码删库跑路）
account_delete_limiter = RateLimiter(window_seconds=3600, max_hits=5)
# 修改密码原密码核验：同一用户每小时最多 5 次失败尝试（会话被盗后在线爆破原密码的唯一闸门；
# 与 account_delete_limiter 同口径——按用户分桶、只统计失败，本人持正确密码永不计数、无自我锁死 DoS，
# 2026-09-19 安全审计 run-1 F-1 修复：登录三级限流、注销、TOTP 关闭都有闸门，改密是全站唯一零限流的密码核验点）
password_verify_limiter = RateLimiter(window_seconds=3600, max_hits=5)
# 健康探针：同一 IP 每分钟最多 30 次（无认证端点，前端状态灯轮询 + Docker HEALTHCHECK 共用，
# 正常用量 2 次/分钟，防被刷成免费探测口）
health_limiter = RateLimiter(window_seconds=60, max_hits=30)
# 管理员数据看板：同一用户每分钟最多 60 次（前端 60s 轮询，正常用量 1 次/分钟；聚合查询略重，防异常循环刷库）
dashboard_limiter = RateLimiter(window_seconds=60, max_hits=60)
# VIP 解析：同一用户每分钟最多 30 次（每次调用写 Record+AccessLog 两行，公开注册场景下
# 防登录用户脚本化刷库拖垮 SQLite 单写者；与 visit_limiter 同口径，2026-09-15 审计 M-4）
parse_limiter = RateLimiter(window_seconds=60, max_hits=30)
# VIP 解析每日配额（滚动 24h 窗口）：同一用户 300 次/天。分钟级 parse_limiter 只能封
# 瞬时频率，管不住低速率长跑——30 次/分钟的理论日上限高达 4.3 万次，登录账号会被
# 当作免费解析 API 农场刷（每行 Record+AccessLog 写库，VIP 线路 iframe 消耗第三方
# 配额）。300 次对正常追剧用户（新链接数十到百余条/天）余量充足；脚本化调用约
# 10 分钟即烧完全天配额（2026-09-18 爬虫视角安全测试报告建议 5）
parse_daily_limiter = RateLimiter(window_seconds=86400, max_hits=300)
# 在线心跳：同一用户每分钟最多 12 次。分母要按「标签页」而不是「用户」算——前端
# 每个标签页各跑一个 30s 定时器（正常 2 次/分钟/标签页），6 个标签页合计 12 次/分钟，
# 取 12 才不会被多标签正常使用误伤（早期取 4 是漏算了这份乘数）。本端点只写内存
# presence 表、不落库，阈值只作异常客户端的兜底闸门（2026-09-15 实时在线功能）
heartbeat_limiter = RateLimiter(window_seconds=60, max_hits=12)
# 登录失败（账号维度）：同一用户名 10 分钟内最多 20 次失败，跨 IP 汇总——IP 维限流
# （10 次/10min/IP）管不住多 /64 或代理池对单一账号的分布式爆破；阈值取 20 高于
# IP 维的 10，正常用户极少连续失败 20 次。
# 命中后**不是硬拒**：login() 改为要求通过人机验证（S6）才放行到密码校验，所以误锁
# 代价是「过一次验证码」而非「等 10 分钟」——硬拒等于让任意第三方靠凑失败数把受害者
# 锁在门外（定向账号锁死 DoS，2026-09-15 审计 M-2 修复）
login_user_limiter = RateLimiter(window_seconds=600, max_hits=20)
# 登录失败（账号维度第三级，2026-09-18 安全评估"未见账户锁定"修复）：同一用户名
# 10 分钟内失败 50 次 → 临时锁定该账户约 10 分钟（时间到自动解锁）。阈值 50 远高于
# 第二级的 20：想持续锁死一个账户，攻击者每个窗口都必须先逐次通过已加固的图形验证
# 码（S6）再错 50 次密码，"免费锁死任意账号"的 DoS 成本被抬到不划算；正常用户即使
# 手滑也不可能连错 50 次。与红线 3.2 的兼容性：解锁通道 = 等待窗口滑出，本人正确
# 密码 + 验证码在解锁后立即可用
login_lock_limiter = RateLimiter(window_seconds=600, max_hits=50)
# TOTP 两步验证管理端点（setup/enable/disable 共用）：同一用户每分钟最多 10 次。
# setup 每次都写 users 行，且返回可入号的 secret，防脚本刷
totp_limiter = RateLimiter(window_seconds=60, max_hits=10)
