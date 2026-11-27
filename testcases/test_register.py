from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import allure
import pytest

from api.http_client import HttpClient
from api.register_api import RegisterAPI
from utils.data_loader import load_cases
from utils.redaction import mask_sensitive, response_for_report
from utils.token import extract_token


def _build_input(case, base):
    payload = {**base, **case.get("input", {})}
    for field in case.get("delete_fields", []):
        payload.pop(field)

    if "email_local_length" in case:
        payload["email"] = "a" * case["email_local_length"] + "@example.com"
    email = payload.get("email")
    if isinstance(email, str) and "{run_id}" in email:
        payload["email"] = email.replace("{run_id}", uuid4().hex[:10])
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
            f"{title}: 错误定位未指向 {error_field}: {mask_sensitive(detail)}"
        )


def _track_if_created(response, payload, cleanup):
    if response.status_code < 300:
        cleanup.append(payload.copy())


@pytest.mark.parametrize(
    "case",
    load_cases("register.yaml", group="success"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("合法注册")
@allure.severity(allure.severity_level.CRITICAL)
def test_register_success(
    register_api, login_api, random_register_data, register_cleanup, case
):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    payload = _build_input(case, random_register_data)

    with allure.step("发送注册请求"):
        response = register_api.register(payload)

    _track_if_created(response, payload, register_cleanup)
    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response_for_report(response)}"
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
            f"{case['title']}: 新账号登录失败 {response_for_report(login_response)}"
        )
        assert extract_token(login_response.json()), (
            f"{case['title']}: 新账号登录未返回 Token"
        )


@pytest.mark.parametrize(
    "case",
    load_cases("register.yaml", group="field_validation"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("字段校验")
def test_register_field_validation(
    register_api, login_api, random_register_data, register_cleanup, case
):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    payload = _build_input(case, random_register_data)

    with allure.step("发送字段异常注册请求"):
        response = register_api.register(
            payload,
            rate_limit=case["expected"]["status"] != 422,
        )

    _track_if_created(response, payload, register_cleanup)
    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response_for_report(response)}"
    )
    _assert_error(response, case["expected"], case["title"])

    if case["expected"].get("verify_not_created"):
        login_response = login_api.login(
            {"email": payload["email"], "password": payload["password"]}
        )
        assert login_response.status_code == 401, (
            f"{case['title']}: 负向注册不应创建可登录账号，实际登录 {response_for_report(login_response)}"
        )
        assert extract_token(login_response.json()) is None, (
            f"{case['title']}: 负向注册后登录不应返回 Token"
        )


@pytest.mark.parametrize(
    "case",
    load_cases("register.yaml", group="request_invalid"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("请求构造异常")
def test_register_request_invalid(register_api, case):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    request = case["request"]
    headers = {"Content-Type": request["content_type"]}
    kwargs = {"headers": headers}
    if request.get("body") is not None:
        kwargs["data"] = request["body"].replace("{run_id}", uuid4().hex[:10])

    with allure.step("发送异常注册请求"):
        response = register_api.register_raw(
            rate_limit=case["expected"]["status"] != 422,
            **kwargs,
        )

    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response_for_report(response)}"
    )
    _assert_error(response, case["expected"], case["title"])


@pytest.mark.parametrize(
    "case",
    load_cases("register.yaml", group="duplicate"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("重复注册")
def test_register_duplicate(
    register_api, login_api, random_register_data, register_cleanup, case
):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    payload = _build_input(case, random_register_data)

    with allure.step("首次注册"):
        first_response = register_api.register(payload)
    assert first_response.status_code == 201, (
        f"{case['title']}: 首次注册失败 {response_for_report(first_response)}"
    )
    register_cleanup.append(payload.copy())

    with allure.step("重复注册"):
        duplicate_response = register_api.register(payload)
    status_matches = duplicate_response.status_code == case["expected"]["status"]

    with allure.step("验证首次账号仍可登录"):
        original_login = login_api.login(
            {"email": payload["email"], "password": payload["password"]}
        )
    assert original_login.status_code == 200, (
        f"{case['title']}: 重复注册后原账号登录失败 {response_for_report(original_login)}"
    )
    assert extract_token(original_login.json()), (
        f"{case['title']}: 原账号登录未返回 Token"
    )

    assert status_matches, (
        f"{case['title']}: 重复注册状态码错误，实际 {duplicate_response.status_code} "
        f"{response_for_report(duplicate_response)}"
    )
    _assert_error(duplicate_response, case["expected"], case["title"])


@pytest.mark.parametrize(
    "case",
    load_cases("register.yaml", group="concurrent"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("并发重复注册")
def test_register_concurrent(config, rate_limiter, random_register_data, register_cleanup, case):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    payload = _build_input(case, random_register_data)

    def send_once():
        client = HttpClient(config["base_url"], config["timeout"], rate_limiter=rate_limiter)
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
        f"{case['title']}: 状态码异常 {[response_for_report(response) for response in responses]}"
    )
    conflict = next(response for response in responses if response.status_code == 409)
    _assert_error(conflict, case["expected"], case["title"])


@pytest.mark.parametrize(
    "case",
    load_cases("register.yaml", group="mass_assignment"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("额外字段与角色隔离")
def test_register_mass_assignment(
    register_api,
    login_api,
    authenticated_account_api,
    random_register_data,
    register_cleanup,
    case,
):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    payload = _build_input(case, random_register_data)

    with allure.step("携带 role 注册"):
        response = register_api.register(payload)
    _track_if_created(response, payload, register_cleanup)
    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response_for_report(response)}"
    )

    login_response = login_api.login(
        {"email": payload["email"], "password": payload["password"]}
    )
    token = extract_token(login_response.json())
    assert token, f"{case['title']}: 注册后登录未返回 Token"
    profile = authenticated_account_api.me(token).json()
    assert profile["role"] != "admin", f"{case['title']}: 额外 role 字段不应提权"


@pytest.mark.parametrize(
    "case",
    load_cases("register.yaml", group="security"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("注册模块")
@allure.story("XSS 与 SQLi 字符")
def test_register_security(
    register_api,
    login_api,
    authenticated_account_api,
    random_register_data,
    register_cleanup,
    case,
):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    payload = _build_input(case, random_register_data)

    with allure.step("提交恶意字符注册"):
        response = register_api.register(payload)

    _track_if_created(response, payload, register_cleanup)
    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response_for_report(response)}"
    )

    field = case["expected"].get("verify_field")
    if field:
        login_response = login_api.login(
            {"email": payload["email"], "password": payload["password"]}
        )
        token = extract_token(login_response.json())
        assert token, f"{case['title']}: 注册后登录未返回 Token"
        profile = authenticated_account_api.me(token).json()
        assert profile[field] == payload[field], (
            f"{case['title']}: /me 返回字段值被改变"
        )
