import os
from copy import deepcopy
from functools import lru_cache
from typing import Any, Dict, Tuple

import yaml

from utils.paths import CONFIG_FILE

def _to_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


# 环境变量优先级高于 YAML；新增配置项时在这里登记即可。
_ENV_OVERRIDES: Tuple[Tuple[str, str, type], ...] = (
    ("API_BASE_URL", "base_url", str),
    ("API_TIMEOUT", "timeout", float),
    ("ADMIN_EMAIL", "admin.email", str),
    ("ADMIN_PASSWORD", "admin.password", str),
    ("RATE_LIMIT_ENABLED", "rate_limit.enabled", _to_bool),
    ("RATE_LIMIT_WINDOW_SECONDS", "rate_limit.window_seconds", float),
    ("RATE_LIMIT_REGISTER_PER_MINUTE", "rate_limit.register_per_minute", int),
    ("RATE_LIMIT_LOGIN_PER_MINUTE", "rate_limit.login_per_minute", int),
    ("RATE_LIMIT_ME_PER_MINUTE", "rate_limit.me_per_minute", int),
    ("RATE_LIMIT_BUFFER_SECONDS", "rate_limit.buffer_seconds", float),
)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _set_nested(config: Dict[str, Any], dotted_key: str, value: Any) -> None:
    target = config
    keys = dotted_key.split(".")
    for key in keys[:-1]:
        target = target.setdefault(key, {})
    target[keys[-1]] = value


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """加载 default + APP_ENV 对应配置，并应用环境变量覆盖。"""
    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    app_env = os.getenv("APP_ENV", "local")
    environments = {key: value for key, value in raw.items() if key != "default"}
    if app_env not in environments:
        raise ValueError(f"APP_ENV={app_env!r} 未在 {CONFIG_FILE} 中定义")

    config = _deep_merge(raw.get("default", {}), environments[app_env])
    config["env"] = app_env

    for env_name, dotted_key, caster in _ENV_OVERRIDES:
        env_value = os.getenv(env_name)
        if env_value is not None and env_value != "":
            _set_nested(config, dotted_key, caster(env_value))

    config["base_url"] = str(config["base_url"]).rstrip("/")
    config["timeout"] = float(config.get("timeout", 10))
    return config
