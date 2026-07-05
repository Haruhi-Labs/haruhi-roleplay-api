"""Concrete model provider adapters."""

from haruhi_roleplay_api.adapters.models.deepseek import DeepSeekModelProvider
from haruhi_roleplay_api.adapters.models.fake import FakeModelProvider
from haruhi_roleplay_api.adapters.models.gemini import GeminiModelProvider
from haruhi_roleplay_api.adapters.models.ollama import OllamaModelProvider
from haruhi_roleplay_api.adapters.models.openai import OpenAIModelProvider
from haruhi_roleplay_api.adapters.models.openai_compatible import (
    LocalOpenAICompatibleModelProvider,
    OpenAICompatibleModelProvider,
)

__all__ = [
    "DeepSeekModelProvider",
    "FakeModelProvider",
    "GeminiModelProvider",
    "LocalOpenAICompatibleModelProvider",
    "OllamaModelProvider",
    "OpenAIModelProvider",
    "OpenAICompatibleModelProvider",
]
