import allure
import pytest

from utils.token import extract_token

LOGIN_EMAIL = "$LOGIN_EMAIL"
LOGIN_PASSWORD = "$LOGIN_PASSWORD"
LOGIN_EMAIL_UPPER = "$LOGIN_EMAIL_UPPER"
LOGIN_EMAIL_SPACED = "$LOGIN_EMAIL_SPACED"


def _build_payload(case, user):
    """标准化 input 字典 + delete_fields，统一替换账号占位符。"""
    payload = dict(case["input"])
    for field in case.get("delete_fields", []):
        payload.pop(field, None)

    for key, value in payload.items():
        if value == LOGIN_EMAIL:
            payload[key] = user["email"]
        elif value == LOGIN_PASSWORD:
            payload[key] = user["password"]
        elif value == LOGIN_EMAIL_UPPER:
            payload[key] = user["email"].upper()
        elif value == LOGIN_EMAIL_SPACED:
            payload[key] = f" {user['email']} "
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
            f"{title}: 错误定位未指向 {error_field}: {detail}"
        )


def _error_text(response) -> str:
    body = response.json()
    for key in ("detail", "message", "error"):
        value = body.get(key) if isinstance(body, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _assert_success(response, account_api, payload, expected, title):
    assert response.status_code == 200, f"{title}: {response.text}"
    body = response.json()
    assert isinstance(body, dict), f"{title}: 登录成功响应必须是 JSON object"

    leaked_fields = [
        field for field in expected.get("forbidden_fields", []) if field in body
    ]
    assert not leaked_fields, f"{title}: 登录响应泄露敏感字段: {leaked_fields}"

    token = extract_token(body)
    assert token, f"{title}: 登录成功必须返回可用的 Bearer Token"

    me_response = account_api.me(token)
    assert me_response.status_code == 200, f"{title}: /me 返回失败 {me_response.text}"
    profile = me_response.json()
    assert profile["email"].strip().lower() == payload["email"].strip().lower(), (
        f"{title}: /me 返回邮箱与登录账号不一致"
    )
    return profile


@pytest.mark.datafile("login.yaml", group="standard")
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("普通用户登录与字段/认证校验")
@allure.severity(allure.severity_level.CRITICAL)
def test_login(login_api, account_api, test_login_user, case):
    allure.dynamic.title(case["title"])
    payload = _build_payload(case, test_login_user)

    with allure.step("发送登录请求"):
        response = login_api.login(
            payload,
            rate_limit=case["expected"]["status"] != 422,
        )

    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response.text}"
    )
    if case["expected"]["status"] == 200:
        _assert_success(response, account_api, payload, case["expected"], case["title"])
    else:
        assert extract_token(response.json()) is None, (
            f"{case['title']}: 登录失败不得返回 Token"
        )
        _assert_error(response, case["expected"], case["title"])


@pytest.mark.datafile("login.yaml", group="error_consistency")
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("认证错误信息一致性")
def test_login_error_consistency(login_api, test_login_user, case):
    allure.dynamic.title(case["title"])
    wrong_password_response = login_api.login(
        {
            "email": test_login_user["email"],
            "password": case["wrong_password"],
        }
    )
    unknown_user_response = login_api.login(
        {
            "email": case["unknown_email"],
            "password": test_login_user["password"],
        }
    )

    for response in (wrong_password_response, unknown_user_response):
        assert response.status_code == case["expected"]["status"], (
            f"{case['title']}: {response.text}"
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


@pytest.mark.datafile("login.yaml", group="admin")
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("管理员登录")
def test_login_admin(login_api, account_api, case):
    allure.dynamic.title(case["title"])
    payload = case["input"]

    with allure.step("管理员登录"):
        response = login_api.login(payload)

    profile = _assert_success(
        response, account_api, payload, case["expected"], case["title"]
    )
    assert profile["role"].strip().lower() in {"admin", "administrator"}, (
        f"{case['title']}: /me 返回角色不是管理员，实际为 {profile['role']!r}"
    )


@pytest.mark.datafile("login.yaml", group="request_invalid")
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("请求构造异常")
def test_login_request_invalid(login_api, case):
    allure.dynamic.title(case["title"])
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
        f"{case['title']}: {response.text}"
    )
    assert extract_token(response.json()) is None, f"{case['title']}: 不得返回 Token"
    _assert_error(response, case["expected"], case["title"])


@pytest.mark.datafile("login.yaml", group="mass_assignment")
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("额外字段与角色隔离")
def test_login_mass_assignment(login_api, account_api, test_login_user, case):
    allure.dynamic.title(case["title"])
    payload = _build_payload(case, test_login_user)

    with allure.step("登录并访问 /me"):
        response = login_api.login(payload)
        assert response.status_code == case["expected"]["status"], (
            f"{case['title']}: {response.text}"
        )
        token = extract_token(response.json())
        assert token, f"{case['title']}: 登录成功必须返回 Token"
        profile = account_api.me(token).json()

    assert profile["role"] != "admin", f"{case['title']}: 额外 role 字段不应提权"


@pytest.mark.datafile("login.yaml", group="security")
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("注入与脚本字符")
def test_login_security(login_api, test_login_user, case):
    allure.dynamic.title(case["title"])
    payload = _build_payload(case, test_login_user)

    with allure.step("发送恶意字符登录请求"):
        response = login_api.login(
            payload,
            rate_limit=case["expected"]["status"] != 422,
        )

    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response.text}"
    )
    assert extract_token(response.json()) is None, f"{case['title']}: 不得返回 Token"
    _assert_error(response, case["expected"], case["title"])


@pytest.mark.datafile("login.yaml", group="auth_guard")
@allure.title("{case[title]}")
@allure.feature("登录模块")
@allure.story("受保护接口鉴权")
def test_login_auth_guard(account_api, case):
    allure.dynamic.title(case["title"])

    with allure.step("使用异常 Authorization 访问 /me"):
        response = account_api.me(headers=case["headers"])

    assert response.status_code == case["expected"]["status"], (
        f"{case['title']}: {response.text}"
    )
    _assert_error(response, case["expected"], case["title"])
