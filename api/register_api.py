from typing import Any, Dict

import requests

from api.http_client import HttpClient


class RegisterAPI:
    """注册接口封装：只发送请求，不做断言。"""

    def __init__(self, client: HttpClient):
        self.client = client

    def register(
        self,
        payload: Dict[str, Any],
        rate_limit: bool = True,
    ) -> requests.Response:
        return self.register_raw(json=payload, rate_limit=rate_limit)

    def register_raw(
        self,
        rate_limit: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        """供缺失 Body、畸形 JSON、错误媒体类型等请求级用例使用。"""
        return self.client.post(
            "/api/v1/auth/register",
            rate_limit=rate_limit,
            **kwargs,
        )
