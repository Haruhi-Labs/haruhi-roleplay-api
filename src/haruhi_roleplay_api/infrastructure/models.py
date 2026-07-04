"""Backward-compatible model provider exports."""

from haruhi_roleplay_api.infrastructure.model_provider_factory import (
    ProviderFactorySpec,
    build_model_router,
)
from haruhi_roleplay_api.infrastructure.model_registry import (
    ModelAliasConfig,
    ModelProviderConfig,
    ModelProviderSettings,
)

__all__ = [
    "ModelAliasConfig",
    "ModelProviderConfig",
    "ModelProviderSettings",
    "ProviderFactorySpec",
    "build_model_router",
]
