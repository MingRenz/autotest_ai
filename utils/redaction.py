import re
from typing import Any

# 日志和 Allure 附件统一走这里，避免密码、Token、Cookie 泄露。
_SENSITIVE_KEYWORDS = (
    "password",
    "token",
    "authorization",
    "cookie",
    "secret",
    "credential",
)


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).lower()
    return any(keyword in normalized for keyword in _SENSITIVE_KEYWORDS)


def mask_sensitive(value: Any) -> Any:
    """递归脱敏 dict/list；对文本中的 Bearer Token 也做替换。"""
    if isinstance(value, dict):
        return {
            key: ("***" if _is_sensitive_key(key) else mask_sensitive(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [mask_sensitive(item) for item in value]
    if isinstance(value, str):
        return re.sub(
            r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
            r"\1***",
            value,
        )
    return value
