import json
from typing import Any, Optional

import allure
import requests

from utils.logger import get_logger
from utils.rate_limit import get_rate_limit_guard
from utils.redaction import mask_sensitive


class HttpClient:
    """通用 HTTP 客户端：session 复用、Token 注入、base_url 拼接和 Allure 记录。"""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10,
        token: Optional[str] = None,
        logger=None,
        rate_limiter=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.logger = logger or get_logger("http")
        self.rate_limiter = rate_limiter or get_rate_limit_guard()

        if token:
            self.set_token(token)

    def set_token(self, token: str) -> None:
        """设置当前客户端的 Bearer Token；空值等价于清除。"""
        if not token:
            self.clear_token()
            return
        self.session.headers["Authorization"] = f"Bearer {token}"

    def clear_token(self) -> None:
        """清除当前客户端的鉴权头，不影响其他 HttpClient 实例。"""
        self.session.headers.pop("Authorization", None)

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _rate_limit_key(path: str) -> Optional[str]:
        normalized = path.rstrip("/")
        if normalized.endswith("/auth/register"):
            return "register"
        if normalized.endswith("/auth/login"):
            return "login"
        if normalized.endswith("/auth/me"):
            return "me"
        return None

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        use_rate_limit = kwargs.pop("rate_limit", True)
        if use_rate_limit:
            self.rate_limiter.wait(self._rate_limit_key(path))

        url = self._url(path)
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Accept", "application/json")
        kwargs["headers"] = headers
        kwargs.setdefault("timeout", self.timeout)
        request_body = kwargs.get("json", kwargs.get("data"))

        with allure.step(f"发送 {method.upper()} 请求: {url}"):
            self._attach_json(
                "request",
                {
                    "method": method.upper(),
                    "url": url,
                    "headers": headers,
                    "params": kwargs.get("params"),
                    "body": request_body,
                },
            )
            self.logger.info("REQUEST %s %s", method.upper(), url)

            try:
                response = self.session.request(method=method, url=url, **kwargs)
            except requests.RequestException as exc:
                self.logger.exception("REQUEST FAILED %s %s", method.upper(), url)
                self._attach_json("request_error", {"error": str(exc)})
                raise

            try:
                response_body: Any = response.json()
            except ValueError:
                response_body = response.text

            self._attach_json(
                "response",
                {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_body,
                },
            )
            self.logger.info(
                "RESPONSE %s %s -> %s (%.3fs)",
                method.upper(),
                url,
                response.status_code,
                response.elapsed.total_seconds(),
            )

        return response

    def _attach_json(self, name: str, payload: Any) -> None:
        allure.attach(
            json.dumps(
                mask_sensitive(payload),
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            name=name,
            attachment_type=allure.attachment_type.JSON,
        )

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        self.session.close()
