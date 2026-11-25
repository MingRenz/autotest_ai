import sys
from pathlib import Path

# 允许从项目根目录或任意工作目录运行 pytest。
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import allure
import pytest

from api.http_client import HttpClient
from utils.config import load_config
from utils.data_loader import load_cases
from utils.logger import LOGGER_NAMES, AllureLogHandler, get_logger
from utils.token import extract_token


def pytest_generate_tests(metafunc):
    """按 @pytest.mark.datafile 加载 YAML；只把可读 case_id 暴露为参数。"""
    marker = metafunc.definition.get_closest_marker("datafile")
    if marker is None or "case_id" not in metafunc.fixturenames:
        return

    file_name = marker.args[0]
    group = marker.kwargs.get("group")
    cases = load_cases(file_name, group=group)
    ids = [
        f"{case['id']}_{case['title']}" if case.get("title") else case["id"]
        for case in cases
    ]
    metafunc.parametrize(
        "case_id",
        [case["id"] for case in cases],
        ids=ids,
    )


@pytest.fixture()
def case(request, case_id):
    """按 case_id 从当前测试的 datafile 中取回完整数据。"""
    marker = request.node.get_closest_marker("datafile")
    if marker is None:
        pytest.fail("使用 case fixture 的测试必须声明 @pytest.mark.datafile")

    cases = load_cases(marker.args[0], group=marker.kwargs.get("group"))
    for item in cases:
        if item["id"] == case_id:
            return item
    pytest.fail(f"未找到测试数据: {case_id}")


@pytest.fixture(autouse=True)
def capture_test_logs():
    """按测试用例收集自定义 logger，结束后作为独立 Allure 文本附件。"""
    handler = AllureLogHandler()
    loggers = [get_logger(name) for name in LOGGER_NAMES]
    for logger in loggers:
        logger.addHandler(handler)

    yield

    for logger in loggers:
        logger.removeHandler(handler)
    allure.attach(
        handler.text() or "no logs captured",
        name="test_log",
        attachment_type=allure.attachment_type.TEXT,
    )


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def http_client(config):
    client = HttpClient(
        base_url=config["base_url"],
        timeout=config["timeout"],
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def admin_token(config):
    """用无 Token 的临时客户端登录，仅把 Token 交给 admin_client 使用。"""
    guest = HttpClient(
        base_url=config["base_url"],
        timeout=config["timeout"],
    )
    try:
        response = guest.post(
            "/api/v1/auth/login",
            json={
                "email": config["admin"]["email"],
                "password": config["admin"]["password"],
            },
        )
        response.raise_for_status()
        token = extract_token(response.json())
        assert token, "管理员登录未返回可用的 Bearer Token"
        return token
    finally:
        guest.close()


@pytest.fixture(scope="session")
def admin_client(config, admin_token):
    """独立 session + 管理员 Token，避免和 guest/user 客户端互相污染。"""
    client = HttpClient(
        base_url=config["base_url"],
        timeout=config["timeout"],
        token=admin_token,
    )
    yield client
    client.close()
