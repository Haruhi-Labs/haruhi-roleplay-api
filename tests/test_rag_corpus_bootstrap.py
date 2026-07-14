from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    PersonaModeId,
    RagRetrieveFilters,
    RagRetrieveInput,
    UserId,
)
from haruhi_roleplay_api.infrastructure import build_rag_service_from_env  # noqa: E402


def _record(*, document_id: str, character_id: str, content: str) -> dict:
    return {
        "document_id": document_id,
        "title": "凉宫春日的忧郁·第一章·台词",
        "character_id": character_id,
        "timeline": "melancholy",
        "spoiler_level": 1,
        "language": "zh-CN",
        "source_type": "scene",
        "trust_level": "canonical_attributed",
        "content": content,
        "metadata": {
            "record_kind": "dialogue_example",
            "perspective": "spoken_by_character",
            "confidence": 0.98,
            "book_title": "凉宫春日的忧郁",
            "section_title": "第一章",
        },
    }


class RagCorpusBootstrapTests(unittest.TestCase):
    def test_factory_bootstraps_jsonl_and_keeps_app_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            rows = (
                _record(
                    document_id="haruhi-test-haruhi",
                    character_id="haruhi",
                    content="春日宣布今天要进行社团招募。",
                ),
                _record(
                    document_id="haruhi-test-kyon",
                    character_id="kyon",
                    content="阿虚认为这又是一场麻烦。",
                ),
            )
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )
            service = build_rag_service_from_env(
                {
                    "RAG_PROVIDER": "local",
                    "RAG_CHUNK_SIZE": "8",
                    "RAG_BOOTSTRAP_CORPUS_PATH": str(path),
                    "RAG_BOOTSTRAP_APP_ID": "web-demo",
                }
            )

        documents = service.list_documents(app_id="web-demo")
        output = service.retrieve(
            RagRetrieveInput(
                appId=AppId("web-demo"),
                userId=UserId("user-1"),
                characterId=CharacterId("haruhi"),
                personaMode=PersonaModeId("melancholy_haruhi"),
                query="社团 招募",
                topK=3,
                filters=RagRetrieveFilters(
                    sourceTypes=("scene",),
                    timelines=("melancholy",),
                    spoilerLevelMax=1,
                    language="zh-CN",
                ),
            )
        )

        self.assertEqual(len(output.chunks), 1)
        self.assertEqual(documents[0].chunkCount, 1)
        self.assertTrue(output.chunks[0].metadata.extra["atomic_record"])
        self.assertEqual(output.chunks[0].documentId, "haruhi-test-haruhi")
        self.assertEqual(
            output.chunks[0].metadata.extra["record_kind"],
            "dialogue_example",
        )
        self.assertEqual(
            output.chunks[0].to_source_mapping()["perspective"],
            "spoken_by_character",
        )

    def test_bootstrap_requires_explicit_app_id(self) -> None:
        with self.assertRaises(AppError) as context:
            build_rag_service_from_env(
                {
                    "RAG_PROVIDER": "local",
                    "RAG_BOOTSTRAP_CORPUS_PATH": "missing.jsonl",
                }
            )

        self.assertEqual(context.exception.code, ErrorCode.RAG_INGEST_FAILED)
        self.assertIn("RAG_BOOTSTRAP_APP_ID", context.exception.public_message)

    def test_allowed_persona_modes_prevent_disappearance_perspective_leak(self) -> None:
        row = _record(
            document_id="haruhi-test-altered-yuki",
            character_id="yuki",
            content="普通世界的长门有希安静地递出入社申请表。",
        )
        row["timeline"] = "disappearance"
        row["spoiler_level"] = 4
        row["metadata"]["allowed_persona_modes"] = ["disappearance_yuki"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            service = build_rag_service_from_env(
                {
                    "RAG_PROVIDER": "local",
                    "RAG_BOOTSTRAP_CORPUS_PATH": str(path),
                    "RAG_BOOTSTRAP_APP_ID": "web-demo",
                }
            )

        def retrieve(persona_mode: str):
            return service.retrieve(
                RagRetrieveInput(
                    appId=AppId("web-demo"),
                    userId=UserId("user-1"),
                    characterId=CharacterId("yuki"),
                    personaMode=PersonaModeId(persona_mode),
                    query="入社申请表",
                    topK=3,
                    filters=RagRetrieveFilters(
                        sourceTypes=("scene",),
                        timelines=("disappearance",),
                        spoilerLevelMax=4,
                        language="zh-CN",
                    ),
                )
            )

        self.assertEqual(len(retrieve("disappearance_yuki").chunks), 1)
        self.assertEqual(retrieve("default_yuki").chunks, ())


if __name__ == "__main__":
    unittest.main()
