from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import FakeModelProvider  # noqa: E402
from haruhi_roleplay_api.application import ModelRouter, PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    CharacterProfile,
    GenerationConfig,
    ModelMessage,
    ModelRequest,
    PersonaPreset,
    PromptBuildInput,
    model_messages_from_prompt,
)


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def prompt_messages() -> tuple[ModelMessage, ...]:
    prompt_output = PersonaPromptBuilder().build(
        PromptBuildInput(
            character=CharacterProfile.from_mapping(
                load_json("personas/haruhi/character.json")
            ),
            persona=PersonaPreset.from_mapping(
                load_json("personas/haruhi/mid_late_haruhi.json")
            ),
            userMessage="今天有什么计划？",
        )
    )
    return model_messages_from_prompt(prompt_output.messages)


class FakeModelProviderTests(unittest.TestCase):
    def test_fake_model_generate_returns_stable_reply_and_usage(self) -> None:
        response = FakeModelProvider().generate(
            ModelRequest(
                messages=(
                    ModelMessage(role="system", content="系统提示"),
                    ModelMessage(role="user", content="今天有什么计划？"),
                ),
                model="fake-roleplay-model",
            )
        )

        self.assertEqual(response.provider, "fake")
        self.assertEqual(response.model, "fake-roleplay-model")
        self.assertEqual(response.reply, "[fake:fake-roleplay-model] 今天有什么计划？")
        self.assertGreater(response.usage.promptTokens, 0)
        self.assertGreater(response.usage.completionTokens, 0)
        self.assertEqual(
            response.usage.totalTokens,
            response.usage.promptTokens + response.usage.completionTokens,
        )

    def test_model_router_selects_fake_provider(self) -> None:
        router = ModelRouter(provider=FakeModelProvider())

        response = router.generate(
            prompt_messages(),
            GenerationConfig(model="fake-roleplay-model"),
        )

        self.assertEqual(response.provider, "fake")
        self.assertEqual(response.model, "fake-roleplay-model")
        self.assertEqual(response.debug["modelProvider"], "fake")

    def test_fake_model_accepts_prompt_builder_messages(self) -> None:
        response = ModelRouter(provider=FakeModelProvider()).generate(
            prompt_messages(),
            GenerationConfig(),
        )

        self.assertEqual(response.provider, "fake")
        self.assertIn("今天有什么计划？", response.reply)

    def test_fake_model_does_not_require_network_or_secret_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            response = ModelRouter(provider=FakeModelProvider()).generate(
                prompt_messages(),
                GenerationConfig(),
            )

        self.assertEqual(response.provider, "fake")
        self.assertEqual(response.model, "fake-roleplay-model")


if __name__ == "__main__":
    unittest.main()

