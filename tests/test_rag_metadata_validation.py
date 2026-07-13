from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import LocalPersonaRepository  # noqa: E402
from haruhi_roleplay_api.api.rag import post_rag_document  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    DTOValidationError,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
)


ROOT = Path(__file__).resolve().parents[1]


def valid_body() -> dict:
    return {
        "app_id": "web",
        "document_id": "doc-haruhi-1",
        "title": "中后期春日时间线资料",
        "source_type": "timeline",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "timeline": "mid_late",
        "spoiler_level": 2,
        "language": "zh-CN",
        "content": "用于 RAG 的资料文本。",
        "metadata": {
            "source": "manual-test",
        },
    }


def call_ingest(body: dict, request_id: str = "req-rag") -> dict:
    return post_rag_document(
        body,
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        request_id=request_id,
    )


class RagMetadataValidationTests(unittest.TestCase):
    def test_valid_metadata_passes(self) -> None:
        response = call_ingest(valid_body(), request_id="req-rag-valid")

        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "req-rag-valid")

        data = response["data"]
        metadata = data["metadata"]

        self.assertEqual(data["document_id"], "doc-haruhi-1")
        self.assertEqual(data["status"], "validated")
        self.assertEqual(data["chunk_count"], 0)
        self.assertEqual(metadata["app_id"], "web")
        self.assertEqual(metadata["character_id"], "haruhi")
        self.assertEqual(metadata["persona_mode"], "mid_late_haruhi")
        self.assertEqual(metadata["timeline"], "mid_late")
        self.assertEqual(metadata["spoiler_level"], 2)
        self.assertEqual(metadata["language"], "zh-CN")
        self.assertEqual(metadata["source_type"], "timeline")

    def test_missing_character_id_returns_validation_error(self) -> None:
        body = valid_body()
        body.pop("character_id")

        response = call_ingest(body, request_id="req-missing-character")

        self.assertFalse(response["ok"])
        self.assertEqual(response["request_id"], "req-missing-character")
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(response["error"]["message"], "characterId is required")

    def test_missing_spoiler_level_returns_validation_error(self) -> None:
        body = valid_body()
        body.pop("spoiler_level")

        response = call_ingest(body, request_id="req-missing-spoiler")

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(response["error"]["message"], "spoilerLevel is required")

    def test_illegal_timeline_returns_validation_error(self) -> None:
        body = valid_body()
        body["timeline"] = "disappearance"

        response = call_ingest(body, request_id="req-illegal-timeline")

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("timeline is not allowed", response["error"]["message"])

    def test_source_type_cannot_bypass_persona_policy(self) -> None:
        body = valid_body()
        body["source_type"] = "system_prompt"

        response = call_ingest(body, request_id="req-source-policy")

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("sourceType is not allowed", response["error"]["message"])

    def test_metadata_type_can_be_built_directly(self) -> None:
        metadata = RagDocumentMetadata.from_mapping(
            {
                "appId": "web",
                "characterId": "haruhi",
                "timeline": "mid_late",
                "spoilerLevel": 2,
                "language": "zh-CN",
                "sourceType": "timeline",
            }
        )

        self.assertEqual(metadata.appId, "web")
        self.assertEqual(metadata.characterId, "haruhi")
        self.assertEqual(metadata.timeline, "mid_late")

    def test_ingest_rejects_mismatched_metadata_app_scope(self) -> None:
        metadata = RagDocumentMetadata.from_mapping(
            {
                "appId": "app-b",
                "characterId": "haruhi",
                "timeline": "mid_late",
                "spoilerLevel": 2,
                "language": "zh-CN",
                "sourceType": "timeline",
            }
        )

        with self.assertRaisesRegex(
            DTOValidationError,
            "metadata.appId must match appId",
        ):
            RagIngestInput(
                appId=AppId("app-a"),
                documentId=RagDocumentId("doc-haruhi-1"),
                title="中后期春日时间线资料",
                content="用于 RAG 的资料文本。",
                metadata=metadata,
            )


if __name__ == "__main__":
    unittest.main()
