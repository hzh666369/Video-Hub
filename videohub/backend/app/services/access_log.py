import logging
import os
import threading
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import AccessLog, User

logger = logging.getLogger("videohub.access")

# 日志目录：backend/logs，可用环境变量 VIDEOHUB_LOG_DIR 覆盖
_env_log_dir = os.environ.get("VIDEOHUB_LOG_DIR", "").strip()
LOG_DIR = Path(_env_log_dir) if _env_log_dir else Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 每次写日志都持有锁 + 追加写整行，避免多线程交错写坏一行
_file_lock = threading.Lock()

# 各动作在日志文件里的展示名
ACTION_LABELS = {"visit": "页面访问", "login": "登录", "register": "注册", "parse": "解析视频"}


def record_access(db: Session, user: User, action: str, detail: str | None = None,
                  ip: str | None = None, commit: bool = True) -> None:
    """写一条访问日志：入库 + 本地文件。日志失败不影响主流程。"""
    username = user.username if user is not None else "anonymous"
    try:
        row = AccessLog(user_id=getattr(user, "id", None), username=username,
                        action=action, detail=detail, ip=ip)
        # SQLite 的 CURRENT_TIMESTAMP 是 UTC，这里显式写本地时间，管理端展示不差时区
        row.created_at = datetime.now()
        db.add(row)
        if commit:
            db.commit()
    except Exception:  # noqa: BLE001 — 日志是旁路，绝不阻塞主流程
        db.rollback()
        logger.exception("访问日志入库失败 user=%s action=%s", username, action)
    try:
        _write_file_line(username, action, detail, ip)
    except Exception:  # noqa: BLE001
        logger.exception("访问日志写文件失败 user=%s action=%s", username, action)


def _sanitize_log_field(value: str | None) -> str:
    """Strip CR/LF so user-controlled fields (e.g. parsed URLs) cannot forge extra log lines."""
    return (value or "-").replace("\r", " ").replace("\n", " ")


def _write_file_line(username: str, action: str, detail: str | None, ip: str | None) -> None:
    now = datetime.now()
    line = "{ts} | {user:<16} | {action} | {detail} | ip={ip}\n".format(
        ts=now.strftime("%Y-%m-%d %H:%M:%S"),
        user=_sanitize_log_field(username),
        action=ACTION_LABELS.get(action, action),
        detail=_sanitize_log_field(detail),
        ip=_sanitize_log_field(ip),
    )
    path = os.path.join(str(LOG_DIR), f"access_{now.strftime('%Y-%m-%d')}.log")
    with _file_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def today_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time())
