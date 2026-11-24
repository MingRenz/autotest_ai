import re
import uuid
from typing import Any, Dict, List, Optional

import yaml

from utils.config import load_config
from utils.paths import TESTDATA_DIR

_PLACEHOLDER = re.compile(r"\$\{([A-Z0-9_]+)\}")
_RUN_ID = uuid.uuid4().hex[:10]


def _context() -> Dict[str, str]:
    config = load_config()
    return {
        "RUN_ID": _RUN_ID,
        "BASE_URL": config["base_url"],
        "ADMIN_EMAIL": config["admin"]["email"],
        "ADMIN_PASSWORD": config["admin"]["password"],
        # 明显超长邮箱样本，不用于断言具体长度上限。
        "LONG_EMAIL": "a" * 300 + "@example.com",
    }


def _substitute(value: Any, context: Dict[str, str]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match) -> str:
            key = match.group(1)
            if key not in context:
                raise KeyError(f"测试数据中存在未定义的占位符: ${{{key}}}")
            return context[key]

        return _PLACEHOLDER.sub(replace, value)
    if isinstance(value, list):
        return [_substitute(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, context) for key, item in value.items()}
    return value


def load_cases(file_name: str, group: Optional[str] = None) -> List[Dict[str, Any]]:
    """读取 YAML 中 cases，按 group 过滤并替换配置占位符。"""
    with (TESTDATA_DIR / file_name).open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}

    cases = content.get("cases", [])
    if group:
        cases = [case for case in cases if case.get("group") == group]
    if not cases:
        raise ValueError(f"{file_name} 中没有 group={group!r} 的测试数据")

    case_ids = [case.get("id") for case in cases]
    if any(not case_id for case_id in case_ids) or len(case_ids) != len(set(case_ids)):
        raise ValueError(f"{file_name} 中的用例 id 缺失或重复")

    context = _context()
    return [_substitute(case, context) for case in cases]
