"""Tavern-style provider config facade.

This module maps user-facing LLM/Embedding/RAG fields onto the existing
provider-specific environment shape. It intentionally does not build providers.
"""

from __future__ import annotations

import json
from typing import Mapping


SIMPLE_LLM_KEYS = (
    "LLM_API_TYPE",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_API_KEY",
)
SIMPLE_EMBEDDING_KEYS = (
    "EMBEDDING_API_TYPE",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "EMBEDDING_API_KEY",
)
SIMPLE_RAG_KEYS = (
    "RAG_API_TYPE",
    "RAG_BASE_URL",
    "RAG_INDEX",
    "RAG_API_KEY",
)
SIMPLE_PROVIDER_CONFIG_KEYS = (
    *SIMPLE_LLM_KEYS,
    *SIMPLE_EMBEDDING_KEYS,
    *SIMPLE_RAG_KEYS,
)


def apply_provider_config_facade(env: Mapping[str, str]) -> dict[str, str]:
    effective = dict(env)
    _apply_llm_facade(effective, env)
    _apply_embedding_facade(effective, env)
    _apply_rag_facade(effective, env)
    _apply_default_session(effective, env)
    return effective


def has_simple_provider_config(env: Mapping[str, str]) -> bool:
    return any(_has_value(env, key) for key in SIMPLE_PROVIDER_CONFIG_KEYS)


def _apply_llm_facade(effective: dict[str, str], env: Mapping[str, str]) -> None:
    if not _has_any_value(env, SIMPLE_LLM_KEYS):
        return
    if _has_value(env, "MODEL_PROVIDER_REGISTRY"):
        return

    api_type = _normalized(env.get("LLM_API_TYPE", ""))
    model = _string(env.get("LLM_MODEL"))
    if api_type == "fake" and not model:
        model = "fake-roleplay-model"
    provider: dict[str, str | int] = {"type": api_type}
    base_url = _string(env.get("LLM_BASE_URL"))
    if base_url:
        provider["base_url"] = base_url
    if _has_value(env, "LLM_API_KEY"):
        provider["api_key_env"] = "LLM_API_KEY"
    timeout_ms = _string(env.get("MODEL_TIMEOUT_MS"))
    if timeout_ms:
        try:
            provider["timeout_ms"] = int(timeout_ms)
        except ValueError:
            provider["timeout_ms"] = timeout_ms  # Let existing validation fail.

    alias = model
    registry = {
        "default_alias": alias,
        "providers": {
            "llm-main": provider,
        },
        "aliases": {
            alias: {
                "provider": "llm-main",
                "model": model,
            },
        },
    }
    effective["MODEL_PROVIDER_REGISTRY"] = json.dumps(
        registry,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _apply_embedding_facade(
    effective: dict[str, str],
    env: Mapping[str, str],
) -> None:
    if not _has_any_value(env, SIMPLE_EMBEDDING_KEYS):
        return

    if _has_value(env, "EMBEDDING_API_TYPE"):
        effective["EMBEDDING_PROVIDER"] = _normalized(env.get("EMBEDDING_API_TYPE", ""))
    if _has_value(env, "EMBEDDING_BASE_URL"):
        effective["EMBEDDING_BASE_URL"] = _string(env.get("EMBEDDING_BASE_URL"))
    if _has_value(env, "EMBEDDING_MODEL"):
        effective["EMBEDDING_MODEL"] = _string(env.get("EMBEDDING_MODEL"))
    if _has_value(env, "EMBEDDING_API_KEY"):
        effective["EMBEDDING_API_KEY"] = _string(env.get("EMBEDDING_API_KEY"))


def _apply_rag_facade(effective: dict[str, str], env: Mapping[str, str]) -> None:
    if not _has_any_value(env, SIMPLE_RAG_KEYS):
        return

    api_type = _normalized(env.get("RAG_API_TYPE", ""))
    if _has_value(env, "RAG_API_TYPE"):
        effective["RAG_PROVIDER"] = api_type
    index = _string(env.get("RAG_INDEX"))
    base_url = _string(env.get("RAG_BASE_URL"))
    api_key = _string(env.get("RAG_API_KEY"))

    if api_type in {"qdrant", "cloud_rag"}:
        if base_url:
            effective["QDRANT_URL"] = base_url
        if index:
            effective["QDRANT_COLLECTION"] = index
        if api_key:
            effective["QDRANT_API_KEY"] = api_key
        return

    if api_type in {"chroma", "chromadb"} and index:
        effective["CHROMA_COLLECTION"] = index


def _apply_default_session(effective: dict[str, str], env: Mapping[str, str]) -> None:
    if not has_simple_provider_config(env):
        return
    if not _has_value(env, "SESSION_PROVIDER"):
        effective["SESSION_PROVIDER"] = "sqlite"
    if effective.get("SESSION_PROVIDER") == "sqlite" and not _has_value(
        env,
        "SESSION_SQLITE_PATH",
    ):
        effective["SESSION_SQLITE_PATH"] = ".data/sessions.sqlite3"


def _has_any_value(env: Mapping[str, str], keys: tuple[str, ...]) -> bool:
    return any(_has_value(env, key) for key in keys)


def _has_value(env: Mapping[str, str], key: str) -> bool:
    return bool(_string(env.get(key)))


def _string(value: str | None) -> str:
    return value.strip() if value is not None else ""


def _normalized(value: str) -> str:
    return value.strip().lower().replace("-", "_")
