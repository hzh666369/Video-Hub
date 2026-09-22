# VideoHub 视频解析播放平台

小范围共用的视频解析播放平台：VIP 长视频解析线路、历史记录库。
完整功能介绍、部署与安全说明见仓库根目录 [README.md](../README.md)；Docker + Cloudflare 隧道部署详解见 [`Docker/README-Docker.md`](../Docker/README-Docker.md)。

## 功能速览

- **VIP 解析**：多线路可配置与切换，iframe 内嵌播放 + 新窗口打开两种模式；切回解析页时自动识别剪贴板中的支持平台链接（B站/腾讯/优酷/爱奇艺/芒果TV）并填入
- **视频库**：解析记录筛选/搜索/分页/删除/批量删除/标题编辑，按用户隔离；视频流与封面图经后端流式代理
- **访问统计**：管理员查看各用户最近/今日/历史访问与解析次数，操作日志检索
- **用户系统**：注册（验证码 + 限流防刷）、登录、改密、密码段位积分制（青铜~王者，规则见 `docs/密码段位说明书.md`）、管理员用户管理与密码重置
- **体验**：新手引导（仅新用户）、免责声明页、明暗双主题、粒子背景

已下线：付费的单视频直链解析与主页批量提取（92k 链路已移除），历史记录仍可在视频库查看。

## 启动

单端口手动启动（需已安装 Python 3.11+ 与 Node.js）：

```bash
# 1. 构建前端（vite build 输出至 backend/static，由 FastAPI 托管）
cd frontend && npm install && npm run build && cd ../backend

# 2. 创建虚拟环境并安装依赖
python -m venv .venv && .venv\Scripts\activate   # Linux/macOS: source .venv/bin/activate
pip install -e .

# 3. 启动服务
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 http://127.0.0.1:8000 。公网/团队共用请使用根 README 的 Docker + 隧道方案，不要直接暴露源站。

### 前端开发模式（可选）

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173 ，/api 自动代理到 8000（后端需先启动）
```

## 管理员账号

- 用户名 `admin`。
- 密码：**不再有默认密码**。首次启动时若未通过环境变量指定 `VIDEOHUB_ADMIN_PASSWORD`，
  系统会自动生成 12 位随机密码并写回 `backend/.env`（`VIDEOHUB_ADMIN_PASSWORD=` 一行），
  启动日志也会提示该位置。
- 以后想换密码：编辑 .env 那一行没用（仅首启生效），在 `backend` 目录下直接跑 `python scripts/user_passwd.py reset admin 新密码` 即可
- 想自行指定：在首启前设置环境变量，或编辑 `backend/.env` 后删除数据库重建。

## 初始配置（管理员）

- VIP 解析线路默认内置七条（虾米、万能稳定 + 牛导航的线路 1-5），可自由增删或设为默认；
  线路失效时可在 `backend` 目录下用 `python scripts/scrape_vip_routes.py merge` 从牛导航重新爬取并合并进数据库。
- 付费的单视频解析 / 主页批量提取功能已下线（原 92k 接口链路已整体移除）。

## 环境变量

可复制 `backend/.env.example` 为 `backend/.env`（已 gitignore，绝不入库）后按需取消注释，全部变量如下：

- `VIDEOHUB_ADMIN_PASSWORD`：初始管理员密码，未设置时首启自动生成并写回 `.env`
  （仅首次启动建号时生效）。
- `VIDEOHUB_SECRET_KEY`：会话签名密钥，未设置时首启自动生成并写回 `.env`。
- `VIDEOHUB_STATIC_DIR`：前端静态资源目录，默认 `backend/static`。
- `VIDEOHUB_DB_URL`：数据库连接串，默认 `sqlite:///./videohub.db`。
- `VIDEOHUB_HOST`：服务监听地址，默认 `0.0.0.0`。
- `VIDEOHUB_PORT`：服务监听端口，默认 `8000`。
- `VIDEOHUB_UPSTREAM_TIMEOUT`：上游代理请求超时秒数，默认 `300`。
- `VIDEOHUB_LOG_DIR`：访问日志目录，默认 `backend/logs`（在 `app/services/access_log.py` 中直接读取）。

## 安全与限流

- 登录失败：同一 IP 10 分钟内最多 10 次失败尝试，超出返回 429（成功登录不计数）
- 注册防刷：同一 IP 10 分钟内最多 10 次注册调用；成功注册间隔 ≥ 60 秒且 1 小时内最多 3 个账号
- 用户名查重：同一 IP 每分钟最多 30 次，防用户名枚举
- 验证码一次性使用；密码 BCrypt 加密；会话 Cookie 签名
- 删除用户时自动将其访问日志匿名化（user_id 置空），日志仍可按用户名快照查阅

## 测试

```bash
cd backend
pytest -v   # 全部测试（认证/注册/限流/VIP/记录/代理/设置/访问统计/密码段位/模型/健康检查）
```
