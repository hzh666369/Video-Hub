def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    # 2026-09-18 爬虫复测收敛：body 不再携带 database 等内部状态字段，
    # 库不可用只经 503 状态码表达（见 test_health_reports_database_failure）
    assert r.json() == {"status": "ok"}


def test_health_reports_database_failure(client, monkeypatch):
    """数据库探测失败时探针必须拒绝（503）：攻击场景回归的反例面——
    后端进程活着但库不可用时，前端状态灯必须亮红灯「数据异常」而非绿灯。"""
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    def broken_execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(Session, "execute", broken_execute)
    r = client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["detail"] == "数据库暂不可用"

    # 正例放行：探测恢复后回到 200（绿灯）
    monkeypatch.undo()
    assert client.get("/api/health").status_code == 200


def test_health_rate_limited(client):
    """公开探针按 S5 限流（30 次/分钟/IP）：超出后拒绝，防被刷成免费探测口。"""
    for _ in range(30):
        assert client.get("/api/health").status_code == 200
    r = client.get("/api/health")
    assert r.status_code == 429


def test_api_unknown_path_returns_404_json(client):
    r = client.get("/api/no-such-api")
    assert r.status_code == 404
    assert r.json()["detail"] == "Not Found"


def test_spa_fallback_blocks_path_traversal(tmp_path, monkeypatch):
    """SPA 回退不得返回 static 目录之外的文件（路径穿越回归）。

    所有文件都放在 pytest 临时目录里：通过 VIDEOHUB_STATIC_DIR 让一份全新的
    app.main 在 import 期就把静态根指到 tmp 目录，全程不读写真实的
    backend/static，因此不会破坏 `npm run build` 的产物。
    """
    import importlib.util
    from pathlib import Path

    from fastapi.testclient import TestClient

    static_root = tmp_path / "static"
    (static_root / "assets").mkdir(parents=True)
    (static_root / "index.html").write_text("<html>spa index</html>", encoding="utf-8")
    (static_root / "real.txt").write_text("legit", encoding="utf-8")
    (static_root / "assets" / "app.js").write_text("console.log(1);", encoding="utf-8")

    # 机密文件位于 static 根之外（tmp_path 内，pytest 自动清理）。
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET-CONTENT", encoding="utf-8")
    secret_outside = tmp_path / "nested" / "also-secret.txt"
    secret_outside.parent.mkdir()
    secret_outside.write_text("ALSO-TOPSECRET", encoding="utf-8")

    # 必须在模块执行前设置：import 期的条件注册（挂载 /assets、注册回退路由）
    # 都基于这个目录判断。
    monkeypatch.setenv("VIDEOHUB_STATIC_DIR", str(static_root))

    backend_dir = Path(__file__).resolve().parent.parent
    # 加载一份全新的 app.main，走真实代码路径（条件注册 + 回退逻辑），
    # 不影响其他测试共享的 app 实例。
    spec = importlib.util.spec_from_file_location("videohub_spa_probe_main", backend_dir / "app" / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 回退与挂载确实指向临时目录（而非真实构建产物）。
    assert module.STATIC_DIR == static_root

    with TestClient(module.app) as c:
        # 尝试逃逸 static 根的请求一律不得返回 static 之外的文件内容。
        for probe in (
            "/..%2fsecret.txt",
            "/%2e%2e%2fsecret.txt",
            "/..%2f..%2fsecret.txt",
            "/assets/..%2fsecret.txt",
            "/assets/..%2f..%2fsecret.txt",
            "/nested/..%2f..%2fsecret.txt",
            "/sub/dir/../../secret.txt",
        ):
            r = c.get(probe)
            assert r.status_code in (200, 404), (probe, r.status_code)
            assert "TOPSECRET-CONTENT" not in r.text, probe
            assert "ALSO-TOPSECRET" not in r.text, probe

        # 正向对照：static 根内的真实文件（含 /assets 挂载）照常返回，防护不误伤。
        ok = c.get("/real.txt")
        assert ok.status_code == 200
        assert ok.text == "legit"

        js = c.get("/assets/app.js")
        assert js.status_code == 200
        assert js.text == "console.log(1);"

        # 命中回退的未知路径返回 SPA 入口页。
        spa = c.get("/some/spa/route")
        assert spa.status_code == 200
        assert spa.text == "<html>spa index</html>"


def test_robots_txt_disallows_all_crawling(tmp_path, monkeypatch):
    """全站禁抓取（2026-09-18 爬虫视角安全测试同类发现项）：登录制私人应用无公开
    可索引内容，robots.txt 必须存在且 Disallow 全站，并作为真实文件返回而非被
    SPA 回退吞成 index.html 空壳（否则爬虫会把所有路径当页面反复抓取空转）。"""
    import importlib.util
    from pathlib import Path

    from fastapi.testclient import TestClient

    source = Path(__file__).resolve().parents[2] / "frontend" / "public" / "robots.txt"
    content = source.read_text(encoding="utf-8")
    assert "User-agent: *" in content
    assert "Disallow: /" in content

    static_root = tmp_path / "static"
    (static_root / "assets").mkdir(parents=True)
    (static_root / "index.html").write_text("<html>spa index</html>", encoding="utf-8")
    (static_root / "robots.txt").write_text(content, encoding="utf-8")

    # 与 test_spa_fallback_blocks_path_traversal 同法：临时静态根加载一份全新 app.main
    monkeypatch.setenv("VIDEOHUB_STATIC_DIR", str(static_root))
    backend_dir = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "videohub_robots_probe_main", backend_dir / "app" / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with TestClient(module.app) as c:
        r = c.get("/robots.txt")
        assert r.status_code == 200
        assert "Disallow: /" in r.text
        assert "spa index" not in r.text

        # 反例：sitemap.xml 不存在时必须明确 404，不得被 SPA 回退吞成 200 空壳
        # （否则爬虫把站点地图当页面无限空转抓取）；正常 SPA 路由仍回退到入口页
        sm = c.get("/sitemap.xml")
        assert sm.status_code == 404
        spa = c.get("/some/spa/route")
        assert spa.status_code == 200
        assert spa.text == "<html>spa index</html>"
