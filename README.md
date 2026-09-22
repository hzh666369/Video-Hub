# VideoHub 视频解析播放平台

VideoHub 是一个小范围共用的 VIP 长视频解析播放平台：多线路解析、历史记录库、流媒体代理与访问统计。

> 部署：Docker + Cloudflare 隧道见下文「📦 部署」与 [`Docker/README-Docker.md`](Docker/README-Docker.md)；English version: [README.en.md](README.en.md)。

## ✨ 核心功能

| 模块 | 功能描述 |
|------|----------|
| **用户系统** | 注册、登录、密码修改、验证码保护、多级限流防刷、密码段位积分制（青铜~王者）、两步验证（TOTP + 一次性恢复代码）、账户自助注销 |
| **VIP 解析** | 多线路可配置与切换，iframe 内嵌播放 + 新窗口打开两种模式，剪贴板链接自动识别填入 |
| **视频库** | 解析记录筛选、搜索、分页、删除/批量删除、标题编辑（数据按用户隔离） |
| **流媒体代理** | 历史记录的视频流与封面图流式代理（共享连接池、Range 支持） |
| **数据大屏** | 管理看板：KPI / 访问与解析趋势 / 平台占比 / 用户排行 / 最新动态 / 系统状态；实时在线人数走内存心跳（前端 30s 上报、120s 窗口），页面 60s 轮询聚合端点 |
| **访问统计** | 管理员查看各用户最近访问/今日/历史访问与解析次数，支持操作日志检索 |
| **系统设置** | 管理员管理 VIP 解析线路（JSON 结构化校验）、用户创建/删除/密码重置 |
| **功能点授权** | 四个权限码（dashboard / routes / users / access）：可授予普通用户只读可见大屏、线路列表、用户列表与访问记录；一切写操作仍仅限管理员 |
| **体验细节** | 新手引导（仅新用户）、免责声明页、明暗双主题、粒子背景、回到顶部等 |

已下线：付费的单视频直链解析与主页批量提取功能（原 92k 接口链路已整体移除），历史记录仍可在视频库查看。

## 🛠 技术栈

### 后端（`videohub/backend`）
- **Python 3.11+** / **FastAPI** — 异步 API 框架
- **SQLAlchemy 2.0** — ORM，数据持久化至 SQLite（WAL 模式）
- **pydantic-settings** — 环境配置（`VIDEOHUB_` 前缀，自动写回 `.env`）
- **httpx** — 异步 HTTP 客户端（流式代理，共享连接池）
- **BCrypt** — 用户密码加密
- **itsdangerous** — Cookie 会话签名（SessionMiddleware）
- **Pillow** — 验证码图片渲染（按字号缓存字体）
- **qrcode** — TOTP 绑定二维码（复用 Pillow，渲染为 data URI 供前端 `<img>` 直用）

### 前端（`videohub/frontend`）
- **Vue 3**（Composition API）+ **Vite 8**
- **Pinia 4** — 状态管理（auth、theme、toast）
- **Vue Router 4** + **Axios**
- **ArtPlayer** — HTML5 播放器
- **three.js** — ParseHome 粒子背景（动态导入，按需加载）
- **GSAP** — 页面动效（`directives/vfx.js`、`views/parseVfx.js`）
- **@phosphor-icons/vue** — 图标
- CSS Variables 明暗双主题

### 测试
- **pytest** + **respx** — 后端单元/集成测试（认证、限流、注册、VIP、记录、代理、设置、访问统计、大屏、心跳、两步验证、功能点授权、账户注销、模型、健康检查，及安全回归 `test_security_fixes` / `test_security_hardening`）

## 📁 项目结构

```
vidio-project/
├── videohub/                    # 应用源码 + 镜像构建定义
│   ├── backend/                 # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/             # 路由层（access、auth、dashboard、deps、heartbeat、parse、records、settings、stream、visits）
│   │   │   ├── models/          # SQLAlchemy 模型（User、Record+Caption、Setting、AccessLog、RecoveryCode）
│   │   │   ├── services/        # 业务模块（access_log、auth、captcha、client_ip、password_tier、permissions、platform、presence、proxy、ratelimit、settings、totp、urlguard）
│   │   │   ├── config.py        # 环境配置与密钥/密码持久化
│   │   │   ├── database.py      # 数据库引擎与会话（WAL + busy_timeout）
│   │   │   └── main.py          # 应用入口、生命周期（存量库幂等补列迁移）、SPA 静态托管
│   │   ├── tests/               # pytest 测试套件（含安全回归 test_security_fixes / test_security_hardening）
│   │   ├── scripts/             # 运维脚本（user_passwd.py 密码重置、scrape_vip_routes.py 线路爬取）
│   │   ├── static/              # 前端构建产物（vite build 输出目录，不入库）
│   │   ├── .env.example         # 后端环境变量模板（复制为 .env 使用）
│   │   └── pyproject.toml
│   ├── frontend/                # Vue 3 前端
│   │   ├── src/
│   │   │   ├── api/             # Axios 实例封装
│   │   │   ├── components/      # 公共组件（VhAurora、VhParticleField、VhOnboarding、VhPopover…，dashboard/ 大屏子组件）
│   │   │   ├── stores/          # Pinia 状态（auth、theme、toast）
│   │   │   ├── router/          # Vue Router 配置
│   │   │   ├── styles/          # 主题令牌与全局样式（明暗双主题）
│   │   │   ├── utils/           # passwordTier.js（密码段位前后端同规则）、permissions.js（权限码与后端同步）
│   │   │   ├── views/           # 页面（Dashboard、Disclaimer、Library、Login、ParseHome、Player、Settings）
│   │   │   └── main.js
│   │   └── vite.config.js       # dev 代理 /api → :8000；build 输出至 backend/static
│   ├── Dockerfile               # 镜像构建（多阶段：前端 build + 后端运行），构建上下文即本目录
│   ├── .dockerignore            # 构建上下文过滤（须与 Dockerfile 同处 videohub/ 根）
│   ├── docs/                    # 密码段位说明书等
│   └── README.md                # 后端日常使用说明
├── Docker/                      # 部署编排层（不含构建定义，构建上下文指回 ../videohub）
│   ├── docker-compose.yml       # 应用 + Cloudflare 命名隧道
│   ├── deploy-docker.bat        # Windows 一键构建/更新脚本（域名等配置读 Docker/.env）
│   ├── .env                     # 本地密钥与 PUBLIC_URL（已 gitignore，绝不入库）
│   ├── .env.example             # .env 模板（复制为 .env 后填写）
│   └── README-Docker.md         # Docker 部署详解（域名/隧道/.env 配置）
├── .gitignore                   # 单一根级忽略规则
├── LICENSE                      # MIT 开源许可证
├── README.md                    # 本文档（中文）
└── README.en.md                 # 英文文档
```

## 🚀 快速启动

### 本地开发（手动启动）
```bash
# 后端（端口 8000，在仓库根目录执行；uvicorn 会占住该终端）
cd videohub/backend
python -m venv .venv && .venv\Scripts\activate   # Linux/macOS: source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 前端（端口 5173，/api 自动代理到 8000）—— 另开一个终端，从仓库根目录进入
cd videohub/frontend
npm install
npm run dev
```
- 开发访问地址：http://localhost:5173（Vite 代理）或后端 http://127.0.0.1:8000
- 对外公网访问请走下文「📦 部署」的 Docker + Cloudflare 隧道方案；局域网直连会使限流与日志的访客 IP 失真

### 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | `admin` | 无默认密码：首次启动自动生成 12 位随机密码并写回 `backend/.env`（`VIDEOHUB_ADMIN_PASSWORD=`），启动日志会提示该位置 |

- 重置密码（在 `videohub/backend` 目录下执行）：`python scripts/user_passwd.py reset admin 新密码`
- 也可在首次启动前通过环境变量 `VIDEOHUB_ADMIN_PASSWORD` 自行指定

## 📖 使用指南

### 登录 / 注册
- 新用户注册需通过一次性验证码校验与密码段位校验（积分制：长度 + 字符类别得分、连续/重复片段扣分，至少 8 位且达到最低段位「青铜」，注册时实时显示青铜~王者段位；弱密码黑名单命中封顶青铜，完整规则见 `videohub/docs/密码段位说明书.md`）
- 用户名规则：3-32 位，字母开头，仅字母/数字/下划线，注册前可查重
- 防刷限流（见下方「安全与限流」）

### 两步验证（2FA / TOTP）
- 入口在右上角账户菜单：获取密钥（扫描二维码或手动录入 `otpauth://` 串）→ 输入一枚 6 位动态码确认开启 → 展示 10 组一次性恢复代码（明文仅此一次回传，须确认已保存）
- 开启后登录需「密码 + 动态码（或恢复代码）」双因子；动态码失败与密码失败同口径计入三级限流
- 动态码遵循 RFC 6238（30 秒步长 / SHA1 / 6 位），兼容 Google / Microsoft Authenticator、1Password 等主流认证器；容忍 ±1 步时钟漂移，已消费时间步单调拒绝重放
- 恢复代码格式 XXXX-XXXX（去混淆字符表），库里只存加盐 SHA-256，用后即标记作废
- 关闭需「登录密码 + 动态码（或恢复代码）」双重确认，关闭时清除密钥与全部恢复代码

### 账户注销
- 普通用户可在账户菜单自助注销：输入登录密码二次确认（按用户限流，只统计失败次数）
- 注销将永久删除账号及名下全部解析记录（字幕随外键级联清理）；访问日志匿名化但保留用户名快照可查
- 管理员账户不支持自助注销（防系统失管），需联系维护者处理

### VIP 视频解析
- 粘贴长视频链接（B站/腾讯视频/优酷/爱奇艺/芒果TV），选择解析线路
- 切回解析页时自动识别剪贴板中的支持平台链接并填入（仅识别上述平台的长视频链接，其余剪贴板内容不打扰；复制了新链接后再次切回会覆盖旧链接，始终以最新复制为准）
- 解析成功自动进入播放页：iframe 内嵌播放，线路不允许内嵌时提供「新窗口打开」
- 线路失效时换一条线路重新解析即可；管理员可在设置中增删线路或设为默认

### 视频库
- 按平台/来源类型筛选，按标题关键词搜索，分页浏览（默认 20 条/页）
- 支持删除、批量删除与标题编辑；记录数据按用户隔离
- 历史记录的视频流与封面图经后端流式代理加载

### 管理员功能
- **数据大屏**：KPI、访问/解析趋势、平台占比、用户排行、最新动态、系统状态（DB 体积、隧道标识、实时在线人数）；管理员默认可见，亦可只读授权给普通用户
- **系统设置**：VIP 解析线路管理（内置七条，可在 `videohub/backend` 目录下用 `python scripts/scrape_vip_routes.py merge` 从牛导航重新爬取合并）
- **用户管理**：创建/删除用户、重置普通用户密码、勾选功能点权限（见下）
- **功能点授权**：权限码 dashboard / routes / users / access，授权语义 = **只读可见**对应页面/列表；一切写操作（改线路、增删用户、重置密码等）仍仅限管理员，未知权限码一律白名单拒绝
- **访问统计**：各用户最近访问/今日/历史访问/解析次数汇总，操作日志检索

## ⚙️ 环境变量（后端）

所有变量使用 `VIDEOHUB_` 前缀，可经环境变量或 `backend/.env` 配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VIDEOHUB_ADMIN_PASSWORD` | 初始管理员密码（仅首次建号时生效） | 首启自动生成并写回 `.env` |
| `VIDEOHUB_SECRET_KEY` | 会话签名密钥 | 首启自动生成并写回 `.env` |
| `VIDEOHUB_STATIC_DIR` | 前端静态资源目录 | `backend/static` |
| `VIDEOHUB_DB_URL` | 数据库连接串 | `sqlite:///./videohub.db` |
| `VIDEOHUB_HOST` | 服务监听地址 | `0.0.0.0` |
| `VIDEOHUB_PORT` | 服务监听端口 | `8000` |
| `VIDEOHUB_UPSTREAM_TIMEOUT` | 上游代理请求超时秒数 | `300` |
| `VIDEOHUB_LOG_DIR` | 访问日志目录 | `backend/logs` |
| `VIDEOHUB_COOKIE_SECURE` | 会话 Cookie 仅 HTTPS 传输（公网隧道部署置 `1`） | `false` |

> 完整模型见 `videohub/backend/app/config.py`；其中 `VIDEOHUB_STATIC_DIR`、`VIDEOHUB_LOG_DIR` 不走 Settings 模型，分别在 `app/main.py`、`app/services/access_log.py` 中直接读取环境变量。

## 🔒 安全与限流

> 新增安全控制必须附带攻击场景回归测试；新增限流器必须登记进 `videohub/backend/tests/conftest.py::_reset_limiters`。

- **真实客户端 IP**：公网流量经 cloudflared 隧道转发，后端从 `CF-Connecting-IP` 取真实访客 IP（`app/services/client_ip.py`），限流与日志不受代理影响
- 登录失败三级限流：① IP 维 10 分钟内最多 10 次失败尝试，超出 429（成功登录不计数）；② 账号维跨 IP 汇总，第 20 次失败起必须先通过人机验证码才放行到密码校验（防代理池分布式爆破，同时避免「任意第三方凑 20 次失败即锁死受害账号」的 DoS）；③ 10 分钟内失败 50 次临时锁定该账户，窗口滑出自动解锁
- 注册防刷：同一 IP 10 分钟内最多 10 次注册调用；成功注册间隔 ≥ 60 秒且 1 小时内最多 3 个账号
- 用户名查重限流：同一 IP 每分钟最多 30 次，防用户名枚举
- 验证码签发限流：同一 IP 每分钟最多 30 张（渲染吃 CPU，防无登录刷接口）；访问计数上报按用户每分钟 30 次（防刷库）
- 验证码一次性使用、答案用加密随机生成；密码 BCrypt 加密；会话 Cookie 签名（HttpOnly，公网部署仅 HTTPS 传输）
- **TOTP 两步验证（S19）**：密钥与恢复代码一律 `secrets` 生成、比较走 `hmac.compare_digest`；恢复代码只存加盐 SHA-256、用后即废；动态码按单调 `last_step` 拒绝重放；动态码失败与密码失败同口径记账限流
- **改密即全端下线**：会话携带密码指纹（`pw_pv`），本人改密或管理员重置后，其他设备的旧会话立即失效
- **破坏性操作闸门**：改密需原密码（登录态下唯一密码核验闸门，按用户失败限流）；自助注销需密码二次确认 + 按用户限流，管理员不可自助注销
- **功能点授权只读边界**：`require_perm` 仅放行只读端点可见性，写端点一律 `require_admin`；权限码白名单校验，未知码拒绝
- **代理目标校验**：流式代理前拒绝内网/环回/链路本地/CGNAT 地址（`app/services/urlguard.py`），防存量记录被用作 SSRF 跳板
- 管理员账户保护：不允许经 API 删除管理员或重置管理员密码（防管理员间横向接管），admin 改密走个人接口
- 删除用户/自助注销时自动将其访问日志匿名化（user_id 置空），日志仍可按用户名快照查阅；日志字段过滤换行防伪造
- 限流桶键经 `rate_limit_key` 收敛（IPv6 → /64），防旋转接口标识符重置计数；日志仍记完整 IP

## 🧪 测试与交付门禁

须使用装好后端依赖的解释器运行全量测试（Windows 下 `.venv\Scripts\python.exe`，Linux 为 `.venv/bin/python`）：

```bash
cd videohub/backend
./.venv/Scripts/python.exe -m pytest tests/ -q                # 全量测试必须全绿
./.venv/Scripts/python.exe -m pytest tests/test_auth.py -v    # 只运行认证模块
```

覆盖模块：认证（登录/注册/改密/验证码/三级限流）、用户名查重、密码段位判定（积分制）、平台识别、VIP 解析与 embed 预检、记录 CRUD 与属主权限、流式代理（Range/403/410）、系统设置与用户管理、功能点授权、访问统计、数据大屏聚合、心跳与在线人数、TOTP 两步验证与恢复代码、账户注销级联清理、模型、健康检查，以及安全回归（`test_security_fixes` / `test_security_hardening`，覆盖各已知攻击场景的正反例）。新增安全控制必须附带攻击场景回归测试；新增限流器必须登记进 `tests/conftest.py::_reset_limiters`。

## 📦 部署

### Docker + Cloudflare 隧道（推荐）

应用容器对外**只绑定 `127.0.0.1:8000`**，公网流量全部经 Cloudflare 命名隧道（`cloudflared` 容器）转发，本机不开放任何入站端口、也无需安装 cloudflared。完整详解见 [`Docker/README-Docker.md`](Docker/README-Docker.md)。

**所有密钥与固定域名统一放在 `Docker/.env`（已被 gitignore，绝不入库；可复制 [`Docker/.env.example`](Docker/.env.example) 为 `Docker/.env` 后填写）：**

```ini
VIDEOHUB_SECRET_KEY=<会话签名随机密钥，如 openssl rand -hex 32>
TUNNEL_TOKEN=<Cloudflare Zero Trust 隧道令牌，eyJ 开头>
PUBLIC_URL=https://<你的域名>.kdns.fr
# 可选：留空则首启自动生成随机管理员密码
VIDEOHUB_ADMIN_PASSWORD=
```

**设置域名的步骤：**

1. **准备域名**：用自有域名，或免费二级域名（如 KataBump 的 `xxx.kdns.fr`，已过 Public Suffix List，可 NS 委派给 Cloudflare）。
2. **接入 Cloudflare**：在 Cloudflare 添加该域名，按提示到域名商处把 NS 改指向 Cloudflare（免费计划即可）。
3. **建隧道拿令牌**：Zero Trust 后台 → Networks → Tunnels → 创建 connector，复制生成的令牌（`eyJ…`）填入 `.env` 的 `TUNNEL_TOKEN`。
4. **配 Public Hostname**：在该隧道下添加 hostname，`Service` 填 `http://drone-test:8000`（**容器名，不是 localhost**）。
5. **同步 PUBLIC_URL 并部署**：把最终域名写进 `.env` 的 `PUBLIC_URL`，双击 `Docker/deploy-docker.bat` 一键构建启动。

要点补充：

- `PUBLIC_URL` 仅被 `deploy-docker.bat` 用于连通性探测与地址存档（写入本地 `tunnel-url.txt`）；**换域名只改 `.env` 即可，无需改动脚本或容器**。
- 更新代码后同样双击 `deploy-docker.bat`：重建镜像并重启容器，数据卷与域名保持不变。
- 仓库内不出现任何真实域名/令牌，`docker-compose.yml` 与文档里的 `<你的域名>.kdns.fr` 均为**占位示例**，请替换为你自己的配置。

### 本地手动 / 自建反代
1. 可复制 `videohub/backend/.env.example` 为 `videohub/backend/.env` 按需填写（不建也能跑：密钥与管理员密码首启自动生成）
2. 前端 `npm run build`（输出至 `backend/static`）
3. FastAPI 自动托管静态目录并提供 SPA 回退（`VIDEOHUB_STATIC_DIR` 可覆盖）
4. 建议 `uvicorn app.main:app --host 127.0.0.1 --port 8000` 启动，前面再放 Nginx/隧道等反向代理与 HTTPS；**不要把 `0.0.0.0` 直接暴露到公网**，源站只应由隧道或反代访问。

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。
