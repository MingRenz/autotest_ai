import re
from typing import Any
from urllib.parse import unquote_plus

# 日志和 Allure 附件统一走这里，避免密码、Token、Cookie 泄露。
_SENSITIVE_KEYWORDS = (
    "password",
    "token",
    "authorization",
    "cookie",
    "secret",
    "credential",
)
_FORM_PAIR = re.compile(r"(?i)(^|[?&\s])([^=&\s]+)=([^&]*)")


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).lower()
    return any(keyword in normalized for keyword in _SENSITIVE_KEYWORDS)


def _mask_form_text(text: str) -> str:
    """脱敏 application/x-www-form-urlencoded 或 query string 的敏感值。"""
    if "=" not in text:
        return text

    def replace(match: re.Match) -> str:
        separator, key, _ = match.group(1), match.group(2), match.group(3)
        if _is_sensitive_key(unquote_plus(key)):
            return f"{separator}{key}=***"
        return match.group(0)

    return _FORM_PAIR.sub(replace, text)


def mask_sensitive(value: Any) -> Any:
    """递归脱敏 dict/list，并处理文本中的 Bearer Token 和表单字段。"""
    if isinstance(value, dict):
        return {
            key: ("***" if _is_sensitive_key(key) else mask_sensitive(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [mask_sensitive(item) for item in value]
    if isinstance(value, str):
        masked = _mask_form_text(value)
        return re.sub(
            r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
            r"\1***",
            masked,
        )
    return value
