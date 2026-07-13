"""访问令牌管理用例。"""

from __future__ import annotations

from haruhi_roleplay_api.domain import (
    AccessToken,
    AccessTokenRequestLog,
    IssuedAccessToken,
)
from haruhi_roleplay_api.ports import AccessTokenStore


class CreateAccessToken:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(
        self,
        *,
        app_id: str,
        name: str,
        quota_tokens: int | None,
        expires_at: str | None,
    ) -> IssuedAccessToken:
        return self._store.create_token(
            app_id=app_id,
            name=name,
            quota_tokens=quota_tokens,
            expires_at=expires_at,
        )


class ListAccessTokens:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(self) -> tuple[AccessToken, ...]:
        return self._store.list_tokens()


class GetAccessToken:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(self, token_id: str) -> AccessToken:
        return self._store.get_token(token_id)


class RevokeAccessToken:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(self, token_id: str) -> AccessToken:
        return self._store.revoke_token(token_id)


class UpdateAccessTokenQuota:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(
        self,
        token_id: str,
        *,
        quota_tokens: int | None,
    ) -> AccessToken:
        return self._store.update_quota(token_id, quota_tokens=quota_tokens)


class ListAccessTokenRequestLogs:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(
        self,
        token_id: str,
        *,
        limit: int,
    ) -> tuple[AccessTokenRequestLog, ...]:
        return self._store.list_request_logs(token_id, limit=limit)
