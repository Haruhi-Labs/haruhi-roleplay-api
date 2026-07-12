"""访问令牌管理用例。"""

from __future__ import annotations

from haruhi_roleplay_api.domain import AccessToken, IssuedAccessToken
from haruhi_roleplay_api.ports import AccessTokenStore


class CreateAccessToken:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(
        self,
        *,
        name: str,
        quota_tokens: int | None,
        expires_at: str | None,
    ) -> IssuedAccessToken:
        return self._store.create_token(
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
