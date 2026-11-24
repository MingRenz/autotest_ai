from typing import Any, Dict

import requests

from api.http_client import HttpClient


class LoginAPI:
    """登录接口封装：只负责发送请求，不做断言和业务编排。"""

    def __init__(self, client: HttpClient):
        self.client = client

    def login(
        self,
        payload: Dict[str, Any],
        rate_limit: bool = True,
    ) -> requests.Response:
        return self.login_raw(json=payload, rate_limit=rate_limit)

    def login_raw(self, rate_limit: bool = True, **kwargs: Any) -> requests.Response:
        """供缺失 Body、畸形 JSON、错误媒体类型等请求级用例使用。"""
        return self.client.post(
            "/api/v1/auth/login",
            rate_limit=rate_limit,
            **kwargs,
        )
