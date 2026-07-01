from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.application import PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    CapabilityConfig,
    CharacterProfile,
    GenerationConfig,
    PersonaPreset,
    PromptBuildInput,
)


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def prompt_input(character_id: str, persona_mode: str) -> PromptBuildInput:
    return PromptBuildInput(
        character=CharacterProfile.from_mapping(
            load_json(f"personas/{character_id}/character.json")
        ),
        persona=PersonaPreset.from_mapping(
            load_json(f"personas/{character_id}/{persona_mode}.json")
        ),
        userMessage="今天有什么计划？",
        capabilities=CapabilityConfig(),
        generation=GenerationConfig(styleIntensity=0.75, allowNarration=True),
    )


class PromptBuilderV1Tests(unittest.TestCase):
    def test_messages_have_stable_order(self) -> None:
        output = PersonaPromptBuilder().build(
            prompt_input("haruhi", "mid_late_haruhi")
        )

        self.assertEqual(
            [message.role for message in output.messages],
            ["system", "system", "system", "system", "user"],
        )
        self.assertIn("系统安全边界", output.messages[0].content)
        self.assertIn("角色设定", output.messages[1].content)
        self.assertIn("时间线和知识边界", output.messages[2].content)
        self.assertIn("输出规则", output.messages[3].content)
        self.assertEqual(output.messages[4].content, "今天有什么计划？")

    def test_different_character_produces_different_persona_section(self) -> None:
        haruhi = PersonaPromptBuilder().build(
            prompt_input("haruhi", "mid_late_haruhi")
        )
        kyon = PersonaPromptBuilder().build(prompt_input("kyon", "default_kyon"))

        self.assertNotEqual(haruhi.messages[1].content, kyon.messages[1].content)
        self.assertIn("SOS 团团长", haruhi.messages[1].content)
        self.assertIn("寻找异常", haruhi.messages[1].content)
        self.assertIn("SOS 团成员", kyon.messages[1].content)
        self.assertIn("吐槽异常", kyon.messages[1].content)

    def test_disabled_rag_and_memory_do_not_create_prompt_sections(self) -> None:
        output = PersonaPromptBuilder().build(
            prompt_input("haruhi", "mid_late_haruhi")
        )

        prompt_text = "\n".join(message.content for message in output.messages)

        self.assertNotIn("RAG", prompt_text)
        self.assertNotIn("memory", prompt_text)
        self.assertNotIn("长期记忆", prompt_text)
        self.assertNotIn("检索资料", prompt_text)

    def test_prompt_does_not_expose_internal_config_field_names(self) -> None:
        output = PersonaPromptBuilder().build(
            prompt_input("haruhi", "mid_late_haruhi")
        )

        prompt_text = "\n".join(message.content for message in output.messages)

        for raw_field in (
            "ToneConfig",
            "ragPolicy",
            "memoryPolicy",
            "safetyPolicy",
            "energy",
            "assertiveness",
            "warmth",
            "directness",
            "randomness",
        ):
            self.assertNotIn(raw_field, prompt_text)

    def test_output_can_be_converted_to_provider_messages(self) -> None:
        output = PersonaPromptBuilder().build(
            prompt_input("kyon", "default_kyon")
        )

        provider_messages = output.to_provider_messages()

        self.assertEqual(provider_messages[0]["role"], "system")
        self.assertIn("content", provider_messages[0])
        self.assertEqual(provider_messages[-1]["role"], "user")


if __name__ == "__main__":
    unittest.main()

