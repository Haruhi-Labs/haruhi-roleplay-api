"""External system adapters."""

from haruhi_roleplay_api.adapters.access_tokens_sqlite import SQLiteAccessTokenStore
from haruhi_roleplay_api.adapters.backend_context import FakeBackendContextProvider
from haruhi_roleplay_api.adapters.embeddings import (
    HashEmbeddingProvider,
    LocalOpenAICompatibleEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
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
from haruhi_roleplay_api.adapters.rag_qdrant import QdrantRagService
from haruhi_roleplay_api.adapters.rag_vector import LocalVectorRagService
from haruhi_roleplay_api.adapters.rag import FakeRagService, LocalRagService
from haruhi_roleplay_api.adapters.sessions import InMemorySessionStore
from haruhi_roleplay_api.adapters.sessions_postgres import PostgresSessionStore
from haruhi_roleplay_api.adapters.sessions_sqlite import SQLiteSessionStore

__all__ = [
    "DeepSeekModelProvider",
    "FakeModelProvider",
    "FakeBackendContextProvider",
    "FakeRagService",
    "GeminiModelProvider",
    "HashEmbeddingProvider",
    "InMemoryMemoryStore",
    "InMemorySessionStore",
    "LocalOpenAICompatibleEmbeddingProvider",
    "LocalOpenAICompatibleModelProvider",
    "LocalPersonaRepository",
    "LocalRagService",
    "LocalVectorRagService",
    "OllamaEmbeddingProvider",
    "OllamaModelProvider",
    "OpenAICompatibleEmbeddingProvider",
    "OpenAIModelProvider",
    "OpenAIEmbeddingProvider",
    "OpenAICompatibleModelProvider",
    "PostgresSessionStore",
    "QdrantRagService",
    "SQLiteAccessTokenStore",
    "SQLiteSessionStore",
]
