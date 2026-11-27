import os

import yaml

from utils.paths import CONFIG_FILE


def load_config() -> dict:
    """读取默认配置和环境配置，应用环境变量覆盖。"""
    with CONFIG_FILE.open(encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    env = os.getenv("APP_ENV", "local")
    if env == "default" or env not in raw:
        raise ValueError(f"APP_ENV={env!r} 未在 {CONFIG_FILE} 中定义")

    defaults, overrides = raw.get("default", {}), raw[env]
    config = {**defaults, **overrides, "env": env}
    admin = {**defaults.get("admin", {}), **overrides.get("admin", {})}
    limits = {**defaults.get("rate_limit", {}), **overrides.get("rate_limit", {})}
    config["base_url"] = str(os.getenv("API_BASE_URL") or config["base_url"]).rstrip("/")
    config["timeout"] = float(os.getenv("API_TIMEOUT") or config.get("timeout", 10))
    admin["email"] = os.getenv("ADMIN_EMAIL") or admin.get("email")
    admin["password"] = os.getenv("ADMIN_PASSWORD") or admin.get("password")
    enabled = os.getenv("RATE_LIMIT_ENABLED")
    if enabled:
        limits["enabled"] = enabled.strip().lower() in ("1", "true", "yes", "on")
    limits["window_seconds"] = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS") or limits.get("window_seconds", 60))
    limits["buffer_seconds"] = float(os.getenv("RATE_LIMIT_BUFFER_SECONDS") or limits.get("buffer_seconds", 0.5))
    for endpoint in ("register", "login", "me"):
        key = f"{endpoint}_per_minute"
        limits[key] = int(os.getenv(f"RATE_LIMIT_{key.upper()}") or limits.get(key, 0))
    return {**config, "admin": admin, "rate_limit": limits}
