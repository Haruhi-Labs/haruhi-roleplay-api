"""External system adapters."""

from haruhi_roleplay_api.adapters.models import (
    FakeModelProvider,
    LocalOpenAICompatibleModelProvider,
)
from haruhi_roleplay_api.adapters.personas import LocalPersonaRepository

__all__ = [
    "FakeModelProvider",
    "LocalOpenAICompatibleModelProvider",
    "LocalPersonaRepository",
]

