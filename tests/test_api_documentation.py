from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.adapters import LocalPersonaRepository  # noqa: E402
from haruhi_roleplay_api.api.personas import get_personas  # noqa: E402


PRODUCTION_DOC = ROOT / "docs" / "usage" / "production-api.md"
FRONTEND_DOC = ROOT / "docs" / "usage" / "frontend-api-calling.md"


class ApiDocumentationTests(unittest.TestCase):
    def test_production_business_routes_are_documented(self) -> None:
        text = PRODUCTION_DOC.read_text(encoding="utf-8")

        self.assertIn("https://roleplay.haruyuki.cn", text)
        for route in (
            "GET /health",
            "GET /v1/personas",
            "POST /v1/sessions",
            "POST /v1/chat",
            "POST /v1/chat/stream",
            "POST /v1/rag/documents",
            "POST /v1/rag/search",
            "GET /v1/memory/{user_id}",
            "DELETE /v1/memory/{user_id}/{memory_id}",
        ):
            with self.subTest(route=route):
                self.assertIn(route, text)

        self.assertIn("不属于外部系统接入", text)

    def test_public_persona_catalog_is_present_in_production_doc(self) -> None:
        text = PRODUCTION_DOC.read_text(encoding="utf-8")
        response = get_personas(
            LocalPersonaRepository(ROOT / "personas"),
            request_id="req-api-docs",
        )

        self.assertTrue(response["ok"])
        for character in response["data"]["characters"]:
            with self.subTest(character_id=character["character_id"]):
                self.assertIn(f"`{character['character_id']}`", text)
            for mode in character["modes"]:
                with self.subTest(persona_mode=mode["persona_mode"]):
                    self.assertIn(f"`{mode['persona_mode']}`", text)

    def test_configurable_chat_fields_are_documented(self) -> None:
        text = PRODUCTION_DOC.read_text(encoding="utf-8")

        for field in (
            "request_id",
            "app_id",
            "user_id",
            "session_id",
            "character_id",
            "persona_mode",
            "message",
            "language",
            "rag",
            "memory",
            "continuous_session",
            "safety_filter",
            "debug_trace",
            "stream",
            "model",
            "temperature",
            "max_tokens",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
            "style_intensity",
            "allow_narration",
        ):
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", text)

    def test_rag_search_filters_are_documented(self) -> None:
        text = PRODUCTION_DOC.read_text(encoding="utf-8")

        for field in (
            "source_types",
            "timelines",
            "record_kinds",
            "perspectives",
            "corpus_versions",
            "retrieval_channels",
            "knowledge_owners",
            "usages",
            "spoiler_level_max",
            "language",
        ):
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", text)

    def test_frontend_memory_example_uses_valid_type(self) -> None:
        text = FRONTEND_DOC.read_text(encoding="utf-8")

        self.assertIn('"type": "user_preference"', text)
        self.assertNotIn('"type": "preference"', text)


if __name__ == "__main__":
    unittest.main()
