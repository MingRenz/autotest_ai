from uuid import uuid4

import allure
import pytest

from utils.data_loader import load_cases
from utils.redaction import mask_sensitive, response_for_report
from utils.token import extract_token


def _build_payload(case, user):
    payload = {"email": user["email"], "password": user["password"]}
    payload.update(case.get("input", {}))
    for field in case.get("delete_fields", []):
        payload.pop(field)

    if case.get("email_transform") == "uppercase":
        payload["email"] = payload["email"].upper()
    elif case.get("email_transform") == "surround_with_spaces":
        payload["email"] = f" {payload['email']} "

    email = payload.get("email")
    if isinstance(email, str) and "{run_id}" in email:
        payload["email"] = email.replace("{run_id}", uuid4().hex[:10])
    return payload


def _assert_error(response, expected, title):
    body = response.json()
    assert isinstance(body, dict), f"{title}: 错误响应必须是 JSON object"
    assert any(key in body for key in ("detail", "message", "error")), (
        f"{title}: 错误响应必须包含明确错误信息"
    )
    error_field = expected.get("error_field")
    if error_field:
        detail = body.get("detail")
        assert isinstance(detail, list), f"{title}: 422 响应应包含 detail 数组"
        assert any(error_field in item.get("loc", []) for item in detail), (
            f"{title}: 错误定位未指向 {error_field}: {mask_sensitive(detail)}"
        )


def _error_text(response) -> str:
    body = response.json()
    for key in ("detail", "message", "error"):
        value = body.get(key) if isinstance(body, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _assert_success(response, account_api, payload, expected, title):
    assert response.status_code == 200, f"{title}: {response_for_report(response)}"
    body = response.json()
    assert isinstance(body, dict), f"{title}: 登录成功响应必须是 JSON object"

    leaked_fields = [
        field for field in expected.get("forbidden_fields", []) if field in body
    ]
    assert not leaked_fields, f"{title}: 登录响应泄露敏感字段: {leaked_fields}"

    token = extract_token(body)
    assert token, f"{title}: 登录成功必须返回可用的 Bearer Token"

    me_response = account_api.me(token)
    assert me_response.status_code == 200, (
        f"{title}: /me 返回失败 {response_for_report(me_response)}"
    )
    profile = me_response.json()
    assert profile["email"].strip().lower() == payload["email"].strip().lower(), (
        f"{title}: /me 返回邮箱与登录账号不一致"
    )
    return profile


@pytest.mark.parametrize(
    "case",
    load_cases("login.yaml", group="standard"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("普通用户登录与字段/认证校验")
@allure.severity(allure.severity_level.CRITICAL)
def test_login(login_api, authenticated_account_api, test_login_user, case):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    payload = _build_payload(case, test_login_user)

    with allure.step("发送登录请求"):
        response = login_api.login(
            payload,
            rate_limit=case["expected"]["status"] != 422,
        )

    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response_for_report(response)}"
    )
    if case["expected"]["status"] == 200:
        _assert_success(
            response, authenticated_account_api, payload, case["expected"], case["title"]
        )
    else:
        assert extract_token(response.json()) is None, (
            f"{case['title']}: 登录失败不得返回 Token"
        )
        _assert_error(response, case["expected"], case["title"])


@pytest.mark.parametrize(
    "case",
    load_cases("login.yaml", group="error_consistency"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("认证错误信息一致性")
def test_login_error_consistency(login_api, test_login_user, case):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    wrong_password_response = login_api.login(
        {
            "email": test_login_user["email"],
            "password": case["wrong_password"],
        }
    )
    unknown_user_response = login_api.login(
        {
            "email": case["unknown_email"].replace("{run_id}", uuid4().hex[:10]),
            "password": test_login_user["password"],
        }
    )

    for response in (wrong_password_response, unknown_user_response):
        assert response.status_code == case["expected"]["status"], (
            f"{case['title']}: {response_for_report(response)}"
        )
        assert extract_token(response.json()) is None, (
            f"{case['title']}: 认证失败不得返回 Token"
        )

    wrong_message = _error_text(wrong_password_response)
    unknown_message = _error_text(unknown_user_response)
    assert wrong_message, f"{case['title']}: 错误密码响应缺少错误信息"
    assert unknown_message, f"{case['title']}: 不存在用户响应缺少错误信息"
    assert wrong_message == unknown_message, (
        f"{case['title']}: 错误信息可用于枚举账号: "
        f"wrong={wrong_message!r}, unknown={unknown_message!r}"
    )


@pytest.mark.parametrize(
    "case",
    load_cases("login.yaml", group="admin"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("管理员登录")
def test_login_admin(login_api, authenticated_account_api, config, case):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    admin = config["admin"]
    payload = {"email": admin["email"], "password": admin["password"]}

    with allure.step("管理员登录"):
        response = login_api.login(payload)

    profile = _assert_success(
        response, authenticated_account_api, payload, case["expected"], case["title"]
    )
    assert profile["role"].strip().lower() in {"admin", "administrator"}, (
        f"{case['title']}: /me 返回角色不是管理员，实际为 {profile['role']!r}"
    )


@pytest.mark.parametrize(
    "case",
    load_cases("login.yaml", group="request_invalid"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("请求构造异常")
def test_login_request_invalid(login_api, case):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    request = case["request"]
    headers = {"Content-Type": request["content_type"]}
    kwargs = {"headers": headers}
    if request.get("body") is not None:
        kwargs["data"] = request["body"]

    with allure.step("发送异常登录请求"):
        response = login_api.login_raw(
            rate_limit=case["expected"]["status"] != 422,
            **kwargs,
        )

    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response_for_report(response)}"
    )
    assert extract_token(response.json()) is None, f"{case['title']}: 不得返回 Token"
    _assert_error(response, case["expected"], case["title"])


@pytest.mark.parametrize(
    "case",
    load_cases("login.yaml", group="mass_assignment"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("额外字段与角色隔离")
def test_login_mass_assignment(login_api, authenticated_account_api, test_login_user, case):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    payload = _build_payload(case, test_login_user)

    with allure.step("登录并访问 /me"):
        response = login_api.login(payload)
        assert response.status_code == case["expected"]["status"], (
            f"{case['title']}: {response_for_report(response)}"
        )
        token = extract_token(response.json())
        assert token, f"{case['title']}: 登录成功必须返回 Token"
        profile = authenticated_account_api.me(token).json()

    assert profile["role"] != "admin", f"{case['title']}: 额外 role 字段不应提权"


@pytest.mark.parametrize(
    "case",
    load_cases("login.yaml", group="security"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("注入与脚本字符")
def test_login_security(login_api, test_login_user, case):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])
    payload = _build_payload(case, test_login_user)

    with allure.step("发送恶意字符登录请求"):
        response = login_api.login(
            payload,
            rate_limit=case["expected"]["status"] != 422,
        )

    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response_for_report(response)}"
    )
    assert extract_token(response.json()) is None, f"{case['title']}: 不得返回 Token"
    _assert_error(response, case["expected"], case["title"])


@pytest.mark.parametrize(
    "case",
    load_cases("login.yaml", group="auth_guard"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("受保护接口鉴权")
def test_login_auth_guard(account_api, case):
    allure.dynamic.title(case["title"])
    allure.dynamic.parameter("case", case["id"])

    with allure.step("使用异常 Authorization 访问 /me"):
        response = account_api.me(headers=case["headers"])

    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response_for_report(response)}"
    )
    _assert_error(response, case["expected"], case["title"])
