import uuid
from typing import Any, Dict, List

import pytest

from api.account_api import AccountAPI
from api.http_client import HttpClient
from api.login_api import LoginAPI
from api.register_api import RegisterAPI
from utils.logger import get_logger
from utils.token import extract_token

logger = get_logger("fixtures")


@pytest.fixture(scope="session")
def register_api(http_client):
    return RegisterAPI(http_client)


@pytest.fixture(scope="session")
def login_api(http_client):
    return LoginAPI(http_client)


@pytest.fixture(scope="session")
def account_api(http_client):
    return AccountAPI(http_client)


def _cleanup_account(config: Dict[str, Any], email: str, password: str) -> None:
    """尽力删除账号；删除不可用时退化为登出，任何异常都不能影响后续用例。"""
    client = HttpClient(
        base_url=config["base_url"],
        timeout=config["timeout"],
    )
    try:
        login_response = LoginAPI(client).login(
            {"email": email, "password": password}
        )
        if login_response.status_code != 200:
            logger.warning(
                "清理跳过：无法登录待清理账号 %s，status=%s",
                email,
                login_response.status_code,
            )
            return

        token = extract_token(login_response.json())
        if not token:
            logger.warning("清理跳过：登录响应无 Token，email=%s", email)
            return

        account = AccountAPI(client)
        delete_response = account.delete_profile(token)
        if delete_response.status_code in (200, 204):
            logger.info(
                "清理完成：删除账号 %s，status=%s",
                email,
                delete_response.status_code,
            )
            return

        logger.warning(
            "删除账号失败，尝试登出：email=%s，status=%s",
            email,
            delete_response.status_code,
        )
        logout_response = account.logout(token)
        if logout_response.status_code not in (200, 204, 401):
            logger.warning(
                "登出也失败：email=%s，status=%s",
                email,
                logout_response.status_code,
            )
    except Exception:
        logger.exception("清理账号异常：email=%s", email)
    finally:
        client.close()


@pytest.fixture(scope="module")
def test_login_user(config, register_api):
    """登录模块共用一个稳定账号，模块结束后再清理。"""
    suffix = uuid.uuid4().hex[:10]
    user = {
        "first_name": "Qa",
        "last_name": f"Login{suffix[:4]}",
        "email": f"qa.login.{suffix}@example.com",
        "password": f"Qa!{suffix}#2026",
        "phone": "13800138000",
    }
    response = register_api.register(user)
    assert response.status_code == 201, (
        f"登录测试账号创建失败: {response.status_code} {response.text}"
    )

    yield user
    _cleanup_account(config, user["email"], user["password"])


@pytest.fixture()
def random_register_data():
    """每个注册用例独立生成一组唯一数据。"""
    suffix = uuid.uuid4().hex[:10]
    return {
        "first_name": "Qa",
        "last_name": f"Reg{suffix[:4]}",
        "email": f"qa.register.{suffix}@example.com",
        "password": f"Qa!{suffix}#2026",
        "phone": "13800138000",
    }


@pytest.fixture()
def register_cleanup(config):
    """用例把成功创建的账号登记进来，teardown 统一清理。"""
    created: List[Dict[str, Any]] = []
    yield created

    for user in created:
        _cleanup_account(config, user["email"], user["password"])
