import uuid

import pytest
import requests

from api.account_api import AccountAPI
from api.http_client import HttpClient
from api.login_api import LoginAPI
from api.register_api import RegisterAPI
from utils.logger import get_logger
from utils.redaction import response_for_report
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


@pytest.fixture()
def authenticated_account_api(config, rate_limiter):
    """用当前用例的独立会话携带登录返回的 Token。"""
    client = HttpClient(config["base_url"], config["timeout"], rate_limiter=rate_limiter)
    yield AccountAPI(client)
    client.close()


def _cleanup_account(config, rate_limiter, email, password):
    """删除测试账号，删除失败时尝试登出。"""
    client = HttpClient(config["base_url"], config["timeout"], rate_limiter=rate_limiter)
    try:
        login = LoginAPI(client).login({"email": email, "password": password})
        if login.status_code != 200:
            raise RuntimeError(f"清理前登录失败，HTTP {login.status_code}")
        token = extract_token(login.json())
        if not token:
            raise RuntimeError("清理前登录响应缺少 Token")

        account = AccountAPI(client)
        try:
            status = account.delete_profile(token).status_code
            if status in (200, 204):
                logger.info("已删除测试账号 %s", email)
                return
            delete_error = f"HTTP {status}"
        except requests.RequestException as exc:
            delete_error = type(exc).__name__

        logger.warning("删除账号 %s 失败（%s），尝试登出", email, delete_error)
        status = account.logout(token).status_code
        if status not in (200, 204, 401):
            raise RuntimeError(f"删除失败（{delete_error}），登出返回 HTTP {status}")
        logger.warning("账号 %s 尚待清理，登出返回 HTTP %s", email, status)
    finally:
        client.close()


@pytest.fixture(scope="module")
def test_login_user(config, rate_limiter, register_api):
    """登录模块共用一个账号，模块结束后清理。"""
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
        f"登录测试账号创建失败（HTTP {response.status_code}）{response_for_report(response)}"
    )

    yield user

    try:
        _cleanup_account(config, rate_limiter, user["email"], user["password"])
    except Exception as exc:
        logger.error("登录模块测试账号 %s 清理失败，%s", user["email"], exc)
        pytest.fail(f"登录模块测试账号清理失败，{exc}", pytrace=False)


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
def register_cleanup(config, rate_limiter):
    """用例登记成功创建的账号，teardown 逐个清理。"""
    created = []
    yield created

    errors = []
    for user in created:
        try:
            _cleanup_account(config, rate_limiter, user["email"], user["password"])
        except Exception as exc:
            errors.append(f"{user['email']} 清理失败，{exc}")

    if errors:
        message = "注册账号清理失败\n" + "\n".join(errors)
        logger.error(message)
        pytest.fail(message, pytrace=False)
