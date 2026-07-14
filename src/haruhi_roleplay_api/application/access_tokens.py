"""访问令牌管理用例。"""

from __future__ import annotations

from haruhi_roleplay_api.domain import (
    AccessToken,
    AccessTokenRequestLog,
    IssuedAccessToken,
    AccessTokenUsageOverview,
)
from haruhi_roleplay_api.ports import AccessTokenStore
from haruhi_roleplay_api.ports.access_tokens import QuotaUpdate, UNCHANGED_QUOTA


class CreateAccessToken:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(
        self,
        *,
        app_id: str,
        name: str,
        quota_tokens: int | None,
        daily_quota_tokens: int | None,
        weekly_quota_tokens: int | None,
        expires_at: str | None,
    ) -> IssuedAccessToken:
        return self._store.create_token(
            app_id=app_id,
            name=name,
            quota_tokens=quota_tokens,
            daily_quota_tokens=daily_quota_tokens,
            weekly_quota_tokens=weekly_quota_tokens,
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
        quota_tokens: QuotaUpdate = UNCHANGED_QUOTA,
        daily_quota_tokens: QuotaUpdate = UNCHANGED_QUOTA,
        weekly_quota_tokens: QuotaUpdate = UNCHANGED_QUOTA,
    ) -> AccessToken:
        return self._store.update_quotas(
            token_id,
            quota_tokens=quota_tokens,
            daily_quota_tokens=daily_quota_tokens,
            weekly_quota_tokens=weekly_quota_tokens,
        )


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


class ListAllAccessTokenRequestLogs:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(self, *, limit: int) -> tuple[AccessTokenRequestLog, ...]:
        return self._store.list_all_request_logs(limit=limit)


class GetAccessTokenUsageOverview:
    def __init__(self, store: AccessTokenStore) -> None:
        self._store = store

    def execute(self, *, days: int) -> AccessTokenUsageOverview:
        return self._store.usage_overview(days=days)
