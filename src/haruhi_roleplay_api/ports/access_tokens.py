"""访问令牌存储端口。"""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain.access_token import (
    AccessToken,
    AccessTokenRequestLog,
    IssuedAccessToken,
)


class AccessTokenStore(Protocol):
    def create_token(
        self,
        *,
        name: str,
        quota_tokens: int | None,
        expires_at: str | None = None,
    ) -> IssuedAccessToken:
        """创建令牌，明文密钥只能通过本次返回。"""

    def authenticate(self, secret: str) -> AccessToken | None:
        """校验令牌；无效、已吊销或过期时返回 None。"""

    def list_tokens(self) -> tuple[AccessToken, ...]:
        """列举令牌的安全摘要。"""

    def get_token(self, token_id: str) -> AccessToken:
        """读取一个令牌的安全摘要。"""

    def revoke_token(self, token_id: str) -> AccessToken:
        """吊销令牌。"""

    def record_request(
        self,
        *,
        token_id: str,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        duration_ms: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        error_code: str | None = None,
    ) -> AccessTokenRequestLog:
        """记录一次令牌请求，不保存请求正文或令牌明文。"""

    def list_request_logs(
        self,
        token_id: str,
        *,
        limit: int = 50,
    ) -> tuple[AccessTokenRequestLog, ...]:
        """按时间倒序读取令牌请求日志。"""
