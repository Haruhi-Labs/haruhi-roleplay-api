"""Runtime configuration loading and safe hot update support."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from haruhi_roleplay_api.domain import DTOValidationError

CONFIG_VALUES_FIELD = "values"

# TODO: 把可提供配置项单独封装
RUNTIME_CONFIG_KEYS = (
    "ENABLE_DEBUG_TRACE",
    "MODEL_ALIAS",
    "MODEL_API_KEY_ENV",
    "MODEL_BASE_URL",
    "MODEL_NAME",
    "MODEL_PROVIDER",
    "MODEL_PROVIDER_ID",
    "MODEL_PROVIDER_NAME",
    "MODEL_PROVIDER_REGISTRY",
    "MODEL_TIMEOUT_MS",
    "RAG_PROVIDER",
    "RAG_CHUNK_SIZE",
    "RAG_EMBEDDING_DIMENSIONS",
    "RAG_VECTOR_BACKEND",
    "LOCAL_VECTOR_RAG_BACKEND",
    "CHROMA_COLLECTION",
    "CHROMA_PERSIST_PATH",
    "QDRANT_URL",
    "QDRANT_COLLECTION",
    "QDRANT_TIMEOUT_MS",
    "QDRANT_ENSURE_COLLECTION",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_TIMEOUT_MS",
    "EMBEDDING_API_KEY_ENV",
    "EMBEDDING_PATH",
)

_RUNTIME_CONFIG_KEY_SET = set(RUNTIME_CONFIG_KEYS)
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNQUOTED_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:@-]+$")


@dataclass(frozen=True, kw_only=True)
class RuntimeConfigUpdate:
    values: Mapping[str, str | None]


class RuntimeConfigStore:
    def __init__(
        self,
        *,
        base_env: Mapping[str, str],
        config_path: Path | None = None,
    ) -> None:
        self._base_env = dict(base_env)
        self._config_path = config_path
        self._file_values = _read_env_file(config_path) if config_path else {}

    @classmethod
    def in_memory(cls, env: Mapping[str, str]) -> "RuntimeConfigStore":
        return cls(base_env=env)

    @classmethod
    def env_file(
        cls,
        *,
        project_root: Path,
        env: Mapping[str, str],
    ) -> "RuntimeConfigStore":
        configured_path = env.get("ROLEPLAY_CONFIG_FILE")
        config_path = (
            Path(configured_path)
            if configured_path is not None and configured_path.strip()
            else project_root / ".env"
        )
        return cls(base_env=env, config_path=config_path)

    @property
    def source(self) -> str:
        return str(self._config_path) if self._config_path else "memory"

    @property
    def persists_updates(self) -> bool:
        return self._config_path is not None

    def env(self) -> dict[str, str]:
        merged = dict(self._base_env)
        merged.update(self._file_values)
        return merged

    def public_snapshot(self) -> dict[str, Any]:
        env = self.env()
        values = {
            key: _public_value(key, env[key])
            for key in RUNTIME_CONFIG_KEYS
            if key in env
        }
        return {
            "source": self.source,
            "persists_updates": self.persists_updates,
            "configurable_keys": list(RUNTIME_CONFIG_KEYS),
            "values": values,
        }

    def parse_update(self, body: Mapping[str, Any]) -> RuntimeConfigUpdate:
        if not isinstance(body, Mapping):
            raise DTOValidationError("runtime config request body must be an object")
        raw_values = body.get(CONFIG_VALUES_FIELD, body)
        if not isinstance(raw_values, Mapping):
            raise DTOValidationError("runtime config values must be an object")
        values: dict[str, str | None] = {}
        for raw_key, raw_value in raw_values.items():
            key = _config_key(raw_key)
            _validate_config_key(key)
            if raw_value is None:
                values[key] = None
                continue
            values[key] = _config_value(key, raw_value)
        if not values:
            raise DTOValidationError("runtime config values must not be empty")
        return RuntimeConfigUpdate(values=values)

    def candidate_env(self, update: RuntimeConfigUpdate) -> dict[str, str]:
        file_values = dict(self._file_values)
        _apply_update(file_values, update)
        merged = dict(self._base_env)
        merged.update(file_values)
        return merged

    def commit(self, update: RuntimeConfigUpdate) -> tuple[str, ...]:
        _apply_update(self._file_values, update)
        if self._config_path is not None:
            _write_env_file(self._config_path, self._file_values)
        return tuple(update.values.keys())


def _apply_update(
    values: dict[str, str],
    update: RuntimeConfigUpdate,
) -> None:
    for key, value in update.values.items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = value


def _config_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError("runtime config key must be a non-empty string")
    return value.strip()


def _validate_config_key(key: str) -> None:
    if key not in _RUNTIME_CONFIG_KEY_SET:
        raise DTOValidationError(f"runtime config key is not allowed: {key}")
    if _is_sensitive_key(key):
        raise DTOValidationError(f"runtime config key is sensitive: {key}")


def _validate_env_file_key(key: str) -> None:
    if not _ENV_KEY_RE.fullmatch(key):
        raise DTOValidationError(f".env key is invalid: {key}")


def _config_value(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        normalized = value.strip()
    else:
        normalized = json.dumps(value, ensure_ascii=False)
    if not normalized:
        raise DTOValidationError(f"runtime config value must not be empty: {key}")
    if key == "MODEL_PROVIDER_REGISTRY":
        _validate_model_provider_registry(normalized)
    return normalized


def _validate_model_provider_registry(raw_value: str) -> None:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise DTOValidationError("MODEL_PROVIDER_REGISTRY must be valid JSON") from exc
    if _contains_inline_secret(parsed):
        raise DTOValidationError(
            "MODEL_PROVIDER_REGISTRY must use *_api_key_env instead of inline API keys"
        )


def _contains_inline_secret(value: Any) -> bool:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.replace("-", "_").lower()
            if normalized in {"api_key", "apikey", "token", "secret"}:
                return True
            if _contains_inline_secret(child):
                return True
    if isinstance(value, list):
        return any(_contains_inline_secret(item) for item in value)
    return False


def _public_value(key: str, value: str) -> Any:
    if key == "MODEL_PROVIDER_REGISTRY":
        return _registry_summary(value)
    if _is_sensitive_key(key):
        return "<redacted>"
    return value


def _registry_summary(raw_value: str) -> Mapping[str, Any]:
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError:
        return {"configured": True, "valid_json": False}
    providers = data.get("providers", {})
    aliases = data.get("aliases", {})
    provider_summary = {}
    if isinstance(providers, Mapping):
        provider_summary = {
            str(provider_id): {
                "type": str(provider_data.get("type", provider_id))
                if isinstance(provider_data, Mapping)
                else "<invalid>",
                "has_api_key_env": bool(
                    isinstance(provider_data, Mapping)
                    and provider_data.get("api_key_env")
                ),
            }
            for provider_id, provider_data in providers.items()
        }
    return {
        "configured": True,
        "valid_json": True,
        "default_alias": data.get("default_alias", data.get("defaultAlias")),
        "providers": provider_summary,
        "aliases": sorted(str(alias) for alias in aliases)
        if isinstance(aliases, Mapping)
        else [],
    }


def _is_sensitive_key(key: str) -> bool:
    if key.endswith("_API_KEY_ENV"):
        return False
    sensitive_markers = (
        "API_KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "PRIVATE_KEY",
        "DATABASE_URL",
        "REDIS_URL",
    )
    return any(marker in key for marker in sensitive_markers)


def _read_env_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise DTOValidationError(
                f".env line {line_number} must use KEY=VALUE syntax"
            )
        key, raw_value = line.split("=", 1)
        key = key.strip()
        _validate_env_file_key(key)
        values[key] = _parse_env_value(raw_value.strip())
    return values


def _parse_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return str(json.loads(value))
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value


def _write_env_file(path: Path, values: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{key}={_format_env_value(value)}" for key, value in sorted(values.items())
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _format_env_value(value: str) -> str:
    if value and _UNQUOTED_VALUE_RE.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)
