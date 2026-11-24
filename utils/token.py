from typing import Any, Optional


def extract_token(payload: Any) -> Optional[str]:
    """从常见凭证字段或嵌套结构中提取 Token，兼容 access_token/token/accessToken。"""
    if isinstance(payload, dict):
        for key in ("access_token", "token", "accessToken"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        for value in payload.values():
            token = extract_token(value)
            if token:
                return token
    elif isinstance(payload, list):
        for item in payload:
            token = extract_token(item)
            if token:
                return token
    return None
