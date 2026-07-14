"""访问令牌存储端口。"""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain.access_token import (
    AccessToken,
    AccessTokenRequestLog,
    AccessTokenUsageOverview,
    AdminAuditLog,
    IssuedAccessToken,
)


class AccessTokenStore(Protocol):
    def create_token(
        self,
        *,
        app_id: str,
        name: str,
        quota_tokens: int | None,
        daily_quota_tokens: int | None = None,
        weekly_quota_tokens: int | None = None,
        expires_at: str | None = None,
    ) -> IssuedAccessToken:
        """创建绑定单一 app 的令牌，明文密钥只能通过本次返回。"""

    def authenticate(self, secret: str) -> AccessToken | None:
        """校验令牌；无效、已吊销或过期时返回 None。"""

    def list_tokens(self) -> tuple[AccessToken, ...]:
        """列举令牌的安全摘要。"""

    def get_token(self, token_id: str) -> AccessToken:
        """读取一个令牌的安全摘要。"""

    def revoke_token(self, token_id: str) -> AccessToken:
        """吊销令牌。"""

    def update_quota(
        self,
        token_id: str,
        *,
        quota_tokens: int | None,
    ) -> AccessToken:
        """修改总 Token 额度；None 表示不限额。"""

    def update_quotas(
        self,
        token_id: str,
        *,
        quota_tokens: int | None,
        daily_quota_tokens: int | None,
        weekly_quota_tokens: int | None,
    ) -> AccessToken:
        """同时修改生命周期、每日和每周 Token 额度。"""

    def ensure_quota_available(self, token_id: str) -> AccessToken:
        """确认令牌仍有模型 Token 额度，否则抛出稳定错误。"""

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

    def list_all_request_logs(
        self,
        *,
        limit: int = 50,
    ) -> tuple[AccessTokenRequestLog, ...]:
        """按时间倒序读取所有服务令牌的请求日志。"""

    def usage_overview(self, *, days: int = 30) -> AccessTokenUsageOverview:
        """聚合指定时间窗口内的整体、逐服务和逐路由用量。"""

    def record_admin_event(
        self,
        *,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        request_id: str,
        status_code: int,
        error_code: str | None = None,
    ) -> AdminAuditLog:
        """记录管理员动作摘要，不保存请求正文或敏感值。"""

    def list_admin_events(self, *, limit: int = 100) -> tuple[AdminAuditLog, ...]:
        """按时间倒序读取管理员审计事件。"""
