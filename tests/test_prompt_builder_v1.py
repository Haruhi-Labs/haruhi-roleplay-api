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
    def test_all_five_default_personas_build_distinct_character_sections(self) -> None:
        defaults = (
            ("haruhi", "mid_late_haruhi"),
            ("kyon", "default_kyon"),
            ("mikuru", "default_mikuru"),
            ("yuki", "default_yuki"),
            ("itsuki", "default_itsuki"),
        )

        sections = {
            PersonaPromptBuilder().build(prompt_input(character, mode)).messages[1].content
            for character, mode in defaults
        }

        self.assertEqual(len(sections), 5)

    def test_disappearance_yuki_uses_altered_world_identity(self) -> None:
        default = PersonaPromptBuilder().build(
            prompt_input("yuki", "default_yuki")
        )
        altered = PersonaPromptBuilder().build(
            prompt_input("yuki", "disappearance_yuki")
        )

        self.assertIn("资讯统合思念体的人形接口", default.messages[1].content)
        self.assertIn("北高文艺社唯一社员、普通高中生", altered.messages[1].content)
        self.assertIn("没有资讯统合思念体", altered.messages[1].content)

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
        self.assertIn("主动制造值得全团参与的有趣事件", haruhi.messages[1].content)
        self.assertIn("普通人视角", kyon.messages[1].content)
        self.assertIn("用常识和吐槽约束春日", kyon.messages[1].content)

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
