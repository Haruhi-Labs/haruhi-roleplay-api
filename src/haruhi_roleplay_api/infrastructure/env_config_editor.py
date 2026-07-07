"""Trusted .env editor schema, validation, and persistence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from haruhi_roleplay_api.domain import DTOValidationError
from haruhi_roleplay_api.infrastructure.runtime_config import (
    RUNTIME_CONFIG_KEYS,
    RUNTIME_CONFIG_RESTART_REQUIRED_KEYS,
)
from haruhi_roleplay_api.infrastructure.provider_config_facade import (
    apply_provider_config_facade,
)

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNQUOTED_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:@-]+$")


@dataclass(frozen=True, kw_only=True)
class EnvConfigField:
    key: str
    group: str
    valueType: str
    description: str
    default: str | None = None
    enum: tuple[str, ...] = ()
    secret: bool = False
    hotReload: bool = False
    restartRequired: bool = False
    required: bool = False
    minValue: int | None = None
    maxValue: int | None = None

    def to_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "key": self.key,
            "group": self.group,
            "type": self.valueType,
            "description": self.description,
            "secret": self.secret,
            "hot_reload": self.hotReload,
            "restart_required": self.restartRequired,
            "required": self.required,
        }
        if self.default is not None:
            data["default"] = self.default
        if self.enum:
            data["enum"] = list(self.enum)
        if self.minValue is not None:
            data["min"] = self.minValue
        if self.maxValue is not None:
            data["max"] = self.maxValue
        return data


@dataclass(frozen=True, kw_only=True)
class EnvConfigCheck:
    valid: bool
    fieldResults: tuple[Mapping[str, Any], ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "field_results": list(self.fieldResults),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, kw_only=True)
class _EnvLine:
    raw: str
    key: str | None = None
    value: str | None = None


@dataclass(frozen=True, kw_only=True)
class _EnvDocument:
    lines: tuple[_EnvLine, ...] = ()
    values: Mapping[str, str] = field(default_factory=dict)


def _field(
    key: str,
    group: str,
    value_type: str,
    description: str,
    *,
    default: str | None = None,
    enum: tuple[str, ...] = (),
    secret: bool = False,
    hot_reload: bool | None = None,
    restart_required: bool | None = None,
    required: bool = False,
    min_value: int | None = None,
    max_value: int | None = None,
) -> EnvConfigField:
    restart = restart_required if restart_required is not None else key in _RESTART_KEYS
    hot = hot_reload if hot_reload is not None else key in _HOT_RELOAD_KEYS
    return EnvConfigField(
        key=key,
        group=group,
        valueType=value_type,
        description=description,
        default=default,
        enum=enum,
        secret=secret,
        hotReload=hot,
        restartRequired=restart,
        required=required,
        minValue=min_value,
        maxValue=max_value,
    )


_RESTART_KEYS = {
    *RUNTIME_CONFIG_RESTART_REQUIRED_KEYS,
    "ROLEPLAY_HOST",
    "ROLEPLAY_PORT",
    "PERSONA_CONFIG_DIR",
}
_HOT_RELOAD_KEYS = {
    *RUNTIME_CONFIG_KEYS,
    "ROLEPLAY_API_KEY",
    "LLM_API_KEY",
    "RAG_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "MODEL_API_KEY",
    "EMBEDDING_API_KEY",
    "QDRANT_API_KEY",
}

ENV_CONFIG_FIELDS: tuple[EnvConfigField, ...] = (
    _field("ROLEPLAY_HOST", "HTTP", "string", "HTTP bind host.", default="127.0.0.1"),
    _field("ROLEPLAY_PORT", "HTTP", "int", "HTTP bind port.", default="8000", min_value=1, max_value=65535),
    _field("ROLEPLAY_API_KEY", "HTTP", "secret", "Trusted admin API key.", secret=True, hot_reload=True),
    _field("ENABLE_DEBUG_TRACE", "HTTP", "bool", "Return safe debug trace summaries.", default="true"),
    _field("LLM_API_TYPE", "Simple LLM", "enum", "LLM API type/provider.", enum=("fake", "openai", "openai_compatible", "ollama", "deepseek", "gemini")),
    _field("LLM_BASE_URL", "Simple LLM", "url", "LLM API base URL."),
    _field("LLM_MODEL", "Simple LLM", "string", "LLM model name."),
    _field("LLM_API_KEY", "Simple LLM", "secret", "LLM API token.", secret=True, hot_reload=True),
    _field("MODEL_PROVIDER", "Model", "enum", "Legacy model provider type.", default="fake", enum=("fake", "local", "openai_compatible", "ollama", "openai", "deepseek", "gemini")),
    _field("MODEL_PROVIDER_ID", "Model", "string", "Legacy provider id override."),
    _field("MODEL_PROVIDER_NAME", "Model", "string", "Display/debug name for local compatible provider."),
    _field("MODEL_NAME", "Model", "string", "Model name sent to provider.", default="fake-roleplay-model"),
    _field("MODEL_ALIAS", "Model", "string", "Model alias exposed to chat requests.", default="fake-roleplay-model"),
    _field("MODEL_BASE_URL", "Model", "url", "OpenAI-compatible base URL."),
    _field("MODEL_TIMEOUT_MS", "Model", "int", "Model provider timeout in milliseconds.", default="60000", min_value=1),
    _field("MODEL_API_KEY_ENV", "Model", "string", "Environment variable name for model API key."),
    _field("MODEL_API_KEY", "Secrets", "secret", "Direct model API key fallback.", secret=True, hot_reload=True),
    _field("MODEL_PROVIDER_REGISTRY", "Model Registry", "json", "Provider registry JSON for multi-provider routing."),
    _field("OPENAI_API_KEY", "Secrets", "secret", "OpenAI API key.", secret=True, hot_reload=True),
    _field("DEEPSEEK_API_KEY", "Secrets", "secret", "DeepSeek API key.", secret=True, hot_reload=True),
    _field("GEMINI_API_KEY", "Secrets", "secret", "Gemini API key.", secret=True, hot_reload=True),
    _field("RAG_API_TYPE", "Simple RAG", "enum", "RAG API type/provider.", enum=("fake", "local", "local_vector", "chroma", "faiss", "qdrant")),
    _field("RAG_BASE_URL", "Simple RAG", "url", "RAG API base URL."),
    _field("RAG_INDEX", "Simple RAG", "string", "RAG collection, index, or vector store id."),
    _field("RAG_API_KEY", "Simple RAG", "secret", "RAG API token.", secret=True, hot_reload=True),
    _field("RAG_PROVIDER", "RAG", "enum", "RAG provider.", default="local", enum=("fake", "local", "local_vector", "chroma", "faiss", "qdrant")),
    _field("RAG_CHUNK_SIZE", "RAG", "int", "RAG chunk size.", default="320", min_value=1),
    _field("RAG_EMBEDDING_DIMENSIONS", "RAG", "int", "RAG vector dimensions.", default="384", min_value=1),
    _field("RAG_VECTOR_BACKEND", "RAG", "enum", "Local vector backend.", default="memory", enum=("memory", "chroma", "faiss")),
    _field("LOCAL_VECTOR_RAG_BACKEND", "RAG", "enum", "Local vector backend override.", default="memory", enum=("memory", "chroma", "faiss")),
    _field("CHROMA_COLLECTION", "RAG", "string", "Chroma collection name.", default="haruhi_rag"),
    _field("CHROMA_PERSIST_PATH", "RAG", "path", "Chroma persist path."),
    _field("QDRANT_URL", "RAG", "url", "Qdrant base URL."),
    _field("QDRANT_COLLECTION", "RAG", "string", "Qdrant collection name.", default="haruhi_rag"),
    _field("QDRANT_TIMEOUT_MS", "RAG", "int", "Qdrant timeout in milliseconds.", default="10000", min_value=1),
    _field("QDRANT_ENSURE_COLLECTION", "RAG", "bool", "Create Qdrant collection when missing.", default="false"),
    _field("QDRANT_API_KEY", "Secrets", "secret", "Qdrant API key.", secret=True, hot_reload=True),
    _field("EMBEDDING_API_TYPE", "Simple Embedding", "enum", "Embedding API type/provider.", enum=("hash", "openai", "openai_compatible", "local_openai_compatible", "ollama")),
    _field("EMBEDDING_BASE_URL", "Simple Embedding", "url", "Embedding API base URL."),
    _field("EMBEDDING_MODEL", "Simple Embedding", "string", "Embedding model name."),
    _field("EMBEDDING_API_KEY", "Simple Embedding", "secret", "Embedding API token.", secret=True, hot_reload=True),
    _field("EMBEDDING_PROVIDER", "Embedding", "enum", "Embedding provider.", default="hash", enum=("hash", "local_openai_compatible", "openai_compatible", "local", "ollama", "openai")),
    _field("EMBEDDING_DIMENSIONS", "Embedding", "int", "Embedding vector dimensions.", default="384", min_value=1),
    _field("EMBEDDING_TIMEOUT_MS", "Embedding", "int", "Embedding timeout in milliseconds.", default="30000", min_value=1),
    _field("EMBEDDING_API_KEY_ENV", "Embedding", "string", "Environment variable name for embedding API key."),
    _field("EMBEDDING_PATH", "Embedding", "path", "Embeddings API path override."),
    _field("AGENT_CONTEXT_PLANNER", "Agent", "enum", "Agent context planner mode.", default="deterministic", enum=("deterministic", "model")),
    _field("BACKEND_CONTEXT_PROVIDER", "Backend Context", "enum", "Backend context provider.", default="none", enum=("none", "fake")),
    _field("BACKEND_CONTEXT_SOURCES", "Backend Context", "csv", "Backend context source list."),
    _field("BACKEND_CONTEXT_ALLOWED_SOURCES", "Backend Context", "csv", "Allowed backend context sources.", default="user_profile,game_state"),
    _field("SESSION_PROVIDER", "Session", "enum", "Session store provider.", default="memory", enum=("memory", "sqlite", "postgres")),
    _field("SESSION_RECENT_LIMIT", "Session", "int", "Recent message count used in prompt.", default="12", min_value=1),
    _field("SESSION_TTL_SECONDS", "Session", "int", "Session TTL seconds.", default="604800", min_value=0),
    _field("SESSION_AUTO_CREATE_SCHEMA", "Session", "bool", "Auto-create session database schema.", default="true"),
    _field("SESSION_SQLITE_PATH", "Session", "path", "SQLite session database path.", default=".data/sessions.sqlite3"),
    _field("SESSION_SQLITE_BUSY_TIMEOUT_MS", "Session", "int", "SQLite busy timeout in milliseconds.", default="5000", min_value=1),
    _field("SESSION_POSTGRES_SCHEMA", "Session", "identifier", "PostgreSQL schema.", default="public"),
    _field("SESSION_POSTGRES_TABLE_PREFIX", "Session", "identifier", "PostgreSQL table prefix.", default="roleplay_"),
    _field("SESSION_POSTGRES_POOL_SIZE", "Session", "int", "PostgreSQL pool size.", default="5", min_value=1),
    _field("MEMORY_PROVIDER", "Memory", "enum", "Memory store provider.", default="memory", enum=("memory", "sqlite")),
    _field("MEMORY_SQLITE_PATH", "Memory", "path", "SQLite memory database path.", default=".data/memories.sqlite3"),
    _field("MEMORY_SQLITE_BUSY_TIMEOUT_MS", "Memory", "int", "SQLite memory busy timeout in milliseconds.", default="5000", min_value=1),
    _field("DATABASE_URL", "Secrets", "secret", "PostgreSQL database URL.", secret=True, restart_required=True),
    _field("REDIS_URL", "Secrets", "secret", "Reserved Redis URL.", secret=True, restart_required=True),
    _field("PERSONA_CONFIG_DIR", "Advanced", "path", "Local persona config directory.", default="./personas"),
)

ENV_CONFIG_FIELD_BY_KEY = {field.key: field for field in ENV_CONFIG_FIELDS}
ENV_CONFIG_GROUPS = tuple(dict.fromkeys(field.group for field in ENV_CONFIG_FIELDS))


class EnvConfigEditor:
    def __init__(
        self,
        *,
        base_env: Mapping[str, str],
        config_path: Path | None,
    ) -> None:
        self._base_env = dict(base_env)
        self._config_path = config_path

    def schema(self) -> dict[str, Any]:
        return {
            "groups": list(ENV_CONFIG_GROUPS),
            "fields": [field.to_data() for field in ENV_CONFIG_FIELDS],
            "writable": self._config_path is not None,
            "source": self.source,
        }

    @property
    def source(self) -> str:
        return str(self._config_path) if self._config_path else "memory"

    def snapshot(self) -> dict[str, Any]:
        document = self._document()
        file_values = dict(document.values)
        env = self._effective_env(file_values)
        values = {
            field.key: _field_snapshot(field, env, file_values, self._base_env)
            for field in ENV_CONFIG_FIELDS
        }
        return {
            "source": self.source,
            "writable": self._config_path is not None,
            "values": values,
            "unknown_keys": _unknown_key_summaries(file_values),
        }

    def check(self, body: Mapping[str, Any]) -> EnvConfigCheck:
        updates = self.parse_update(body)
        document = self._document()
        candidate = self._candidate_env(dict(document.values), updates)
        field_results = tuple(
            _check_field(ENV_CONFIG_FIELD_BY_KEY.get(key), key, value)
            for key, value in updates.items()
        )
        errors = [
            error
            for result in field_results
            for error in result.get("errors", ())
        ]
        warnings = [
            warning
            for result in field_results
            for warning in result.get("warnings", ())
        ]
        dependency_errors, dependency_warnings = _check_dependencies(candidate)
        errors.extend(dependency_errors)
        warnings.extend(dependency_warnings)
        return EnvConfigCheck(
            valid=not errors,
            fieldResults=field_results,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def commit(self, body: Mapping[str, Any]) -> dict[str, Any]:
        if self._config_path is None:
            raise DTOValidationError("env config source is not writable")
        updates = self.parse_update(body)
        if not updates:
            raise DTOValidationError("env config values must not be empty")
        check = self.check({"values": updates})
        if not check.valid:
            raise DTOValidationError(
                "env config check failed: " + "; ".join(check.errors)
            )
        before = self.snapshot()["values"]
        document = self._document()
        _write_env_document(self._config_path, document, updates)
        after = self.snapshot()["values"]
        changes = tuple(
            _change_summary(
                key,
                updates[key],
                before.get(key, {}),
                after.get(key, {}),
            )
            for key in updates
        )
        return {
            "applied_keys": list(updates.keys()),
            "restart_required_keys": [
                key for key in updates if ENV_CONFIG_FIELD_BY_KEY[key].restartRequired
            ],
            "hot_reload_keys": [
                key for key in updates if ENV_CONFIG_FIELD_BY_KEY[key].hotReload
            ],
            "changes": list(changes),
            "check": check.to_data(),
            "config": self.snapshot(),
        }

    def parse_update(self, body: Mapping[str, Any]) -> dict[str, str | None]:
        if not isinstance(body, Mapping):
            raise DTOValidationError("env config request body must be an object")
        if "key" in body:
            key = _config_key(body.get("key"))
            value = body.get("value")
            return {key: _normalize_update_value(key, value)}
        raw_values = body.get("values", body)
        if not isinstance(raw_values, Mapping):
            raise DTOValidationError("env config values must be an object")
        updates: dict[str, str | None] = {}
        for raw_key, raw_value in raw_values.items():
            key = _config_key(raw_key)
            updates[key] = _normalize_update_value(key, raw_value)
        if not updates:
            raise DTOValidationError("env config values must not be empty")
        return updates

    def _document(self) -> _EnvDocument:
        return _read_env_document(self._config_path)

    def _effective_env(self, file_values: Mapping[str, str]) -> dict[str, str]:
        env = dict(self._base_env)
        env.update(file_values)
        return apply_provider_config_facade(env)

    def _candidate_env(
        self,
        file_values: dict[str, str],
        updates: Mapping[str, str | None],
    ) -> dict[str, str]:
        for key, value in updates.items():
            if value is None:
                file_values.pop(key, None)
            else:
                file_values[key] = value
        return self._effective_env(file_values)


def _config_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError("env config key must be a non-empty string")
    key = value.strip()
    if key not in ENV_CONFIG_FIELD_BY_KEY:
        raise DTOValidationError(f"env config key is not supported: {key}")
    return key


def _normalize_update_value(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Mapping) and "value" in value:
        value = value["value"]
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False)


def _field_snapshot(
    field: EnvConfigField,
    env: Mapping[str, str],
    file_values: Mapping[str, str],
    base_env: Mapping[str, str],
) -> dict[str, Any]:
    has_file_value = field.key in file_values
    has_process_value = field.key in base_env
    value = env.get(field.key)
    source = (
        "file"
        if has_file_value
        else "process"
        if has_process_value
        else "default"
        if field.default is not None
        else "missing"
    )
    status = "set" if value else "empty" if value == "" else "missing"
    data: dict[str, Any] = {
        "key": field.key,
        "source": source,
        "status": status,
        "secret": field.secret,
        "restart_required": field.restartRequired,
        "hot_reload": field.hotReload,
    }
    if field.secret:
        return data
    data["value"] = value if value is not None else field.default
    if value is not None and not has_file_value and not has_process_value:
        data["source"] = "derived"
    return data


def _unknown_key_summaries(file_values: Mapping[str, str]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for key, value in sorted(file_values.items()):
        if key in ENV_CONFIG_FIELD_BY_KEY:
            continue
        secret = _looks_sensitive(key)
        summaries.append(
            {
                "key": key,
                "secret": secret,
                "status": "set" if value else "empty",
            }
        )
    return summaries


def _check_field(
    field: EnvConfigField | None,
    key: str,
    value: str | None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if field is None:
        return {
            "key": key,
            "valid": False,
            "errors": [f"env config key is not supported: {key}"],
            "warnings": [],
        }
    if value is None:
        return {
            "key": key,
            "valid": True,
            "action": "remove",
            "errors": [],
            "warnings": [],
        }
    if field.required and not value:
        errors.append(f"{key} is required")
    if field.valueType in {"string", "path", "url", "identifier", "csv"}:
        _check_text_field(field, value, errors, warnings)
    if field.valueType == "int":
        _check_int_field(field, value, errors)
    if field.valueType == "bool":
        _check_bool_field(field, value, errors)
    if field.valueType == "enum":
        _check_enum_field(field, value, errors)
    if field.valueType == "json":
        _check_json_field(field, value, errors)
    if field.valueType == "secret":
        return {
            "key": key,
            "valid": not errors,
            "secret": True,
            "secret_status_after": "set" if value else "empty",
            "errors": errors,
            "warnings": warnings,
        }
    result: dict[str, Any] = {
        "key": key,
        "valid": not errors,
        "normalized_value": value,
        "errors": errors,
        "warnings": warnings,
    }
    return result


def _check_text_field(
    field: EnvConfigField,
    value: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    if "\x00" in value:
        errors.append(f"{field.key} must not contain NUL")
    if field.valueType == "url" and value:
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            errors.append(f"{field.key} must be a valid URL")
    if field.valueType == "identifier" and value:
        if not _IDENTIFIER_RE.fullmatch(value):
            errors.append(f"{field.key} must be a safe identifier")
    if field.valueType == "csv" and "\n" in value:
        errors.append(f"{field.key} must be a comma-separated single line")
    if field.valueType == "path" and value.startswith("~"):
        warnings.append(f"{field.key} uses a user-home path; prefer explicit paths")


def _check_int_field(
    field: EnvConfigField,
    value: str,
    errors: list[str],
) -> None:
    try:
        parsed = int(value)
    except ValueError:
        errors.append(f"{field.key} must be an integer")
        return
    if field.minValue is not None and parsed < field.minValue:
        errors.append(f"{field.key} must be >= {field.minValue}")
    if field.maxValue is not None and parsed > field.maxValue:
        errors.append(f"{field.key} must be <= {field.maxValue}")


def _check_bool_field(
    field: EnvConfigField,
    value: str,
    errors: list[str],
) -> None:
    if value.strip().lower() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        errors.append(f"{field.key} must be a boolean")


def _check_enum_field(
    field: EnvConfigField,
    value: str,
    errors: list[str],
) -> None:
    normalized = value.strip().lower().replace("-", "_")
    allowed = {item.lower().replace("-", "_") for item in field.enum}
    if normalized not in allowed:
        errors.append(f"{field.key} must be one of: {', '.join(field.enum)}")


def _check_json_field(
    field: EnvConfigField,
    value: str,
    errors: list[str],
) -> None:
    if not value:
        return
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        errors.append(f"{field.key} must be valid JSON")
        return
    if field.key == "MODEL_PROVIDER_REGISTRY":
        errors.extend(_model_provider_registry_errors(parsed))


def _model_provider_registry_errors(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return ["MODEL_PROVIDER_REGISTRY must be an object"]
    providers = value.get("providers")
    aliases = value.get("aliases")
    default_alias = value.get("default_alias", value.get("defaultAlias"))
    if not isinstance(providers, Mapping) or not providers:
        errors.append("MODEL_PROVIDER_REGISTRY.providers must be a non-empty object")
    if not isinstance(aliases, Mapping) or not aliases:
        errors.append("MODEL_PROVIDER_REGISTRY.aliases must be a non-empty object")
    if not isinstance(default_alias, str) or not default_alias.strip():
        errors.append("MODEL_PROVIDER_REGISTRY.default_alias is required")
    elif isinstance(aliases, Mapping) and default_alias not in aliases:
        errors.append("MODEL_PROVIDER_REGISTRY.default_alias must exist in aliases")
    if isinstance(aliases, Mapping) and isinstance(providers, Mapping):
        for alias, alias_data in aliases.items():
            if not isinstance(alias_data, Mapping):
                errors.append(f"MODEL_PROVIDER_REGISTRY alias {alias} must be an object")
                continue
            provider = alias_data.get("provider")
            model = alias_data.get("model")
            if provider not in providers:
                errors.append(f"MODEL_PROVIDER_REGISTRY alias {alias} references missing provider")
            if not isinstance(model, str) or not model.strip():
                errors.append(f"MODEL_PROVIDER_REGISTRY alias {alias} model is required")
    if _contains_inline_secret(value):
        errors.append("MODEL_PROVIDER_REGISTRY must not contain inline api_key/token/secret")
    return errors


def _contains_inline_secret(value: Any) -> bool:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).replace("-", "_").lower()
            if key in {"api_key", "apikey", "token", "secret"}:
                return True
            if _contains_inline_secret(child):
                return True
    if isinstance(value, list):
        return any(_contains_inline_secret(item) for item in value)
    return False


def _check_dependencies(env: Mapping[str, str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    errors: list[str] = []
    warnings: list[str] = []
    _check_simple_llm_dependencies(env, errors)
    _check_simple_embedding_dependencies(env, errors)
    _check_simple_rag_dependencies(env, errors)
    session_provider = _normalized(env.get("SESSION_PROVIDER", "memory"))
    if session_provider in {"postgres", "postgresql"} and not env.get("DATABASE_URL"):
        errors.append("DATABASE_URL is required when SESSION_PROVIDER=postgres")
    rag_provider = _normalized(env.get("RAG_PROVIDER", "local"))
    if rag_provider in {"qdrant", "cloud_rag"}:
        if not env.get("QDRANT_URL"):
            errors.append("QDRANT_URL is required when RAG_PROVIDER=qdrant")
        if not env.get("QDRANT_COLLECTION"):
            errors.append("QDRANT_COLLECTION is required when RAG_PROVIDER=qdrant")
    if rag_provider in {"chroma", "chromadb"}:
        if not env.get("CHROMA_COLLECTION"):
            errors.append("CHROMA_COLLECTION is required when RAG_PROVIDER=chroma")
        if not env.get("CHROMA_PERSIST_PATH"):
            warnings.append("CHROMA_PERSIST_PATH is empty; Chroma will be in-memory")
    embedding_provider = _normalized(env.get("EMBEDDING_PROVIDER", "hash"))
    if embedding_provider == "openai" and not (
        env.get("EMBEDDING_API_KEY")
        or env.get("OPENAI_API_KEY")
        or env.get("EMBEDDING_API_KEY_ENV")
    ):
        errors.append("OPENAI_API_KEY or EMBEDDING_API_KEY_ENV is required when EMBEDDING_PROVIDER=openai")
    if embedding_provider in {"local", "openai_compatible", "local_openai_compatible"} and not env.get("EMBEDDING_BASE_URL"):
        errors.append("EMBEDDING_BASE_URL is required for local OpenAI-compatible embeddings")
    if _normalized(env.get("AGENT_CONTEXT_PLANNER", "deterministic")) == "model":
        warnings.append("AGENT_CONTEXT_PLANNER=model is reserved and not implemented")
    rag_dimensions = env.get("RAG_EMBEDDING_DIMENSIONS")
    embedding_dimensions = env.get("EMBEDDING_DIMENSIONS")
    if rag_dimensions and embedding_dimensions and rag_dimensions != embedding_dimensions:
        warnings.append("RAG_EMBEDDING_DIMENSIONS and EMBEDDING_DIMENSIONS differ; vector collections may need rebuild")
    return tuple(errors), tuple(warnings)


def _check_simple_llm_dependencies(
    env: Mapping[str, str],
    errors: list[str],
) -> None:
    if not _has_any(env, ("LLM_API_TYPE", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")):
        return
    api_type = _normalized(env.get("LLM_API_TYPE", ""))
    if not api_type:
        errors.append("LLM_API_TYPE is required when using simple LLM config")
        return
    if api_type != "fake" and not env.get("LLM_MODEL"):
        errors.append("LLM_MODEL is required when using simple LLM config")
    if api_type in {"openai_compatible", "ollama"} and not env.get("LLM_BASE_URL"):
        errors.append("LLM_BASE_URL is required for this LLM_API_TYPE")
    if api_type == "openai" and not (env.get("LLM_API_KEY") or env.get("OPENAI_API_KEY")):
        errors.append("LLM_API_KEY or OPENAI_API_KEY is required for LLM_API_TYPE=openai")
    if api_type == "deepseek" and not (
        env.get("LLM_API_KEY") or env.get("DEEPSEEK_API_KEY")
    ):
        errors.append("LLM_API_KEY or DEEPSEEK_API_KEY is required for LLM_API_TYPE=deepseek")
    if api_type == "gemini" and not (
        env.get("LLM_API_KEY") or env.get("GEMINI_API_KEY")
    ):
        errors.append("LLM_API_KEY or GEMINI_API_KEY is required for LLM_API_TYPE=gemini")


def _check_simple_embedding_dependencies(
    env: Mapping[str, str],
    errors: list[str],
) -> None:
    if not _has_any(
        env,
        (
            "EMBEDDING_API_TYPE",
            "EMBEDDING_BASE_URL",
            "EMBEDDING_MODEL",
            "EMBEDDING_API_KEY",
        ),
    ):
        return
    api_type = _normalized(env.get("EMBEDDING_API_TYPE", ""))
    if not api_type:
        errors.append("EMBEDDING_API_TYPE is required when using simple embedding config")
        return
    if api_type in {"openai_compatible", "local_openai_compatible"} and not env.get(
        "EMBEDDING_BASE_URL"
    ):
        errors.append("EMBEDDING_BASE_URL is required for this EMBEDDING_API_TYPE")
    if api_type == "openai" and not (
        env.get("EMBEDDING_API_KEY") or env.get("OPENAI_API_KEY")
    ):
        errors.append("EMBEDDING_API_KEY or OPENAI_API_KEY is required for EMBEDDING_API_TYPE=openai")


def _check_simple_rag_dependencies(
    env: Mapping[str, str],
    errors: list[str],
) -> None:
    if not _has_any(env, ("RAG_API_TYPE", "RAG_BASE_URL", "RAG_INDEX", "RAG_API_KEY")):
        return
    api_type = _normalized(env.get("RAG_API_TYPE", ""))
    if not api_type:
        errors.append("RAG_API_TYPE is required when using simple RAG config")
        return
    if api_type in {"qdrant", "cloud_rag"}:
        if not env.get("RAG_BASE_URL"):
            errors.append("RAG_BASE_URL is required for RAG_API_TYPE=qdrant")
        if not env.get("RAG_INDEX"):
            errors.append("RAG_INDEX is required for RAG_API_TYPE=qdrant")


def _has_any(env: Mapping[str, str], keys: tuple[str, ...]) -> bool:
    return any(bool(env.get(key)) for key in keys)


def _normalized(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _change_summary(
    key: str,
    new_value: str | None,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    field = ENV_CONFIG_FIELD_BY_KEY[key]
    action = "remove" if new_value is None else "set"
    data: dict[str, Any] = {
        "key": key,
        "action": action,
        "secret": field.secret,
        "restart_required": field.restartRequired,
        "hot_reload": field.hotReload,
        "before_status": before.get("status", "missing"),
        "after_status": after.get("status", "missing"),
    }
    if not field.secret:
        data["before"] = before.get("value")
        data["after"] = after.get("value")
    return data


def _read_env_document(path: Path | None) -> _EnvDocument:
    if path is None or not path.exists():
        return _EnvDocument()
    lines: list[_EnvLine] = []
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        parsed = _parse_env_line(raw_line, line_number)
        lines.append(parsed)
        if parsed.key is not None and parsed.value is not None:
            values[parsed.key] = parsed.value
    return _EnvDocument(lines=tuple(lines), values=values)


def _parse_env_line(raw_line: str, line_number: int) -> _EnvLine:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return _EnvLine(raw=raw_line)
    if line.startswith("export "):
        line = line.removeprefix("export ").strip()
    if "=" not in line:
        raise DTOValidationError(f".env line {line_number} must use KEY=VALUE syntax")
    key, raw_value = line.split("=", 1)
    key = key.strip()
    if not _ENV_KEY_RE.fullmatch(key):
        raise DTOValidationError(f".env key is invalid: {key}")
    return _EnvLine(raw=raw_line, key=key, value=_parse_env_value(raw_value.strip()))


def _parse_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return str(json.loads(value))
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value


def _write_env_document(
    path: Path,
    document: _EnvDocument,
    updates: Mapping[str, str | None],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output: list[str] = []
    handled: set[str] = set()
    for line in document.lines:
        if line.key is None or line.key not in updates:
            output.append(line.raw)
            continue
        handled.add(line.key)
        value = updates[line.key]
        if value is not None:
            output.append(f"{line.key}={_format_env_value(value)}")
    for key, value in updates.items():
        if key in handled or value is None:
            continue
        output.append(f"{key}={_format_env_value(value)}")
    path.write_text("\n".join(output) + ("\n" if output else ""), encoding="utf-8")


def _format_env_value(value: str) -> str:
    if value and _UNQUOTED_VALUE_RE.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)


def _looks_sensitive(key: str) -> bool:
    markers = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY", "DATABASE_URL", "REDIS_URL")
    return any(marker in key for marker in markers)
