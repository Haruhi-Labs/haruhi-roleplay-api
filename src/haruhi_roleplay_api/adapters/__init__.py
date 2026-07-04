"""External system adapters."""

from haruhi_roleplay_api.adapters.memory import InMemoryMemoryStore
from haruhi_roleplay_api.adapters.models import (
    DeepSeekModelProvider,
    FakeModelProvider,
    GeminiModelProvider,
    LocalOpenAICompatibleModelProvider,
    OllamaModelProvider,
    OpenAIModelProvider,
    OpenAICompatibleModelProvider,
)
from haruhi_roleplay_api.adapters.personas import LocalPersonaRepository
from haruhi_roleplay_api.adapters.rag import FakeRagService, LocalRagService
from haruhi_roleplay_api.adapters.sessions import InMemorySessionStore

__all__ = [
    "DeepSeekModelProvider",
    "FakeModelProvider",
    "FakeRagService",
    "GeminiModelProvider",
    "InMemoryMemoryStore",
    "InMemorySessionStore",
    "LocalOpenAICompatibleModelProvider",
    "LocalPersonaRepository",
    "LocalRagService",
    "OllamaModelProvider",
    "OpenAIModelProvider",
    "OpenAICompatibleModelProvider",
]

