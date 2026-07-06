"""Backend context provider factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from haruhi_roleplay_api.adapters.backend_context import FakeBackendContextProvider
from haruhi_roleplay_api.domain import DTOValidationError
from haruhi_roleplay_api.ports import BackendContextProvider


@dataclass(frozen=True, kw_only=True)
class BackendContextProviderSettings:
    provider: str = "none"
    allowed_sources: tuple[str, ...] = ("user_profile", "game_state")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "BackendContextProviderSettings":
        return cls(
            provider=env.get("BACKEND_CONTEXT_PROVIDER", "none"),
            allowed_sources=_csv_tuple(
                env.get("BACKEND_CONTEXT_ALLOWED_SOURCES"),
                default=("user_profile", "game_state"),
            ),
        )


def build_backend_context_provider(
    settings: BackendContextProviderSettings,
) -> BackendContextProvider | None:
    provider = settings.provider.strip().lower()
    if provider in {"", "none", "disabled", "off"}:
        return None
    if provider == "fake":
        return FakeBackendContextProvider(
            allowed_sources=settings.allowed_sources,
        )
    raise DTOValidationError(
        "BACKEND_CONTEXT_PROVIDER must be none or fake"
    )


def build_backend_context_provider_from_env(
    env: Mapping[str, str],
) -> BackendContextProvider | None:
    return build_backend_context_provider(BackendContextProviderSettings.from_env(env))


def _csv_tuple(
    value: str | None,
    *,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    if value is None or not value.strip():
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())
