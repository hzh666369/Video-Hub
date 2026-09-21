@echo off
setlocal
chcp 65001 >nul

rem VideoHub Docker 一键部署/更新脚本（取代旧的 deploy-to-wsl.bat）
rem - 代码更新后：双击本脚本，自动重建镜像并重启容器，数据不丢
rem - 首次运行：自动把 历史文件/ 里的旧数据库导入数据卷（导入过一次后跳过）
rem - 公网入口：Cloudflare 命名隧道，固定域名（改域名时同步改下面 PUBLIC_URL 与 CF 后台）

cd /d "%~dp0"

rem 公网地址：从本地 Docker\.env 读取 PUBLIC_URL（固定域名不入库，避免公开仓库暴露线上入口）
rem 请在 Docker\.env 配置一行：PUBLIC_URL=https://<你的固定域名>
set "PUBLIC_URL="
for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do if /i "%%a"=="PUBLIC_URL" set "PUBLIC_URL=%%b"
if not defined PUBLIC_URL (
    echo [VideoHub] 未在 Docker\.env 找到 PUBLIC_URL，请先配置你的固定域名后重跑本脚本。
    pause
    exit /b 1
)

echo [VideoHub] 1/5 构建镜像（代码更新体现在这一步）...
docker compose build
if errorlevel 1 goto fail

echo [VideoHub] 2/5 准备数据卷...
docker compose run --rm --no-deps --entrypoint sh drone-test -c "test -f /app/data/videohub.db" >nul 2>&1
if errorlevel 1 (
    if exist "历史文件\videohub.db" (
        echo   检测到历史数据，正在导入...
        docker compose create drone-test >nul 2>&1
        docker compose stop drone-test >nul 2>&1
        docker cp "历史文件\videohub.db" drone-test:/app/data/videohub.db
        docker cp "历史文件\videohub.db-wal" drone-test:/app/data/ >nul 2>&1
        docker cp "历史文件\videohub.db-shm" drone-test:/app/data/ >nul 2>&1
        rem docker cp 进来的文件属主是 root，改回 appuser（SQLite 需要写权限）
        docker compose run --rm --no-deps --user root --entrypoint sh drone-test -c "chown -R appuser:appuser /app/data" >nul 2>&1
        echo   导入完成。
    ) else (
        echo   全新安装，将创建空数据库。
    )
) else (
    echo   数据库已存在，保留现有数据。
)

echo [VideoHub] 3/5 启动服务（应用 + Cloudflare 隧道）...
docker compose up -d
if errorlevel 1 goto fail

echo [VideoHub] 4/5 检查公网连通（命名隧道注册需要几秒）...
rem 等 6 秒让隧道向 Cloudflare 注册，然后探测固定域名是否已通，通就把地址写入 tunnel-url.txt
powershell -NoProfile -Command "Start-Sleep 6; try { $r = Invoke-WebRequest -Uri '%PUBLIC_URL%' -Method Head -TimeoutSec 20 -UseBasicParsing; if ($r.StatusCode -lt 500) { Set-Content -Path tunnel-url.txt -Value '%PUBLIC_URL%' -Encoding ascii; Write-Host ('  公网地址: %PUBLIC_URL%  (HTTP ' + $r.StatusCode + ')  已写入 tunnel-url.txt') } else { Write-Host ('  返回 HTTP ' + $r.StatusCode + '，应用可能未就绪，稍后重跑本脚本。') } } catch { Write-Host '  暂未连通（隧道仍在注册或 Public Hostname 未生效），稍后重跑本脚本；域名解析需几分钟。' }"

echo [VideoHub] 5/5 当前状态...
docker compose ps
echo.
echo [VideoHub] 完成。本机: http://127.0.0.1:8000   公网: %PUBLIC_URL% （固定域名，不再变动）
pause
exit /b 0

:fail
echo [VideoHub] 部署失败，请检查上方错误信息。
pause
exit /b 1
