from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CapabilityConfig,
    CharacterId,
    ChatInput,
    ChatOutput,
    DTOValidationError,
    GenerationConfig,
    PersonaModeId,
    RequestId,
    UserId,
)
from haruhi_roleplay_api.domain.request_limits import (  # noqa: E402
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_GENERATION_TOKENS,
    MAX_ID_LENGTH,
)


class ChatDTOContractTests(unittest.TestCase):
    def test_minimal_valid_chat_input_from_mapping(self) -> None:
        chat_input = ChatInput.from_mapping(
            {
                "appId": "web",
                "userId": "user-1",
                "characterId": "haruhi",
                "personaMode": "mid_late_haruhi",
                "message": "今天有什么计划？",
                "language": "zh-CN",
            }
        )

        self.assertEqual(chat_input.appId, AppId("web"))
        self.assertEqual(chat_input.userId, UserId("user-1"))
        self.assertEqual(chat_input.characterId, CharacterId("haruhi"))
        self.assertEqual(chat_input.personaMode, PersonaModeId("mid_late_haruhi"))
        self.assertFalse(chat_input.capabilities.rag)
        self.assertFalse(chat_input.capabilities.memory)
        self.assertFalse(chat_input.capabilities.continuousSession)
        self.assertTrue(chat_input.capabilities.safetyFilter)
        self.assertIsNone(chat_input.generation.model)
        self.assertEqual(chat_input.generation.temperature, 0.8)
        self.assertEqual(chat_input.generation.maxTokens, 800)

    def test_missing_required_field_fails(self) -> None:
        with self.assertRaisesRegex(DTOValidationError, "appId is required"):
            ChatInput.from_mapping(
                {
                    "userId": "user-1",
                    "characterId": "haruhi",
                    "personaMode": "mid_late_haruhi",
                    "message": "hello",
                    "language": "zh-CN",
                    "capabilities": {},
                }
            )

    def test_invalid_language_fails(self) -> None:
        with self.assertRaisesRegex(DTOValidationError, "language is not supported"):
            ChatInput.from_mapping(
                {
                    "appId": "web",
                    "userId": "user-1",
                    "characterId": "haruhi",
                    "personaMode": "mid_late_haruhi",
                    "message": "hello",
                    "language": "fr-FR",
                    "capabilities": {},
                }
            )

    def test_capability_config_defaults(self) -> None:
        capabilities = CapabilityConfig()

        self.assertFalse(capabilities.rag)
        self.assertFalse(capabilities.memory)
        self.assertFalse(capabilities.continuousSession)
        self.assertTrue(capabilities.safetyFilter)
        self.assertFalse(capabilities.debugTrace)
        self.assertFalse(capabilities.stream)

    def test_chat_message_and_id_length_limits(self) -> None:
        base = {
            "appId": "web",
            "userId": "user-1",
            "characterId": "haruhi",
            "personaMode": "mid_late_haruhi",
            "message": "hello",
            "language": "zh-CN",
            "capabilities": {},
        }
        for field_name, value, error_field in (
            ("message", "x" * (MAX_CHAT_MESSAGE_LENGTH + 1), "message"),
            ("appId", "x" * (MAX_ID_LENGTH + 1), "appId"),
        ):
            with self.subTest(field_name=field_name):
                data = {**base, field_name: value}
                with self.assertRaisesRegex(
                    DTOValidationError,
                    rf"{error_field} must be at most",
                ):
                    ChatInput.from_mapping(data)

    def test_generation_max_tokens_limit(self) -> None:
        with self.assertRaisesRegex(
            DTOValidationError,
            "generation.maxTokens must be at most",
        ):
            GenerationConfig(maxTokens=MAX_GENERATION_TOKENS + 1)

    def test_boolean_strings_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            DTOValidationError,
            "capabilities.rag must be a boolean",
        ):
            CapabilityConfig.from_mapping({"rag": "false"})
        with self.assertRaisesRegex(
            DTOValidationError,
            "generation.allowNarration must be a boolean",
        ):
            GenerationConfig.from_mapping({"allowNarration": "false"})

    def test_chat_output_minimal_contract(self) -> None:
        output = ChatOutput(
            requestId=RequestId("req-1"),
            characterId=CharacterId("haruhi"),
            personaMode=PersonaModeId("mid_late_haruhi"),
            reply="当然要做点有趣的事。",
        )

        self.assertEqual(output.requestId, RequestId("req-1"))
        self.assertIsNone(output.sessionId)
        self.assertEqual(output.reply, "当然要做点有趣的事。")


if __name__ == "__main__":
    unittest.main()
