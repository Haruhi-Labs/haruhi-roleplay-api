"""Manual Ollama + Chroma smoke runner.

Run from the repository root:

    uv run --with chromadb python scripts/local_ollama_chroma_smoke.py

Prerequisites:

    ollama serve
    ollama pull qwen2.5:7b
    ollama pull nomic-embed-text
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from haruhi_roleplay_api.infrastructure import RoleplayHttpRuntime  # noqa: E402


class SmokeFailure(Exception):
    pass


@dataclass(frozen=True)
class SmokeSettings:
    ollama_base_url: str
    ollama_openai_base_url: str
    chat_model: str
    model_alias: str
    embedding_model: str
    embedding_dimensions: int
    chroma_collection: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "SmokeSettings":
        ollama_base_url = env.get("SMOKE_OLLAMA_BASE_URL", "http://localhost:11434").rstrip(
            "/"
        )
        return cls(
            ollama_base_url=ollama_base_url,
            ollama_openai_base_url=env.get(
                "SMOKE_OLLAMA_OPENAI_BASE_URL",
                f"{ollama_base_url}/v1",
            ).rstrip("/"),
            chat_model=env.get("SMOKE_CHAT_MODEL", "qwen2.5:7b"),
            model_alias=env.get("SMOKE_MODEL_ALIAS", "haruhi-ollama"),
            embedding_model=env.get("SMOKE_EMBEDDING_MODEL", "nomic-embed-text:latest"),
            embedding_dimensions=int(env.get("SMOKE_EMBEDDING_DIMENSIONS", "768")),
            chroma_collection=env.get("SMOKE_CHROMA_COLLECTION", "haruhi_manual_smoke"),
        )


def main() -> int:
    settings = SmokeSettings.from_env(os.environ)
    try:
        _run(settings)
    except SmokeFailure as exc:
        print()
        print("[failed]")
        print(str(exc))
        return 1
    return 0


def _run(settings: SmokeSettings) -> None:
    print("=== Haruhi Roleplay API manual smoke ===")
    print(f"Model provider: Ollama ({settings.chat_model})")
    print(f"Embedding provider: Ollama ({settings.embedding_model})")
    print(f"Vector store: Chroma ({settings.chroma_collection})")
    print()

    chroma_version = _chromadb_version()
    print(f"[preflight] chromadb -> {chroma_version}")

    model_names = _fetch_ollama_model_names(settings.ollama_base_url)
    _require_model(model_names, settings.chat_model, purpose="chat")
    _require_model(model_names, settings.embedding_model, purpose="embedding")
    print(f"[preflight] Ollama models -> {settings.chat_model}, {settings.embedding_model}")
    print()

    app = RoleplayHttpRuntime.local(project_root=ROOT, env=_runtime_env(settings))

    health = _call(app, "GET", "/health")
    print("[1/5] GET /health ->", health["data"]["status"])

    personas = _call(app, "GET", "/v1/personas")
    characters = ", ".join(
        character["character_id"] for character in personas["data"]["characters"]
    )
    print("[2/5] GET /v1/personas ->", characters)

    ingest = _call(app, "POST", "/v1/rag/documents", _rag_document_body())
    print(
        "[3/5] POST /v1/rag/documents ->",
        ingest["data"]["status"],
        f"chunks={ingest['data']['chunk_count']}",
    )

    search = _call(app, "POST", "/v1/rag/search", _rag_search_body())
    chunks = search["data"]["chunks"]
    print(
        "[4/5] POST /v1/rag/search ->",
        f"provider={search['data']['provider']}",
        f"hits={len(chunks)}",
    )
    if not chunks:
        raise SmokeFailure("RAG search returned no chunks.")
    for index, chunk in enumerate(chunks, start=1):
        score = round(float(chunk["score"]), 4)
        print(
            f"      source[{index}]",
            chunk["document_id"],
            f"score={score}",
            f"text={_preview(chunk['content'])}",
        )

    chat = _call(app, "POST", "/v1/chat", _chat_body(settings.model_alias))
    data = chat["data"]
    debug = data.get("debug") or {}
    print(
        "[5/5] POST /v1/chat ->",
        f"provider={data['usage']['provider']}",
        f"model_alias={data['usage']['model']}",
    )
    print(
        "      rag ->",
        f"provider={data['rag']['provider']}",
        f"sources={len(data['rag']['sources'])}",
    )
    print("      debug ->", f"model_route={debug.get('modelRoute')}")
    print()
    print("--- reply ---")
    print(data["reply"].strip())
    print("--- end ---")


def _runtime_env(settings: SmokeSettings) -> dict[str, str]:
    registry = {
        "default_alias": settings.model_alias,
        "providers": {
            "ollama-local": {
                "type": "ollama",
                "base_url": settings.ollama_openai_base_url,
                "timeout_ms": 180000,
            }
        },
        "aliases": {
            settings.model_alias: {
                "provider": "ollama-local",
                "model": settings.chat_model,
            }
        },
    }
    return {
        "MODEL_PROVIDER_REGISTRY": json.dumps(registry, ensure_ascii=False),
        "RAG_PROVIDER": "chroma",
        "RAG_CHUNK_SIZE": "220",
        "CHROMA_COLLECTION": settings.chroma_collection,
        "EMBEDDING_PROVIDER": "ollama",
        "EMBEDDING_MODEL": settings.embedding_model,
        "EMBEDDING_BASE_URL": settings.ollama_openai_base_url,
        "EMBEDDING_DIMENSIONS": str(settings.embedding_dimensions),
        "EMBEDDING_TIMEOUT_MS": "60000",
        "ENABLE_DEBUG_TRACE": "true",
    }


def _call(
    app: RoleplayHttpRuntime,
    method: str,
    target: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    response = app.handle(
        method=method,
        target=target,
        headers={
            "content-type": "application/json",
            "x-request-id": f"req-manual-smoke-{method.lower()}",
        },
        body=(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else b""
        ),
    )
    body = json.loads(response.body.decode("utf-8"))
    if response.status >= 400 or not body.get("ok", False):
        formatted = json.dumps(body, ensure_ascii=False, indent=2)
        raise SmokeFailure(f"{method} {target} failed with HTTP {response.status}\n{formatted}")
    return body


def _chromadb_version() -> str:
    try:
        import chromadb
    except ImportError as exc:
        raise SmokeFailure(
            "chromadb is not installed. Run:\n"
            "uv run --with chromadb python scripts/local_ollama_chroma_smoke.py"
        ) from exc
    return str(chromadb.__version__)


def _fetch_ollama_model_names(ollama_base_url: str) -> set[str]:
    try:
        with urllib.request.urlopen(f"{ollama_base_url}/api/tags", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SmokeFailure(
            f"Ollama is not reachable at {ollama_base_url}. "
            "Start Ollama before running this smoke."
        ) from exc
    return {
        str(item.get("name", ""))
        for item in data.get("models", [])
        if isinstance(item, Mapping)
    }


def _require_model(model_names: set[str], model: str, *, purpose: str) -> None:
    if _has_model(model_names, model):
        return
    available = ", ".join(sorted(model_names)) or "<none>"
    raise SmokeFailure(
        f"Ollama {purpose} model is missing: {model}\n"
        f"Available models: {available}\n"
        f"Install it with: ollama pull {model.removesuffix(':latest')}"
    )


def _has_model(model_names: set[str], model: str) -> bool:
    if model in model_names:
        return True
    return ":" not in model and f"{model}:latest" in model_names


def _rag_document_body() -> dict[str, Any]:
    return {
        "app_id": "web",
        "document_id": "doc-manual-smoke-sos-plan",
        "title": "SOS 团今日活动资料",
        "source_type": "timeline",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "timeline": "mid_late",
        "spoiler_level": 2,
        "language": "zh-CN",
        "content": (
            "SOS 团今日活动资料：春日准备在放学后召集全员，先检查社团教室，"
            "再去校内寻找异常线索。她会要求阿虚负责记录，长门负责资料整理，"
            "朝比奈学姐负责泡茶和稳定现场气氛。活动目标是把普通的一天变得不普通。"
        ),
    }


def _rag_search_body() -> dict[str, Any]:
    return {
        "app_id": "web",
        "user_id": "manual-smoke-user",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "query": "今天 SOS 团活动怎么安排？",
        "top_k": 3,
        "filters": {
            "source_types": ["timeline"],
            "timelines": ["mid_late"],
            "spoiler_level_max": 2,
            "language": "zh-CN",
        },
    }


def _chat_body(model_alias: str) -> dict[str, Any]:
    return {
        "app_id": "web",
        "user_id": "manual-smoke-user",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "春日，今天 SOS 团活动怎么安排？要按社团资料来。",
        "language": "zh-CN",
        "capabilities": {
            "rag": True,
            "memory": False,
            "continuous_session": False,
            "safety_filter": True,
            "debug_trace": True,
            "stream": False,
        },
        "generation": {
            "model": model_alias,
            "temperature": 0.6,
            "max_tokens": 160,
            "top_p": 0.9,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "style_intensity": 0.8,
            "allow_narration": False,
        },
    }


def _preview(text: str, *, limit: int = 72) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


if __name__ == "__main__":
    raise SystemExit(main())
