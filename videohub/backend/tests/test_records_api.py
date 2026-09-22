from app.models import Caption, Record, User


def _mk(db, n, **kw):
    for i in range(n):
        # FIX(brief): 原两批次标题都从 视频0 开始编号，第二批次会再生成一条 视频1，
        # 使 q=视频1 命中 2 条而非注释前提的 1 条；第二批次改用 剧 前缀保持断言意图。
        db.add(Record(user_id=1, title=f'{kw.get("title_prefix", "视频")}{i}', source_url=f"u{i}",
                      platform=kw.get("platform", "douyin"),
                      source_type=kw.get("source_type", "single"),
                      parse_status=kw.get("parse_status", "parsed"),
                      video_url=f"https://cdn/{i}.mp4"))
    db.commit()


def test_records_require_login(client):
    assert client.get("/api/records").status_code == 401


def test_list_filter_search_pagination(auth_client, db):
    _mk(db, 3)
    _mk(db, 2, platform="bilibili", source_type="vip", title_prefix="剧")
    r = auth_client.get("/api/records")
    assert r.json()["total"] == 5
    r = auth_client.get("/api/records", params={"platform": "bilibili"})
    assert r.json()["total"] == 2
    r = auth_client.get("/api/records", params={"q": "视频1"})
    assert r.json()["total"] == 1  # "视频1" 精确命中 1 条（视频1、视频10…不存在）
    r = auth_client.get("/api/records", params={"page": 2, "page_size": 2})
    assert len(r.json()["items"]) == 2


def test_get_and_delete_record(auth_client, db):
    _mk(db, 1)
    rid = db.query(Record).first().id
    assert auth_client.get(f"/api/records/{rid}").json()["title"] == "视频0"
    assert auth_client.delete(f"/api/records/{rid}").status_code == 200
    assert auth_client.get(f"/api/records/{rid}").status_code == 404


def test_list_records_no_n_plus_one(auth_client, db):
    """selectinload 回归（2026-09-15 审计 M-11）：to_dict 访问 caption 关系属性，
    若退回逐行懒加载，5 条记录会发 5 次额外 SELECT。"""
    from sqlalchemy import event

    from app.database import engine
    admin = db.query(User).filter_by(username="admin").first()
    for i in range(5):
        rec = Record(user_id=admin.id, source_type="vip", parse_status="parsed",
                     platform="tencent", source_url=f"https://v.qq.com/x/{i}",
                     video_url=f"https://v.qq.com/x/{i}")
        db.add(rec)
        db.flush()
        db.add(Caption(record_id=rec.id, text_content=f"c{i}"))
    db.commit()

    selects: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        r = auth_client.get("/api/records", params={"page_size": 5})
        assert r.status_code == 200
        assert len(r.json()["items"]) == 5
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    # get_current_user 1 + 总数 COUNT 1 + 页查询 1 + selectinload 批量取 caption 1 = 4；
    # N+1 退化时为 4 + 5 = 9
    assert len(selects) == 4, selects


def test_batch_delete_requires_login(client):
    assert client.post("/api/records/batch-delete", json={"ids": [1]}).status_code == 401


def test_batch_delete_success(auth_client, db):
    _mk(db, 3)
    ids = [r.id for r in db.query(Record).order_by(Record.id).all()]
    r = auth_client.post("/api/records/batch-delete", json={"ids": ids[:2]})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "deleted": 2}
    assert db.query(Record).count() == 1
    # 重复 ID 只算一次
    r = auth_client.post("/api/records/batch-delete", json={"ids": [ids[2], ids[2]]})
    assert r.json()["deleted"] == 1
    assert db.query(Record).count() == 0


def test_batch_delete_cascade_caption(auth_client, db):
    from app.models import Caption

    _mk(db, 1)
    rid = db.query(Record).first().id
    db.add(Caption(record_id=rid, text_content="字幕"))
    db.commit()
    r = auth_client.post("/api/records/batch-delete", json={"ids": [rid]})
    assert r.json()["deleted"] == 1
    assert db.query(Caption).count() == 0  # 级联删除文案，不残留孤儿行


def test_batch_delete_ignores_foreign_and_missing(auth_client, db):
    from app.models import User
    from app.services.auth import hash_password

    db.add(User(username="someone", password_hash=hash_password("password123")))
    db.flush()
    other_id = db.query(User).filter(User.username == "someone").first().id
    db.add(Record(user_id=other_id, title="别人的", source_url="u-x"))
    db.add(Record(user_id=1, title="自己的", source_url="u-me"))
    db.commit()
    ids = [r.id for r in db.query(Record).all()]
    r = auth_client.post("/api/records/batch-delete", json={"ids": ids + [99999]})
    assert r.json()["deleted"] == 1  # 他人的记录与不存在的 ID 均被忽略
    assert db.query(Record).filter(Record.title == "别人的").count() == 1


def test_batch_delete_empty_and_too_many(auth_client, db):
    r = auth_client.post("/api/records/batch-delete", json={"ids": []})
    assert r.status_code == 400
    assert r.json()["detail"] == "未选择任何记录"
    r = auth_client.post("/api/records/batch-delete", json={"ids": list(range(1, 202))})
    assert r.status_code == 400
    assert r.json()["detail"] == "单次最多删除 200 条"


def test_patch_title_success(auth_client, db):
    _mk(db, 1)
    rid = db.query(Record).first().id
    r = auth_client.patch(f"/api/records/{rid}", json={"title": "  我的专属标题  "})
    assert r.status_code == 200
    assert r.json()["title"] == "我的专属标题"  # 首尾空白被裁剪
    assert db.query(Record).get(rid).title == "我的专属标题"


def test_patch_title_duplicate(auth_client, db):
    _mk(db, 2)  # 视频0、视频1
    rid = db.query(Record).filter(Record.title == "视频0").first().id
    r = auth_client.patch(f"/api/records/{rid}", json={"title": "视频1"})
    assert r.status_code == 409
    # 大小写不同也算重复
    auth_client.patch(f"/api/records/{rid}", json={"title": "ABC"})
    r = auth_client.patch(f"/api/records/{rid}", json={"title": "abc"})
    assert r.status_code == 200  # 与自身同名不算重复
    other = db.query(Record).filter(Record.title == "视频1").first().id
    r = auth_client.patch(f"/api/records/{other}", json={"title": "abc"})
    assert r.status_code == 409


def test_patch_title_empty_and_too_long(auth_client, db):
    _mk(db, 1)
    rid = db.query(Record).first().id
    assert auth_client.patch(f"/api/records/{rid}", json={"title": "   "}).status_code == 400
    assert auth_client.patch(f"/api/records/{rid}", json={"title": "x" * 101}).status_code == 400


def test_patch_title_other_user_404(auth_client, db):
    from app.models import User
    from app.services.auth import hash_password

    db.add(User(username="someone", password_hash=hash_password("password123")))
    db.flush()
    other_id = db.query(User).filter(User.username == "someone").first().id
    db.add(Record(user_id=other_id, title="别人的", source_url="u-x"))
    db.commit()
    rid = db.query(Record).filter(Record.user_id == other_id).first().id
    assert auth_client.patch(f"/api/records/{rid}", json={"title": "抢过来"}).status_code == 404
