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


class DisappearancePromptBoundaryTests(unittest.TestCase):
    def test_haruhi_uses_altered_world_identity(self) -> None:
        self._assert_boundary(
            "haruhi",
            forbidden_fact="SOS 团团长。",
            required_facts=(
                "私立光阳园学院学生",
                "从未创建 SOS 团",
                "没有超能力",
            ),
        )

    def test_kyon_uses_only_his_retained_original_memory(self) -> None:
        self._assert_boundary(
            "kyon",
            forbidden_fact="SOS 团唯一的普通人",
            required_facts=(
                "世界改写的唯一记忆保有者与选择者",
                "只有你记得原来的 SOS 团",
                "不能要求他人自然认出自己",
            ),
        )

    def test_mikuru_uses_ordinary_student_identity(self) -> None:
        self._assert_boundary(
            "mikuru",
            forbidden_fact="SOS 团的温柔学姐。",
            required_facts=(
                "北高二年级普通学生、鹤屋的朋友",
                "不是未来人，也从未加入 SOS 团",
                "把阿虚视为陌生学弟",
            ),
        )

    def test_yuki_uses_ordinary_literature_club_identity(self) -> None:
        self._assert_boundary(
            "yuki",
            forbidden_fact="SOS 团成员、文艺社唯一正式社员。",
            required_facts=(
                "北高文艺社唯一社员、普通高中生",
                "没有资讯统合思念体",
                "不记得 SOS 团",
            ),
        )

    def test_itsuki_uses_ordinary_kouyouen_identity(self) -> None:
        self._assert_boundary(
            "itsuki",
            forbidden_fact="SOS 团副团长。",
            required_facts=(
                "私立光阳园学院学生、普通转学生",
                "没有超能力，也从未加入“机关”或 SOS 团",
                "把阿虚视为刚认识的北高学生",
            ),
        )

    def _assert_boundary(
        self,
        character_id: str,
        *,
        forbidden_fact: str,
        required_facts: tuple[str, ...],
    ) -> None:
        character = CharacterProfile.from_mapping(
            _load_json(f"personas/{character_id}/character.json")
        )
        persona = PersonaPreset.from_mapping(
            _load_json(
                f"personas/{character_id}/disappearance_{character_id}.json"
            )
        )
        output = PersonaPromptBuilder().build(
            PromptBuildInput(
                character=character,
                persona=persona,
                userMessage="你还记得 SOS 团和原来的大家吗？",
                capabilities=CapabilityConfig(),
                generation=GenerationConfig(),
            )
        )
        prompt_text = "\n".join(message.content for message in output.messages)

        self.assertNotIn(character.description, prompt_text)
        self.assertNotIn(forbidden_fact, prompt_text)
        for required_fact in required_facts:
            self.assertIn(required_fact, prompt_text)


def _load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
