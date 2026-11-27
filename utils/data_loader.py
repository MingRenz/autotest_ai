from typing import Optional

import yaml

from utils.paths import TESTDATA_DIR


def load_cases(file_name: str, group: Optional[str] = None) -> list[dict]:
    """读取 YAML 用例，按需选取指定分组。"""
    with (TESTDATA_DIR / file_name).open(encoding="utf-8") as file:
        cases = yaml.safe_load(file)["cases"]

    ids = [case.get("id") for case in cases]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError(f"{file_name} 中的用例 id 缺失或重复")

    selected = [case for case in cases if case.get("group") == group] if group else cases
    if not selected:
        raise ValueError(f"{file_name} 中没有 group={group!r} 的测试数据")
    return selected
