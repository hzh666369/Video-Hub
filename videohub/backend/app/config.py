from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIDEOHUB_", env_file=str(_ENV_FILE), extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = ""
    admin_password: str = ""  # 为空则首次建管理员时自动生成随机密码并写回 .env
    db_url: str = "sqlite:///./videohub.db"
    upstream_timeout: int = 300
    # 会话 Cookie 是否仅 HTTPS 传输（公网隧道全 HTTPS 时置 1；本地/局域网 http 访问保持 0）
    cookie_secure: bool = False


settings = Settings()


def persist_env(key: str, value: str) -> None:
    """把一项配置写回 .env（存在则覆盖），供自动生成的密钥/密码持久化使用。"""
    lines = []
    if _ENV_FILE.exists():
        lines = _ENV_FILE.read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


if not settings.secret_key:
    import secrets

    settings.secret_key = secrets.token_hex(32)
    persist_env("VIDEOHUB_SECRET_KEY", settings.secret_key)
