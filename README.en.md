# VideoHub Video Parsing & Playback Platform

VideoHub is a small-scope VIP long-video parsing & playback platform: multi-route parsing, a history record library, streaming media proxy, data dashboard, fine-grained read-only permissions, and access statistics.

> Deployment: Docker + Cloudflare tunnel — see the "📦 Deployment" section below and [`Docker/README-Docker.md`](Docker/README-Docker.md). Chinese version: [README.md](README.md).

## ✨ Core Features

| Module | Feature Description |
|------|----------|
| **User System** | Registration, Login, Password Change, Captcha Protection, Multi-level Rate Limiting, Password Tier Scoring (Bronze ~ King), Two-Factor Authentication (TOTP + one-time recovery codes), self-service account deletion |
| **VIP Parsing** | Multiple configurable & switchable parsing routes, iframe embedded playback + open-in-new-window modes, clipboard link auto-detection |
| **Video Library** | Parse record filtering, search, pagination, delete/batch delete, title editing (data isolated per user) |
| **Streaming Media Proxy** | Streaming proxy for video streams and cover images of history records (shared connection pool, Range support) |
| **Data Dashboard** | Admin dashboard: KPIs / visit & parse trends / platform share / user ranking / recent activity / system status; real-time online count via in-memory heartbeats (frontend reports every 30s, 120s window), page polls the aggregate endpoint every 60s |
| **Access Statistics** | Admin view of each user's recent/today/historical visits and parse counts, with operation log search |
| **System Settings** | Admin management of VIP parsing routes (JSON structured validation), user creation/deletion/password reset |
| **Feature Permissions** | Four permission codes (dashboard / routes / users / access): regular users can be granted read-only visibility of the dashboard, route list, user list and access logs; all write operations remain admin-only |
| **UX Details** | Onboarding guide (new users only), disclaimer page, light/dark themes, particle background, back-to-top, etc. |

Removed features: the paid single-video direct-link parsing and homepage batch extraction (the former 92k API pipeline has been fully removed). Historical records remain viewable in the Video Library.

## 🛠 Tech Stack

### Backend (`videohub/backend`)
- **Python 3.11+** / **FastAPI** — Asynchronous API framework
- **SQLAlchemy 2.0** — ORM, data persistence to SQLite (WAL mode)
- **pydantic-settings** — Environment configuration (`VIDEOHUB_` prefix, auto-written back to `.env`)
- **httpx** — Asynchronous HTTP client (streaming proxy, shared connection pool)
- **BCrypt** — User password hashing
- **itsdangerous** — Cookie session signing (SessionMiddleware)
- **Pillow** — Captcha image rendering (fonts cached by size)
- **qrcode** — TOTP provisioning QR code (rendered to a data URI via Pillow, used directly in an `<img>` tag)

### Frontend (`videohub/frontend`)
- **Vue 3** (Composition API) + **Vite 8**
- **Pinia 4** — State management (auth, theme, toast)
- **Vue Router 4** + **Axios**
- **ArtPlayer** — HTML5 player
- **three.js** — ParseHome particle background (dynamically imported, loaded on demand)
- **GSAP** — Page animations (`directives/vfx.js`, `views/parseVfx.js`)
- **@phosphor-icons/vue** — Icons
- CSS Variables light/dark theming

### Testing
- **pytest** + **respx** — Backend unit/integration tests (auth, rate limiting, registration, VIP, records, proxy, settings, access stats, dashboard, heartbeat, 2FA, feature permissions, account deletion, models, health check, plus security regressions `test_security_fixes` / `test_security_hardening`)

## 📁 Project Structure

```
vidio-project/
├── videohub/                    # App source + image build definition
│   ├── backend/                 # FastAPI Backend
│   │   ├── app/
│   │   │   ├── api/             # Routing Layer (access, auth, dashboard, deps, heartbeat, parse, records, settings, stream, visits)
│   │   │   ├── models/          # SQLAlchemy Models (User, Record+Caption, Setting, AccessLog, RecoveryCode)
│   │   │   ├── services/        # Business Modules (access_log, auth, captcha, client_ip, password_tier, permissions, platform, presence, proxy, ratelimit, settings, totp, urlguard)
│   │   │   ├── config.py        # Environment Configuration and Secret/Password Persistence
│   │   │   ├── database.py      # Database Engine and Session (WAL + busy_timeout)
│   │   │   └── main.py          # App Entry, Lifecycle (idempotent column migrations for legacy DBs), SPA Static Hosting
│   │   ├── tests/               # pytest Test Suite (incl. security regressions test_security_fixes / test_security_hardening)
│   │   ├── scripts/             # Ops Scripts (user_passwd.py password reset, scrape_vip_routes.py route scraping)
│   │   ├── static/              # Frontend Build Output (vite build target; not committed)
│   │   ├── .env.example         # Backend Environment Template (copy to .env)
│   │   └── pyproject.toml
│   ├── frontend/                # Vue 3 Frontend
│   │   ├── src/
│   │   │   ├── api/             # Axios Instance Wrapper
│   │   │   ├── components/      # Common Components (VhAurora, VhParticleField, VhOnboarding, VhPopover…, dashboard/ sub-components)
│   │   │   ├── stores/          # Pinia State (auth, theme, toast)
│   │   │   ├── router/          # Vue Router Configuration
│   │   │   ├── styles/          # Theme Tokens and Global Styles (light/dark)
│   │   │   ├── utils/           # passwordTier.js (same rules as backend), permissions.js (permission codes synced with backend)
│   │   │   ├── views/           # Pages (Dashboard, Disclaimer, Library, Login, ParseHome, Player, Settings)
│   │   │   └── main.js
│   │   └── vite.config.js       # dev proxy /api → :8000; build output to backend/static
│   ├── Dockerfile               # Image build (multi-stage: frontend build + backend runtime); build context is this dir
│   ├── .dockerignore            # Build-context filters (must sit alongside the Dockerfile in videohub/)
│   ├── docs/                    # Password tier spec, etc.
│   └── README.md                # Backend day-to-day usage notes (Chinese)
├── Docker/                      # Deployment orchestration layer (build context points back to ../videohub)
│   ├── docker-compose.yml       # App + Cloudflare named tunnel
│   ├── deploy-docker.bat        # Windows one-click build/update script (reads domain & keys from Docker/.env)
│   ├── .env                     # Local secrets & PUBLIC_URL (gitignored, never committed)
│   ├── .env.example             # Template for .env (copy it and fill in)
│   └── README-Docker.md         # Docker deployment guide (domain / tunnel / .env setup)
├── .gitignore                   # Single root-level ignore file
├── LICENSE                      # MIT License
├── README.md                    # Chinese doc
└── README.en.md                 # English doc
```

## 🚀 Quick Start

### Local development (manual start)
```bash
# Backend (port 8000; run from the repo root — uvicorn occupies this terminal)
cd videohub/backend
python -m venv .venv && .venv\Scripts\activate   # Linux/macOS: source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend (port 5173, /api auto-proxied to 8000) — open a SECOND terminal, from the repo root
cd videohub/frontend
npm install
npm run dev
```
- Dev URL: http://localhost:5173 (Vite proxy) or the backend at http://127.0.0.1:8000
- For public access use the Docker + Cloudflare tunnel deployment below; direct LAN exposure makes real-client-IP rate limiting and logs unreliable

### Default Account

| Role | Username | Password |
|------|--------|------|
| Admin | `admin` | No default password: a 12-character random password is auto-generated on first startup and written back to `backend/.env` (`VIDEOHUB_ADMIN_PASSWORD=`); the startup log points to that location |

- Reset (run inside `videohub/backend`): `python scripts/user_passwd.py reset admin <new-password>`
- You can also set the `VIDEOHUB_ADMIN_PASSWORD` environment variable before the first startup

## 📖 Usage Guide

### Login / Register
- New users must pass a one-time captcha check and password tier validation (scoring: length + character categories minus consecutive/repeat penalties; at least 8 characters and reaching the minimum tier "Bronze"; the tier — Bronze ~ King — is shown in real time during registration; weak-password blacklist hits are capped at Bronze; full rules in `videohub/docs/密码段位说明书.md`)
- Username rules: 3-32 characters, starting with a letter, only letters/digits/underscores, availability check before registration
- Anti-abuse rate limiting (see "Security & Rate Limiting" below)

### Two-Factor Authentication (2FA / TOTP)
- Entry in the top-right account menu: get a secret (scan the QR code or enter the `otpauth://` URI manually) → confirm with one 6-digit code to enable → 10 one-time recovery codes are shown (plaintext returned only once; you must confirm they are saved)
- Once enabled, login requires "password + TOTP code (or recovery code)"; TOTP failures are metered into the same three-level rate limiting as password failures
- RFC 6238 compliant (30s step / SHA1 / 6 digits), works with Google / Microsoft Authenticator, 1Password, etc.; tolerates ±1 step clock drift, consumed steps are monotonically rejected (replay protection)
- Recovery codes use the XXXX-XXXX format (confusion-free alphabet); only salted SHA-256 hashes are stored, each is single-use
- Disabling requires double confirmation with "login password + TOTP code (or recovery code)"; the secret and all recovery codes are wiped on disable

### Account Deletion
- Regular users can self-delete from the account menu: login password re-confirmation required (per-user rate limit, only failures counted)
- Deletion permanently removes the account and all its parse records (captions cleaned via FK cascade); access logs are anonymized but remain searchable by username snapshot
- Admin accounts cannot self-delete (prevents an unmanaged system); contact the maintainer instead

### VIP Video Parsing
- Paste a long-video link (Bilibili/Tencent Video/Youku/iQIYI/Mango TV) and select a parsing route
- When returning to the parse page, a supported platform link in the clipboard is auto-detected and filled in (only for the platforms above; other clipboard content is ignored; a newly copied link overrides the old one)
- On success you enter the player page: iframe embedded playback, with "open in new window" offered when a route disallows embedding
- If a route fails, simply parse again with another route; admins can add/remove routes or set a default in Settings

### Video Library
- Filter by platform/source type, search by title keyword, paginated browsing (20 items/page by default)
- Delete, batch delete and title editing; record data is isolated per user
- Video streams and cover images of history records are loaded via the backend streaming proxy

### Admin Functions
- **Data Dashboard**: KPIs, visit/parse trends, platform share, user ranking, recent activity, system status (DB size, tunnel flag, real-time online count); visible to admins by default, can also be granted read-only to regular users
- **System Settings**: VIP parsing route management (7 built-in; refresh from Niudh by running `python scripts/scrape_vip_routes.py merge` inside `videohub/backend`)
- **User Management**: Create/delete users, reset regular users' passwords, tick feature permissions (see below)
- **Feature Permissions**: permission codes dashboard / routes / users / access; granting means **read-only visibility** of the corresponding page/list; all write operations (route edits, user create/delete, password resets) remain admin-only, unknown permission codes are rejected by a whitelist
- **Access Statistics**: Per-user recent/today/historical visits and parse counts, operation log search

## ⚙️ Environment Variables (Backend)

All variables use the `VIDEOHUB_` prefix and can be set via environment variables or `backend/.env`:

| Variable | Description | Default Value |
|------|------|--------|
| `VIDEOHUB_ADMIN_PASSWORD` | Initial admin password (effective only when the account is first created) | Auto-generated on first startup and written back to `.env` |
| `VIDEOHUB_SECRET_KEY` | Session signing secret | Auto-generated on first startup and written back to `.env` |
| `VIDEOHUB_STATIC_DIR` | Frontend static assets directory | `backend/static` |
| `VIDEOHUB_DB_URL` | Database connection string | `sqlite:///./videohub.db` |
| `VIDEOHUB_HOST` | Server bind address | `0.0.0.0` |
| `VIDEOHUB_PORT` | Server port | `8000` |
| `VIDEOHUB_UPSTREAM_TIMEOUT` | Upstream proxy request timeout (seconds) | `300` |
| `VIDEOHUB_LOG_DIR` | Access log directory | `backend/logs` |
| `VIDEOHUB_COOKIE_SECURE` | Session cookie HTTPS-only transmission (set `1` for public tunnel deployment) | `false` |

> The full settings model is in `videohub/backend/app/config.py`; `VIDEOHUB_STATIC_DIR` and `VIDEOHUB_LOG_DIR` bypass the Settings model and are read directly from the environment in `app/main.py` and `app/services/access_log.py` respectively.

## 🔒 Security & Rate Limiting

> New security controls must ship with attack-scenario regression tests; new rate limiters must be registered in `videohub/backend/tests/conftest.py::_reset_limiters`.

- **Real client IP**: public traffic is forwarded through the cloudflared tunnel; the backend reads the real visitor IP from `CF-Connecting-IP` (`app/services/client_ip.py`), so rate limiting and logs are unaffected by the proxy
- Three-level login failure limiting: ① IP dimension — max 10 failed attempts per IP within 10 minutes, then 429 (successful logins don't count); ② account dimension — cross-IP failure aggregation; from the 20th failure a captcha challenge is required before password verification (blocks distributed brute force via proxy pools while avoiding the "anyone can lock a victim account with 20 failures" DoS); ③ 50 failures within 10 minutes temporarily locks the account, auto-unlocking as the window slides out
- Registration anti-abuse: max 10 registration calls per IP within 10 minutes; successful registrations spaced ≥ 60 seconds and max 3 accounts per hour
- Username availability check: max 30 requests per IP per minute, preventing username enumeration
- Captcha issuance: max 30 per IP per minute (rendering is CPU-heavy, protects the unauthenticated endpoint); visit-count reporting limited to 30/min per user (prevents DB flooding)
- Captcha is single-use; answers generated with the `secrets` module; passwords are BCrypt-hashed; session cookies are signed (HttpOnly, HTTPS-only transmission in public deployments)
- **TOTP 2FA (S19)**: secrets and recovery codes always generated via `secrets`, compared with `hmac.compare_digest`; recovery codes stored only as salted SHA-256, single-use; TOTP codes replay-rejected via a monotonic `last_step`; TOTP failures are metered the same way as password failures
- **Password change logs out everywhere**: sessions carry a password fingerprint (`pw_pv`); after a self-service change or admin reset, old sessions on other devices become invalid immediately
- **Destructive-operation gates**: password change requires the old password (the only in-session password verification gate, per-user failure limiting); self-deletion requires password re-confirmation + per-user rate limiting; admins cannot self-delete
- **Read-only permission boundary**: `require_perm` only gates read endpoint visibility; write endpoints always require `require_admin`; permission codes are whitelist-validated, unknown codes rejected
- **Proxy target validation**: before streaming proxy, internal/loopback/link-local/CGNAT addresses are rejected (`app/services/urlguard.py`), preventing legacy records from being used as an SSRF springboard
- Admin account protection: the API refuses to delete admins or reset admin passwords (prevents lateral takeover between admins); admin password changes go through the personal endpoint
- Deleting a user or self-deletion automatically anonymizes their access logs (user_id cleared); logs remain searchable by username snapshot; log fields strip newlines to prevent forging
- Rate-limit bucket keys are canonicalized via `rate_limit_key` (IPv6 → /64) to prevent rotating interface identifiers from resetting counters; logs still record the full IP

## 🧪 Testing & Delivery Gates

Run the full suite with the interpreter that has backend dependencies installed (`.venv\Scripts\python.exe` on Windows, `.venv/bin/python` on Linux):

```bash
cd videohub/backend
./.venv/Scripts/python.exe -m pytest tests/ -q                # full suite must be green
./.venv/Scripts/python.exe -m pytest tests/test_auth.py -v    # run the auth module only
```

Coverage: auth (login/register/password change/captcha/three-level rate limiting), username availability check, password tier scoring, platform identification, VIP parsing and embed pre-check, record CRUD and ownership permissions, streaming proxy (Range/403/410), system settings and user management, feature permissions, access statistics, dashboard aggregation, heartbeat & online count, TOTP 2FA and recovery codes, account-deletion cascade cleanup, models, health check, plus security regressions (`test_security_fixes` / `test_security_hardening` covering known attack scenarios with positive and negative cases). New security controls must ship with attack-scenario regression tests; new rate limiters must be registered in `tests/conftest.py::_reset_limiters`.

## 📦 Deployment

### Docker + Cloudflare tunnel (Recommended)

The app container binds **only `127.0.0.1:8000`**; all public traffic is forwarded through a Cloudflare named tunnel (`cloudflared` container), so the host opens no inbound port and does not need cloudflared installed locally. Full details live in [`Docker/README-Docker.md`](Docker/README-Docker.md).

**All secrets and the fixed domain go in `Docker/.env` (gitignored, never committed; copy [`Docker/.env.example`](Docker/.env.example) to `Docker/.env` and fill it in):**

```ini
VIDEOHUB_SECRET_KEY=<random session-signing secret, e.g. openssl rand -hex 32>
TUNNEL_TOKEN=<Cloudflare Zero Trust tunnel token, starts with eyJ>
PUBLIC_URL=https://<your-domain>.kdns.fr
# Optional: leave empty to auto-generate a random admin password on first start
VIDEOHUB_ADMIN_PASSWORD=
```

**Setting up the domain:**

1. **Get a domain** — your own, or a free second-level domain (e.g. KataBump `xxx.kdns.fr`, which is on the Public Suffix List and can be NS-delegated to Cloudflare).
2. **Add it to Cloudflare** — add the Site and change its nameservers at your registrar to Cloudflare's (the free plan is enough).
3. **Create the tunnel, copy the token** — Zero Trust dashboard → Networks → Tunnels → create a connector, copy the `eyJ…` token into `TUNNEL_TOKEN`.
4. **Configure the Public Hostname** — add a hostname on that tunnel with `Service` = `http://drone-test:8000` (**the container name, not localhost**).
5. **Set PUBLIC_URL and deploy** — write the final domain into `PUBLIC_URL` in `.env`, then double-click `Docker/deploy-docker.bat` to build and start.

Notes:

- `PUBLIC_URL` is used only by `deploy-docker.bat` for connectivity probing and address archiving (written to a local `tunnel-url.txt`); **to change the domain, just edit `.env` — no need to touch the script or the containers**.
- After a code update, double-click `deploy-docker.bat` again: it rebuilds the image and restarts the container; the data volume and domain are unchanged.
- The repository contains no real domain or token; the `<your-domain>.kdns.fr` values in `docker-compose.yml` and the docs are **placeholders** — replace them with your own configuration.

### Manual / self-hosted reverse proxy
1. Optionally copy `videohub/backend/.env.example` to `videohub/backend/.env` and fill it in (works without it too: the signing key and admin password are auto-generated on first start)
2. Build the frontend with `npm run build` (output to `backend/static`)
3. FastAPI serves the static directory automatically with SPA fallback (`VIDEOHUB_STATIC_DIR` can override)
4. Prefer starting with `uvicorn app.main:app --host 127.0.0.1 --port 8000` behind a reverse proxy / HTTPS; **never expose `0.0.0.0` directly to the public network** — the origin should only be reachable via the tunnel or reverse proxy.

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## 📞 Feedback

If you have any questions or suggestions, welcome to submit an Issue or Pull Request.
