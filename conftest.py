import pytest

from api.http_client import HttpClient
from api.login_api import LoginAPI
from utils.config import load_config
from utils.rate_limit import build_rate_limit_guard
from utils.token import extract_token


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def rate_limiter(config):
    # 各角色和临时客户端共用服务端配额。
    return build_rate_limit_guard(config["rate_limit"])


@pytest.fixture(scope="session")
def http_client(config, rate_limiter):
    client = HttpClient(config["base_url"], config["timeout"], rate_limiter=rate_limiter)
    yield client
    client.close()


@pytest.fixture(scope="session")
def admin_token(config, rate_limiter):
    guest = HttpClient(config["base_url"], config["timeout"], rate_limiter=rate_limiter)
    try:
        admin = config["admin"]
        response = LoginAPI(guest).login(
            {"email": admin["email"], "password": admin["password"]}
        )
        response.raise_for_status()
        token = extract_token(response.json())
        assert token, "管理员登录未返回可用的 Bearer Token"
        return token
    finally:
        guest.close()


@pytest.fixture(scope="session")
def admin_client(config, admin_token, rate_limiter):
    client = HttpClient(
        config["base_url"], config["timeout"], token=admin_token, rate_limiter=rate_limiter
    )
    yield client
    client.close()
