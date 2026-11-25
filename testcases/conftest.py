import json
import uuid
from typing import Any, Dict, List

import allure
import pytest

from api.account_api import AccountAPI
from api.http_client import HttpClient
from api.login_api import LoginAPI
from api.register_api import RegisterAPI
from utils.logger import get_logger
from utils.redaction import mask_sensitive
from utils.token import extract_token

logger = get_logger("fixtures")


class CleanupError(RuntimeError):
    """账号清理失败，用于在 pytest teardown 中明确反馈。"""


@pytest.fixture(scope="session")
def register_api(http_client):
    return RegisterAPI(http_client)


@pytest.fixture(scope="session")
def login_api(http_client):
    return LoginAPI(http_client)


@pytest.fixture(scope="session")
def account_api(http_client):
    return AccountAPI(http_client)


def _attach_cleanup_result(result: Dict[str, Any]) -> None:
    allure.attach(
        json.dumps(
            mask_sensitive(result),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        name="cleanup_result",
        attachment_type=allure.attachment_type.JSON,
    )


def _cleanup_account(config: Dict[str, Any], email: str, password: str) -> None:
    """删除账号；删除不可用时退化为登出。失败必须抛给 teardown。"""
    result: Dict[str, Any] = {
        "email": email,
        "status": "failed",
        "stage": "init",
        "reason": "",
    }
    with allure.step(f"清理账号: {email}"):
        client = HttpClient(
            base_url=config["base_url"],
            timeout=config["timeout"],
        )
        try:
            login_response = LoginAPI(client).login(
                {"email": email, "password": password}
            )
            if login_response.status_code != 200:
                result.update(
                    stage="login",
                    reason=f"登录失败 status={login_response.status_code}",
                )
                _attach_cleanup_result(result)
                raise CleanupError(result["reason"])

            token = extract_token(login_response.json())
            if not token:
                result.update(stage="login", reason="登录响应没有 Token")
                _attach_cleanup_result(result)
                raise CleanupError(result["reason"])

            account = AccountAPI(client)
            delete_response = None
            delete_reason = ""
            try:
                delete_response = account.delete_profile(token)
            except Exception as exc:
                delete_reason = f"删除异常: {exc!r}"
                logger.exception("清理删除异常：email=%s", email)

            if delete_response is not None and delete_response.status_code in (200, 204):
                result.update(
                    status="deleted",
                    stage="delete",
                    reason=f"删除成功 status={delete_response.status_code}",
                )
                _attach_cleanup_result(result)
                logger.info("清理完成：删除账号 %s", email)
                return

            if delete_response is None:
                delete_reason = delete_reason or "删除请求未返回响应"
            elif not delete_reason:
                delete_reason = f"删除失败 status={delete_response.status_code}"

            logger.warning("删除账号失败，尝试登出：email=%s，%s", email, delete_reason)
            try:
                logout_response = account.logout(token)
            except Exception as exc:
                result.update(
                    status="failed",
                    stage="logout",
                    reason=f"{delete_reason}; 登出异常: {exc!r}",
                )
                _attach_cleanup_result(result)
                logger.exception("清理登出异常：email=%s", email)
                raise CleanupError(result["reason"]) from exc

            if logout_response.status_code in (200, 204, 401):
                result.update(
                    status="logout_fallback",
                    stage="logout",
                    reason=(
                        f"{delete_reason}; 登出降级 status={logout_response.status_code}"
                    ),
                )
                _attach_cleanup_result(result)
                logger.warning(
                    "清理降级：删除失败但登出完成 email=%s，status=%s",
                    email,
                    logout_response.status_code,
                )
                return

            result.update(
                status="failed",
                stage="logout",
                reason=(
                    f"{delete_reason}; 登出失败 status={logout_response.status_code}"
                ),
            )
            _attach_cleanup_result(result)
            raise CleanupError(result["reason"])
        except CleanupError:
            raise
        except Exception as exc:
            result.update(stage="exception", reason=f"清理异常: {exc!r}")
            _attach_cleanup_result(result)
            logger.exception("清理账号异常：email=%s", email)
            raise CleanupError(result["reason"]) from exc
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

    try:
        _cleanup_account(config, user["email"], user["password"])
    except Exception as exc:
        logger.error("登录模块测试账号清理失败：email=%s，%s", user["email"], exc)
        pytest.fail(f"登录模块测试账号清理失败: {exc}", pytrace=False)


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

    errors: List[str] = []
    for user in created:
        try:
            _cleanup_account(config, user["email"], user["password"])
        except Exception as exc:
            errors.append(f"{user['email']}: {exc}")

    if errors:
        message = "注册账号清理失败:\n" + "\n".join(errors)
        logger.error(message)
        pytest.fail(message, pytrace=False)
