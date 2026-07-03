"""Model provider registry configuration and factories."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from haruhi_roleplay_api.adapters import (
    FakeModelProvider,
    LocalOpenAICompatibleModelProvider,
)
from haruhi_roleplay_api.application import (
    ModelAliasRoute,
    ModelProviderRegistryRouter,
)
from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.ports import ChatModelProvider, ChatModelRouter


@dataclass(frozen=True, kw_only=True)
class ModelProviderConfig:
    provider_id: str
    provider_type: str
    baseUrl: str | None = None
    timeoutMs: int = 60000
    apiKey: str | None = None
    providerName: str | None = None

    @classmethod
    def from_mapping(
        cls,
        provider_id: str,
        data: Mapping[str, Any],
    ) -> "ModelProviderConfig":
        provider_type = _string_value(
            data.get("type", data.get("provider_type", provider_id)),
            f"provider type for {provider_id}",
        )
        timeout_raw = data.get("timeout_ms", data.get("timeoutMs", 60000))
        return cls(
            provider_id=_require_non_empty(provider_id, "provider id"),
            provider_type=provider_type,
            baseUrl=_optional_string(data.get("base_url", data.get("baseUrl"))),
            timeoutMs=_int_value(timeout_raw, f"timeout_ms for {provider_id}"),
            apiKey=_optional_string(data.get("api_key", data.get("apiKey"))),
            providerName=_optional_string(
                data.get("provider_name", data.get("providerName"))
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ModelAliasConfig:
    alias: str
    provider_id: str
    model: str

    @classmethod
    def from_mapping(
        cls,
        alias: str,
        data: Mapping[str, Any],
    ) -> "ModelAliasConfig":
        return cls(
            alias=_require_non_empty(alias, "model alias"),
            provider_id=_string_value(data.get("provider"), f"provider for {alias}"),
            model=_string_value(data.get("model"), f"model for {alias}"),
        )


@dataclass(frozen=True, kw_only=True)
class ModelProviderSettings:
    defaultAlias: str
    providers: Mapping[str, ModelProviderConfig]
    aliases: Mapping[str, ModelAliasConfig]

    @classmethod
    def from_mapping(cls, data: Mapping[str, str]) -> "ModelProviderSettings":
        registry_json = data.get("MODEL_PROVIDER_REGISTRY")
        if registry_json is not None and registry_json.strip():
            return cls.from_registry_mapping(_json_mapping(registry_json))
        return cls.from_legacy_mapping(data)

    @classmethod
    def from_registry_mapping(
        cls,
        data: Mapping[str, Any],
    ) -> "ModelProviderSettings":
        providers_data = _mapping_value(data.get("providers"), "providers")
        aliases_data = _mapping_value(data.get("aliases"), "aliases")
        default_alias = _string_value(
            data.get("default_alias", data.get("defaultAlias")),
            "default_alias",
        )
        providers = {
            provider_id: ModelProviderConfig.from_mapping(
                provider_id,
                _mapping_value(provider_data, f"provider {provider_id}"),
            )
            for provider_id, provider_data in providers_data.items()
        }
        aliases = {
            alias: ModelAliasConfig.from_mapping(
                alias,
                _mapping_value(alias_data, f"alias {alias}"),
            )
            for alias, alias_data in aliases_data.items()
        }
        return cls(
            defaultAlias=default_alias,
            providers=providers,
            aliases=aliases,
        )

    @classmethod
    def from_legacy_mapping(cls, data: Mapping[str, str]) -> "ModelProviderSettings":
        provider_type = data.get("MODEL_PROVIDER", "fake")
        default_model = "fake-roleplay-model" if provider_type == "fake" else ""
        model = data.get("MODEL_NAME", default_model)
        alias = data.get("MODEL_ALIAS", model)
        provider_id = data.get("MODEL_PROVIDER_ID", _legacy_provider_id(provider_type))
        timeout_ms = _int_value(
            data.get("MODEL_TIMEOUT_MS", "60000"),
            "MODEL_TIMEOUT_MS",
        )
        provider_config = ModelProviderConfig(
            provider_id=provider_id,
            provider_type=provider_type,
            baseUrl=data.get("MODEL_BASE_URL"),
            timeoutMs=timeout_ms,
            apiKey=data.get("MODEL_API_KEY"),
            providerName=data.get("MODEL_PROVIDER_NAME"),
        )
        alias_config = ModelAliasConfig(
            alias=_require_non_empty(alias, "MODEL_ALIAS"),
            provider_id=provider_id,
            model=_require_non_empty(model, "MODEL_NAME"),
        )
        return cls(
            defaultAlias=alias_config.alias,
            providers={provider_id: provider_config},
            aliases={alias_config.alias: alias_config},
        )

    @classmethod
    def from_env(cls) -> "ModelProviderSettings":
        return cls.from_mapping(os.environ)


def build_model_router(settings: ModelProviderSettings) -> ChatModelRouter:
    providers = {
        provider_id: _build_provider(config)
        for provider_id, config in settings.providers.items()
    }
    aliases = {
        alias: ModelAliasRoute(
            alias=alias_config.alias,
            provider_id=alias_config.provider_id,
            provider_model=alias_config.model,
        )
        for alias, alias_config in settings.aliases.items()
    }
    return ModelProviderRegistryRouter(
        providers=providers,
        aliases=aliases,
        default_alias=settings.defaultAlias,
    )


def _build_provider(config: ModelProviderConfig) -> ChatModelProvider:
    provider_type = _normalized_provider_type(config.provider_type)
    if provider_type == "fake":
        return FakeModelProvider()
    if provider_type in {
        "local",
        "openai_compatible",
        "local_openai_compatible",
        "ollama",
    }:
        if not config.baseUrl:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=(
                    f"MODEL_BASE_URL is required for model provider "
                    f"{config.provider_id}."
                ),
            )
        if config.timeoutMs <= 0:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message="MODEL_TIMEOUT_MS must be positive.",
            )
        return LocalOpenAICompatibleModelProvider(
            base_url=config.baseUrl,
            timeout_seconds=config.timeoutMs / 1000,
            api_key=config.apiKey,
            provider_name=_provider_debug_name(config, provider_type),
        )
    raise AppError(
        code=ErrorCode.MODEL_PROVIDER_ERROR,
        message=f"MODEL_PROVIDER is not supported: {config.provider_type}",
    )


def _provider_debug_name(
    config: ModelProviderConfig,
    provider_type: str,
) -> str | None:
    if config.providerName:
        return config.providerName
    if provider_type == "ollama":
        return "ollama"
    return None


def _legacy_provider_id(provider_type: str) -> str:
    provider_type = _normalized_provider_type(provider_type)
    if provider_type == "fake":
        return "fake"
    if provider_type == "ollama":
        return "ollama"
    return "local"


def _normalized_provider_type(provider_type: str) -> str:
    return provider_type.strip().lower().replace("-", "_")


def _json_mapping(raw_value: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message="MODEL_PROVIDER_REGISTRY must be valid JSON.",
        ) from exc
    return _mapping_value(parsed, "MODEL_PROVIDER_REGISTRY")


def _mapping_value(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"{field_name} must be an object.",
        )
    return value


def _string_value(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"{field_name} must be a string.",
        )
    return _require_non_empty(value, field_name)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message="model provider config value must be a string.",
        )
    return value


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"{field_name} is required.",
        )
    return value.strip()


def _int_value(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"{field_name} must be an integer.",
        ) from exc
