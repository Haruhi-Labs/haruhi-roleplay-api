"""Model routing use cases."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Mapping

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    GenerationConfig,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
)
from haruhi_roleplay_api.ports import ChatModelProvider


@dataclass(frozen=True, kw_only=True)
class ModelRouteDecision:
    provider: str
    model: str
    alias: str | None = None

    def to_debug_trace(self) -> dict[str, str]:
        data = {
            "modelProvider": self.provider,
            "model": self.model,
        }
        if self.alias is not None:
            data["modelAlias"] = self.alias
        return data


@dataclass(frozen=True, kw_only=True)
class ModelAliasRoute:
    alias: str
    provider_id: str
    provider_model: str


class ModelRouter:
    def __init__(
        self,
        provider: ChatModelProvider,
        *,
        default_model: str = "fake-roleplay-model",
        allowed_models: tuple[str, ...] = ("fake-roleplay-model",),
    ) -> None:
        self._provider = provider
        self._default_model = default_model
        self._allowed_models = allowed_models

    def route(
        self,
        generation: GenerationConfig | None = None,
    ) -> ModelRouteDecision:
        selected_model = (
            generation.model if generation and generation.model else self._default_model
        )
        if selected_model not in self._allowed_models:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"Model alias is not configured: {selected_model}",
            )
        return ModelRouteDecision(
            provider=self._provider.provider_name,
            model=selected_model,
        )

    def generate(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> ModelResponse:
        decision = self.route(generation)
        return self._provider.generate(
            ModelRequest(
                messages=messages,
                model=decision.model,
                generation=generation,
            )
        )

    def stream(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> Iterable[ModelStreamEvent]:
        decision = self.route(generation)
        return self._provider.stream(
            ModelRequest(
                messages=messages,
                model=decision.model,
                generation=generation,
            )
        )


class ModelProviderRegistryRouter:
    def __init__(
        self,
        *,
        providers: Mapping[str, ChatModelProvider],
        aliases: Mapping[str, ModelAliasRoute],
        default_alias: str,
    ) -> None:
        self._providers = dict(providers)
        self._aliases = dict(aliases)
        self._default_alias = _require_configured(default_alias, "default model alias")
        _validate_registry(self._providers, self._aliases, self._default_alias)

    def route(
        self,
        generation: GenerationConfig | None = None,
    ) -> ModelRouteDecision:
        alias = generation.model if generation and generation.model else self._default_alias
        route = self._route_for_alias(alias)
        provider = self._provider_for_route(route)
        return ModelRouteDecision(
            provider=provider.provider_name,
            model=route.alias,
            alias=route.alias,
        )

    def generate(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> ModelResponse:
        route = self._route_for_generation(generation)
        provider = self._provider_for_route(route)
        response = provider.generate(
            ModelRequest(
                messages=messages,
                model=route.provider_model,
                generation=generation,
            )
        )
        return _response_with_alias(response, route.alias)

    def stream(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> Iterable[ModelStreamEvent]:
        route = self._route_for_generation(generation)
        provider = self._provider_for_route(route)
        for event in provider.stream(
            ModelRequest(
                messages=messages,
                model=route.provider_model,
                generation=generation,
            )
        ):
            if event.event != "done":
                yield event
                continue
            if event.response is None:
                raise AppError(
                    code=ErrorCode.MODEL_PROVIDER_ERROR,
                    message="Model provider stream ended without final response.",
                )
            yield ModelStreamEvent(
                event="done",
                response=_response_with_alias(event.response, route.alias),
            )

    def _route_for_generation(
        self,
        generation: GenerationConfig | None,
    ) -> ModelAliasRoute:
        alias = generation.model if generation and generation.model else self._default_alias
        return self._route_for_alias(alias)

    def _route_for_alias(self, alias: str | None) -> ModelAliasRoute:
        selected_alias = _require_configured(alias, "model alias")
        try:
            return self._aliases[selected_alias]
        except KeyError as exc:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"Model alias is not configured: {selected_alias}",
            ) from exc

    def _provider_for_route(self, route: ModelAliasRoute) -> ChatModelProvider:
        try:
            return self._providers[route.provider_id]
        except KeyError as exc:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"Model provider is not configured: {route.provider_id}",
            ) from exc


def _validate_registry(
    providers: Mapping[str, ChatModelProvider],
    aliases: Mapping[str, ModelAliasRoute],
    default_alias: str,
) -> None:
    if not providers:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message="At least one model provider must be configured.",
        )
    if not aliases:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message="At least one model alias must be configured.",
        )
    if default_alias not in aliases:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"Default model alias is not configured: {default_alias}",
        )
    for alias, route in aliases.items():
        _require_configured(alias, "model alias")
        _require_configured(route.provider_id, f"model alias provider for {alias}")
        _require_configured(route.provider_model, f"provider model for {alias}")
        if route.provider_id not in providers:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"Model provider is not configured: {route.provider_id}",
            )


def _response_with_alias(response: ModelResponse, alias: str) -> ModelResponse:
    debug = dict(response.debug)
    debug["modelAlias"] = alias
    return ModelResponse(
        reply=response.reply,
        provider=response.provider,
        model=alias,
        usage=response.usage,
        debug=debug,
    )


def _require_configured(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"{field_name} is required.",
        )
    return value.strip()
