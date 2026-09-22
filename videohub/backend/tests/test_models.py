from sqlalchemy import select

from app.models import Caption, Record, Setting, User


def test_record_with_caption_roundtrip(db):
    u = User(username="u1", password_hash="x")
    db.add(u)
    db.flush()
    rec = Record(user_id=u.id, source_type="single", parse_status="parsed",
                 platform="douyin", source_url="https://www.douyin.com/video/1",
                 title="T", video_url="https://cdn/v.mp4", image_atlas=[{"imageSrc": "a"}])
    db.add(rec)
    db.flush()
    db.add(Caption(record_id=rec.id, text_content="文案", srt_content="1\n00:00:00,000 --> 00:00:01,000\n文案",
                   formatted_text="格式化", duration_minutes=1))
    db.commit()

    got = db.scalar(select(Record).where(Record.id == rec.id))
    d = got.to_dict()
    assert d["platform"] == "douyin"
    assert d["image_atlas"] == [{"imageSrc": "a"}]
    assert d["captions"]["duration_minutes"] == 1
    assert d["captions"]["text_content"] == "文案"


def test_delete_record_cascades_caption(db):
    u = User(username="u2", password_hash="x")
    db.add(u)
    db.flush()
    rec = Record(user_id=u.id, source_url="s", video_url="v")
    db.add(rec)
    db.flush()
    db.add(Caption(record_id=rec.id, text_content="c"))
    db.commit()
    rec_id = rec.id

    db.delete(rec)
    db.commit()

    assert db.scalar(select(Record).where(Record.id == rec_id)) is None
    assert db.scalar(select(Caption).where(Caption.record_id == rec_id)) is None


def test_setting_roundtrip(db):
    db.add(Setting(key="visit_total", value=7))
    db.commit()
    row = db.get(Setting, "visit_total")
    assert row.value == 7


def test_sqlite_pragma_synchronous_normal():
    # WAL 标准搭配（2026-09-15 审计 M-13）：默认 FULL 每次提交多 1-2 次 fsync；
    # 1 = NORMAL（0=OFF / 2=FULL），连接事件按连接生效，池内连接均应命中
    from app.database import engine
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA synchronous").scalar() == 1


def test_startup_migration_indexes_exist(client):
    # _ensure_columns 幂等迁移（M-5/M-13）：users NOCASE 唯一索引 + records.created_at 索引
    from sqlalchemy import text

    from app.database import engine
    with engine.connect() as conn:
        names = {row[0] for row in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'"))}
    assert "ix_users_username_nocase" in names
    assert "ix_records_created_at" in names


def test_ensure_columns_isolates_failing_ddl(tmp_path, monkeypatch):
    """反例回归（2026-09-15 审查 F2）：某条索引 DDL 失败**不得**连带跳过其余迁移。

    原实现两条索引 DDL 之间**没有任何 try**：存量库若已有大小写重名，第一条
    （users NOCASE 唯一索引）抛错会一直穿透到 lifespan 的 except，导致
    ix_records_created_at 根本不会被创建，而注释却写"互不牵连"。
    这里用一次性临时库复现「第一条失败」，断言第二条仍建成。
    """
    from sqlalchemy import create_engine
    from sqlalchemy import text as sa_text

    from app import main as main_mod
    from app.database import Base

    eng = create_engine(f"sqlite:///{tmp_path}/iso.db", connect_args={"check_same_thread": False})
    try:
        Base.metadata.create_all(eng)
        with eng.begin() as conn:
            conn.execute(sa_text("DROP INDEX IF EXISTS ix_records_created_at"))

        real_text = sa_text

        def fake_text(sql):
            if "ix_users_username_nocase" in sql:
                raise RuntimeError("模拟存量大小写重名导致 NOCASE 唯一索引创建失败")
            return real_text(sql)

        monkeypatch.setattr(main_mod, "engine", eng)
        monkeypatch.setattr(main_mod, "text", fake_text)

        main_mod._ensure_columns()  # 逐条 try/except，整体不得抛出

        with eng.connect() as conn:
            names = {row[0] for row in conn.execute(
                sa_text("SELECT name FROM sqlite_master WHERE type='index'"))}
        assert "ix_records_created_at" in names  # 正例：前一条失败不牵连后一条
        assert "ix_users_username_nocase" not in names  # 反例：失败的那条确实没建成
    finally:
        eng.dispose()

