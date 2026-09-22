# Docker 部署说明

## 架构

```
公网用户 → https://<你的域名>.kdns.fr（固定域名，Cloudflare 免费托管 + 自动 HTTPS）
        → Cloudflare 边缘
        → cloudflared 容器（命名隧道，出站连接，无需开放任何入站端口）
        → drone-test 容器（仅绑定 127.0.0.1:8000，内网同事无法直达）
```

- **固定域名**：<你的域名>.kdns.fr —— KataBump 免费二级域名，已通过 NS 委派接入 Cloudflare
  （zone 的 NS 为 `malcolm.ns.cloudflare.com` / `zelda.ns.cloudflare.com`），公网地址**永久固定**，
  不受容器/Docker/整机重启影响。
- **隧道**：Cloudflare 命名隧道（令牌模式），令牌在 `.env` 的 `TUNNEL_TOKEN`（eyJ 开头，不入库）。
- Windows 本机**不需要安装** cloudflared，隧道以容器方式随 compose 运行。

## 首次部署：准备 `.env` 与域名

所有密钥与固定域名统一放在**本文件夹的 `Docker/.env`**（已被 `.gitignore` 排除，绝不入库）。docker compose 与 `deploy-docker.bat` 都读它。首次部署前把 `Docker/.env.example` 复制为 `Docker/.env`，至少填入：

```ini
# 会话签名密钥（随机串即可，如 openssl rand -hex 32 生成）
VIDEOHUB_SECRET_KEY=<64位随机十六进制串>

# Cloudflare Zero Trust 命名隧道的令牌（eyJ 开头，后台复制）
TUNNEL_TOKEN=<你的 Cloudflare 隧道令牌>

# 公网访问地址：deploy-docker.bat 用它做连通性探测与地址存档（换成你自己的域名）
PUBLIC_URL=https://<你的域名>.kdns.fr

# 可选：首次启动前指定管理员初始密码（留空则自动生成随机密码写回 backend/.env）
VIDEOHUB_ADMIN_PASSWORD=
```

域名与隧道配置步骤：

1. **准备域名**：可用自有域名，或免费二级域名（如 [KataBump](https://dashboard.katabump.com) 的 `xxx.kdns.fr`，已过 Public Suffix List，可 NS 委派给 Cloudflare）。
2. **把域名接入 Cloudflare**（免费计划）：在 Cloudflare 添加该 Site，按提示到域名商处把 NS 改指向 Cloudflare（例：`<nameserver>.ns.cloudflare.com`）。
3. **建命名隧道**：Zero Trust 后台 → Networks → Tunnels → 创建 Cloudflare connector → 复制生成的**令牌**（`eyJ…`）填入 `.env` 的 `TUNNEL_TOKEN`。
4. **配 Public Hostname**：同一隧道里加 hostname，`Hostname` 填你的完整域名，`Service` 填 `http://drone-test:8000`（**容器名，不是 localhost**）。
5. **同步 `PUBLIC_URL`**：把最终域名写进 `Docker/.env` 的 `PUBLIC_URL`，双击 `Docker/deploy-docker.bat` 一键构建并启动。

## 日常使用

- **更新代码后**：双击 `Docker/deploy-docker.bat` → 重建镜像并重启应用，域名不变。
- **公网地址（主入口）**：即 `.env` 里 `PUBLIC_URL` 的域名（每次部署脚本会探测连通性，并把地址写入
  本文件夹的 `tunnel-url.txt` 存档）。给同事发这个固定地址即可，以后不用再换。
- **换域名/加子域名**：在 Zero Trust 后台（Networks → Tunnels → 本隧道 → Public Hostname）增删条目，
  并同步修改 `Docker/.env` 的 `PUBLIC_URL` 即可，无需改动容器或脚本（域名不再写死在脚本里）。

## 数据与备份

- 位置：Docker 卷 `videohub-data`（容器内 `/app/data`：`videohub.db` + `logs/`）。服务名改过两次（videohub → ai-hub → drone-test，后者仅为低调不暴露用途），卷名始终沿用最初的，数据才不丢。
- 备份：`docker run --rm -v videohub-data:/data -v "%cd%":/backup alpine tar czf /backup/videohub-backup.tar.gz -C /data .`
- 恢复：先停容器，把备份解回卷（或 `docker cp` 到 `drone-test:/app/data/`），再启动。

## 常用命令

| 操作 | 命令 |
|---|---|
| 看后端日志 | `docker compose logs -f drone-test` |
| 看隧道日志 | `docker compose logs -f cloudflared` |
| 重启 | `docker compose restart`（域名不受影响） |
| 停止 | `docker compose down`（**不加** `-v`，数据不动；`-v` 会删卷！） |
| 公网地址存档 | `type tunnel-url.txt` |

## 域名与隧道配置备忘

1. 域名来自 [KataBump](https://dashboard.katabump.com)（免费二级域名 `xxx.kdns.fr`，每账号 2 个，
   已过 PSL 可 NS 委派给 Cloudflare）。2026-09 申请，当前 zone：`<你的域名>.kdns.fr`。
2. Zone 在 Cloudflare（免费计划），NS 委派：`malcolm.ns.cloudflare.com` / `zelda.ns.cloudflare.com`。
3. Zero Trust 后台已建命名隧道（容器 `drone-test-cloudflared` 用的就是它），令牌存两处：
   - `.env` → `TUNNEL_TOKEN`（compose 实际读取，**此文件为准**）
   - `clauflaretoken.txt`（旧存档，仅备份，脚本不读取）
4. Public Hostname：`<你的域名>.kdns.fr` → Service `http://drone-test:8000`（容器名，不是 localhost）。

> 注意：.env、clauflaretoken.txt、tunnel-url.txt 均已被 .gitignore 排除，不会提交进仓库。

## 备注

- 本机调试入口 `http://127.0.0.1:8000` 保留（仅本机回环，内网访问不到）；想彻底只走隧道，删掉 compose 里 `ports` 两行。
- 大陆访问走 Cloudflare 免费边缘，延迟高于国内 CDN，属正常现象；体验不可接受再评估备案 + 国内 CDN 路线。
