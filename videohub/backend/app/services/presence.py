"""在线心跳表（实时在线口径）：单进程内存实现。

user_id → 最后一次心跳的 monotonic 时间戳。服务重启后清零，1-2 分钟内各在线
客户端心跳回来即自动恢复——在线人数本来就是易失指标，不落库、不写日志。
多进程部署时本表需换成共享存储（当前部署为单进程 FastAPI，内存即为事实来源）。
"""
import threading
import time

_lock = threading.Lock()
_last_seen: dict[int, float] = {}


def beat(user_id: int) -> None:
    """记录一次心跳（谁调用谁负责先过认证与限流）。"""
    with _lock:
        _last_seen[user_id] = time.monotonic()


def online_count(window_seconds: float) -> int:
    """窗口内有心跳的去重用户数；顺手惰性回收过期条目，防表随用户数无限增长。"""
    cutoff = time.monotonic() - window_seconds
    with _lock:
        for uid in [uid for uid, ts in _last_seen.items() if ts < cutoff]:
            del _last_seen[uid]
        return len(_last_seen)


def reset() -> None:
    """测试夹具用：清空心跳表，避免用例间在线数互相污染。"""
    with _lock:
        _last_seen.clear()
