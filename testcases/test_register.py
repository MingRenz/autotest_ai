from concurrent.futures import ThreadPoolExecutor

import allure
import pytest

from api.http_client import HttpClient
from api.register_api import RegisterAPI
from utils.token import extract_token

REGISTER_FIRST_NAME = "$REGISTER_FIRST_NAME"
REGISTER_LAST_NAME = "$REGISTER_LAST_NAME"
REGISTER_EMAIL = "$REGISTER_EMAIL"
REGISTER_PASSWORD = "$REGISTER_PASSWORD"
REGISTER_PHONE = "$REGISTER_PHONE"


def _build_input(case, base):
    """标准化 input + delete_fields；占位符在发请求前替换为本次唯一数据。"""
    payload = dict(case["input"])
    for field in case.get("delete_fields", []):
        payload.pop(field, None)

    replacements = {
        REGISTER_FIRST_NAME: base["first_name"],
        REGISTER_LAST_NAME: base["last_name"],
        REGISTER_EMAIL: base["email"],
        REGISTER_PASSWORD: base["password"],
        REGISTER_PHONE: base["phone"],
    }
    for key, value in list(payload.items()):
        if value in replacements:
            payload[key] = replacements[value]
    return payload


def _assert_error(response, expected, title):
    body = response.json()
    assert isinstance(body, dict), f"{title}: 错误响应必须是 JSON object"
    assert any(key in body for key in ("detail", "message", "error")), (
        f"{title}: 注册失败响应必须包含明确错误信息"
    )
    error_field = expected.get("error_field")
    if error_field:
        detail = body.get("detail")
        assert isinstance(detail, list), f"{title}: 422 响应应包含 detail 数组"
        assert any(error_field in item.get("loc", []) for item in detail), (
            f"{title}: 错误定位未指向 {error_field}: {detail}"
        )


def _track_if_created(response, payload, cleanup):
    if response.status_code < 300:
        cleanup.append(payload.copy())


@pytest.mark.datafile("register.yaml", group="success")
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("合法注册")
@allure.severity(allure.severity_level.CRITICAL)
def test_register_success(
    register_api, login_api, random_register_data, register_cleanup, case
):
    allure.dynamic.title(case["title"])
    payload = _build_input(case, random_register_data)

    with allure.step("发送注册请求"):
        response = register_api.register(payload)

    _track_if_created(response, payload, register_cleanup)
    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response.text}"
    )

    body = response.json()
    assert isinstance(body, dict)
    for field in ("password", "password_hash", "hashed_password"):
        assert field not in body, f"{case['title']}: 响应泄露敏感字段 {field}"

    if case["expected"].get("verify_login"):
        login_response = login_api.login(
            {"email": payload["email"], "password": payload["password"]}
        )
        assert login_response.status_code == 200, (
            f"{case['title']}: 新账号登录失败 {login_response.text}"
        )
        assert extract_token(login_response.json()), (
            f"{case['title']}: 新账号登录未返回 Token"
        )


@pytest.mark.datafile("register.yaml", group="field_validation")
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("字段校验")
def test_register_field_validation(
    register_api, random_register_data, register_cleanup, case
):
    allure.dynamic.title(case["title"])
    payload = _build_input(case, random_register_data)

    with allure.step("发送字段异常注册请求"):
        response = register_api.register(
            payload,
            rate_limit=case["expected"]["status"] != 422,
        )

    _track_if_created(response, payload, register_cleanup)
    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response.text}"
    )
    _assert_error(response, case["expected"], case["title"])


@pytest.mark.datafile("register.yaml", group="request_invalid")
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("请求构造异常")
def test_register_request_invalid(register_api, case):
    allure.dynamic.title(case["title"])
    request = case["request"]
    headers = {"Content-Type": request["content_type"]}
    kwargs = {"headers": headers}
    if request.get("body") is not None:
        kwargs["data"] = request["body"]

    with allure.step("发送异常注册请求"):
        response = register_api.register_raw(
            rate_limit=case["expected"]["status"] != 422,
            **kwargs,
        )

    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response.text}"
    )
    _assert_error(response, case["expected"], case["title"])


@pytest.mark.datafile("register.yaml", group="duplicate")
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("重复注册")
def test_register_duplicate(register_api, random_register_data, register_cleanup, case):
    allure.dynamic.title(case["title"])
    payload = _build_input(case, random_register_data)

    with allure.step("首次注册"):
        first_response = register_api.register(payload)
    assert first_response.status_code == 201, (
        f"{case['title']}: 首次注册失败 {first_response.text}"
    )
    register_cleanup.append(payload.copy())

    with allure.step("重复注册"):
        duplicate_response = register_api.register(payload)
    assert duplicate_response.status_code == case["expected"]["status"], (
        f"{case['title']}: {duplicate_response.text}"
    )
    _assert_error(duplicate_response, case["expected"], case["title"])


@pytest.mark.datafile("register.yaml", group="concurrent")
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("并发重复注册")
def test_register_concurrent(config, random_register_data, register_cleanup, case):
    allure.dynamic.title(case["title"])
    payload = _build_input(case, random_register_data)

    def send_once():
        client = HttpClient(config["base_url"], config["timeout"])
        try:
            return RegisterAPI(client).register(payload)
        finally:
            client.close()

    with allure.step("并发发送两次相同注册请求"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: send_once(), range(2)))

    if any(response.status_code < 300 for response in responses):
        register_cleanup.append(payload.copy())

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201, 409], (
        f"{case['title']}: 状态码异常 {[response.text for response in responses]}"
    )
    conflict = next(response for response in responses if response.status_code == 409)
    _assert_error(conflict, case["expected"], case["title"])


@pytest.mark.datafile("register.yaml", group="mass_assignment")
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("额外字段与角色隔离")
def test_register_mass_assignment(
    register_api, login_api, account_api, random_register_data, register_cleanup, case
):
    allure.dynamic.title(case["title"])
    payload = _build_input(case, random_register_data)

    with allure.step("携带 role 注册"):
        response = register_api.register(payload)
    _track_if_created(response, payload, register_cleanup)
    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response.text}"
    )

    login_response = login_api.login(
        {"email": payload["email"], "password": payload["password"]}
    )
    token = extract_token(login_response.json())
    assert token, f"{case['title']}: 注册后登录未返回 Token"
    profile = account_api.me(token).json()
    assert profile["role"] != "admin", f"{case['title']}: 额外 role 字段不应提权"


@pytest.mark.datafile("register.yaml", group="security")
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("XSS 与 SQLi 字符")
def test_register_security(
    register_api, login_api, account_api, random_register_data, register_cleanup, case
):
    allure.dynamic.title(case["title"])
    payload = _build_input(case, random_register_data)

    with allure.step("提交恶意字符注册"):
        response = register_api.register(payload)

    _track_if_created(response, payload, register_cleanup)
    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response.text}"
    )

    field = case["expected"].get("verify_field")
    if field:
        login_response = login_api.login(
            {"email": payload["email"], "password": payload["password"]}
        )
        token = extract_token(login_response.json())
        assert token, f"{case['title']}: 注册后登录未返回 Token"
        profile = account_api.me(token).json()
        assert profile[field] == payload[field], (
            f"{case['title']}: /me 返回字段值被改变"
        )
