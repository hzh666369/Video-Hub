from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


# check_same_thread 与 PRAGMA 均为 SQLite 专属，换其他数据库（VIDEOHUB_DB_URL）时会直接报错
_is_sqlite = settings.db_url.startswith("sqlite")
engine = create_engine(settings.db_url, connect_args={"check_same_thread": False} if _is_sqlite else {})

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        # WAL 允许读写并行；busy_timeout 让写锁竞争时等待而非直接报 database is locked；
        # synchronous=NORMAL 是 WAL 的标准搭配——断电最多丢最后一次 checkpoint 后的事务、
        # 不损库，每次提交少 1-2 次 fsync，写吞吐显著高于默认 FULL（2026-09-15 审计 M-13）
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
