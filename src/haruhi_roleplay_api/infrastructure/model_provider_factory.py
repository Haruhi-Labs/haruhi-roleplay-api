"""Provider factory map for model registry wiring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Mapping

from haruhi_roleplay_api.adapters import (
    DeepSeekModelProvider,
    FakeModelProvider,
    GeminiModelProvider,
    LocalOpenAICompatibleModelProvider,
    OllamaModelProvider,
)
from haruhi_roleplay_api.application import (
    ModelAliasRoute,
    ModelProviderRegistryRouter,
)
from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.infrastructure.model_registry import (
    ModelProviderConfig,
    ModelProviderSettings,
)
from haruhi_roleplay_api.ports import ChatModelProvider, ChatModelRouter


ProviderFactory = Callable[[ModelProviderConfig, Mapping[str, str]], ChatModelProvider]


@dataclass(frozen=True, kw_only=True)
class ProviderFactorySpec:
    factory: ProviderFactory
    default_base_url: str | None = None
    default_api_key_env: str | None = None
    default_chat_completions_path: str | None = None
    requires_api_key: bool = False


def build_model_router(settings: ModelProviderSettings) -> ChatModelRouter:
    providers = {
        provider_id: _build_provider(config, settings.sourceEnv)
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


def _build_provider(
    config: ModelProviderConfig,
    env: Mapping[str, str],
) -> ChatModelProvider:
    provider_type = _normalized_provider_type(config.provider_type)
    try:
        spec = PROVIDER_FACTORIES[provider_type]
    except KeyError as exc:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"MODEL_PROVIDER is not supported: {config.provider_type}",
        ) from exc
    if config.timeoutMs <= 0:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message="MODEL_TIMEOUT_MS must be positive.",
        )
    api_key = _api_key(config, env, spec)
    if spec.requires_api_key and not api_key:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=(
                f"{_api_key_name(config, spec)} is required "
                f"for model provider {config.provider_id}."
            ),
        )
    return spec.factory(
        _normalized_config(config, api_key=api_key, spec=spec),
        env,
    )


def _build_fake_provider(
    config: ModelProviderConfig,
    env: Mapping[str, str],
) -> ChatModelProvider:
    return FakeModelProvider()


def _build_openai_compatible_provider(
    config: ModelProviderConfig,
    env: Mapping[str, str],
) -> ChatModelProvider:
    if not config.baseUrl:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=(
                f"MODEL_BASE_URL is required for model provider "
                f"{config.provider_id}."
            ),
        )
    return LocalOpenAICompatibleModelProvider(
        base_url=config.baseUrl,
        timeout_seconds=config.timeoutMs / 1000,
        api_key=config.apiKey,
        provider_name=config.providerName,
        chat_completions_path=config.chatCompletionsPath,
    )


def _build_ollama_provider(
    config: ModelProviderConfig,
    env: Mapping[str, str],
) -> ChatModelProvider:
    if not config.baseUrl:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=(
                f"MODEL_BASE_URL is required for model provider "
                f"{config.provider_id}."
            ),
        )
    return OllamaModelProvider(
        base_url=config.baseUrl,
        timeout_seconds=config.timeoutMs / 1000,
        api_key=config.apiKey,
        chat_completions_path=config.chatCompletionsPath,
    )


def _build_deepseek_provider(
    config: ModelProviderConfig,
    env: Mapping[str, str],
) -> ChatModelProvider:
    return DeepSeekModelProvider(
        base_url=config.baseUrl,
        timeout_seconds=config.timeoutMs / 1000,
        api_key=_required_api_key(config),
        chat_completions_path=config.chatCompletionsPath,
    )


def _build_gemini_provider(
    config: ModelProviderConfig,
    env: Mapping[str, str],
) -> ChatModelProvider:
    return GeminiModelProvider(
        base_url=config.baseUrl,
        timeout_seconds=config.timeoutMs / 1000,
        api_key=_required_api_key(config),
        chat_completions_path=config.chatCompletionsPath,
    )


PROVIDER_FACTORIES: Mapping[str, ProviderFactorySpec] = {
    "fake": ProviderFactorySpec(factory=_build_fake_provider),
    "local": ProviderFactorySpec(factory=_build_openai_compatible_provider),
    "openai_compatible": ProviderFactorySpec(
        factory=_build_openai_compatible_provider
    ),
    "local_openai_compatible": ProviderFactorySpec(
        factory=_build_openai_compatible_provider
    ),
    "ollama": ProviderFactorySpec(factory=_build_ollama_provider),
    "deepseek": ProviderFactorySpec(
        factory=_build_deepseek_provider,
        default_base_url=DeepSeekModelProvider.default_base_url,
        default_api_key_env=DeepSeekModelProvider.default_api_key_env,
        default_chat_completions_path=(
            DeepSeekModelProvider.default_chat_completions_path
        ),
        requires_api_key=True,
    ),
    "gemini": ProviderFactorySpec(
        factory=_build_gemini_provider,
        default_base_url=GeminiModelProvider.default_base_url,
        default_api_key_env=GeminiModelProvider.default_api_key_env,
        default_chat_completions_path=(
            GeminiModelProvider.default_chat_completions_path
        ),
        requires_api_key=True,
    ),
}


def _normalized_provider_type(provider_type: str) -> str:
    return provider_type.strip().lower().replace("-", "_")


def _normalized_config(
    config: ModelProviderConfig,
    *,
    api_key: str | None,
    spec: ProviderFactorySpec,
) -> ModelProviderConfig:
    return ModelProviderConfig(
        provider_id=config.provider_id,
        provider_type=config.provider_type,
        baseUrl=config.baseUrl or spec.default_base_url,
        timeoutMs=config.timeoutMs,
        apiKey=api_key,
        apiKeyEnv=config.apiKeyEnv,
        providerName=config.providerName,
        chatCompletionsPath=(
            config.chatCompletionsPath or spec.default_chat_completions_path
        ),
    )


def _api_key(
    config: ModelProviderConfig,
    env: Mapping[str, str],
    spec: ProviderFactorySpec,
) -> str | None:
    if config.apiKey:
        return config.apiKey
    env_key = config.apiKeyEnv or spec.default_api_key_env
    if env_key is None:
        return None
    return env.get(env_key)


def _api_key_name(
    config: ModelProviderConfig,
    spec: ProviderFactorySpec,
) -> str:
    return config.apiKeyEnv or spec.default_api_key_env or "MODEL_API_KEY"


def _required_api_key(config: ModelProviderConfig) -> str:
    if not config.apiKey:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"API key is required for model provider {config.provider_id}.",
        )
    return config.apiKey
