from typing import Dict, Optional

import requests

from api.http_client import HttpClient


class AccountAPI:
    """账号清理相关接口：删除当前账号或使其会话失效。"""

    def __init__(self, client: HttpClient):
        self.client = client

    @staticmethod
    def _auth(token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def me(
        self,
        token: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        """获取当前用户资料；headers 用于无凭据/错误方案等鉴权负向场景。"""
        request_headers = dict(headers) if headers is not None else {}
        if token:
            request_headers.update(self._auth(token))
        return self.client.get("/api/v1/auth/me", headers=request_headers)

    def delete_profile(self, token: str) -> requests.Response:
        return self.client.delete(
            "/api/v1/users/profile",
            headers=self._auth(token),
        )

    def logout(self, token: str) -> requests.Response:
        return self.client.post(
            "/api/v1/auth/logout",
            headers=self._auth(token),
        )
