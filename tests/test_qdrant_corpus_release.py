from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.application.errors import AppError  # noqa: E402
from haruhi_roleplay_api.infrastructure.qdrant_corpus_release import (  # noqa: E402
    activate_qdrant_collection,
    corpus_version_from_file,
    publish_qdrant_corpus,
    versioned_collection_name,
)


class FakeReleaseQdrantService:
    collection = "haruhi_rag__haruhi-rag-test-version"

    def __init__(self, *, point_count: int = 1) -> None:
        self.point_count = point_count
        self.schema_ensured = False
        self.alias_switched = False
        self.exists = True

    def ensure_collection_schema(self) -> None:
        self.schema_ensured = True

    def ingest(self, ingest_input: object) -> object:
        return SimpleNamespace(chunkCount=1)

    def count_points(self, *, app_id: str | None = None) -> int:
        return self.point_count

    def switch_alias(self, alias: str) -> str:
        self.alias_switched = True
        return "haruhi_rag__old"

    def collection_exists(self) -> bool:
        return self.exists


class QdrantCorpusReleaseTests(unittest.TestCase):
    def test_publish_checks_count_before_switching_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            _write_record(path)
            service = FakeReleaseQdrantService()

            summary = publish_qdrant_corpus(
                service,  # type: ignore[arg-type]
                path=path,
                app_id="web-demo",
                alias="haruhi_rag_live",
            )

        self.assertTrue(service.schema_ensured)
        self.assertTrue(service.alias_switched)
        self.assertEqual(summary.corpusVersion, "haruhi-rag-test-version")
        self.assertEqual(summary.previousCollection, "haruhi_rag__old")
        self.assertEqual(summary.pointCount, 1)

    def test_publish_does_not_switch_alias_when_count_is_wrong(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            _write_record(path)
            service = FakeReleaseQdrantService(point_count=2)

            with self.assertRaises(AppError):
                publish_qdrant_corpus(
                    service,  # type: ignore[arg-type]
                    path=path,
                    app_id="web-demo",
                    alias="haruhi_rag_live",
                )

        self.assertFalse(service.alias_switched)

    def test_activate_rejects_missing_or_empty_collection(self) -> None:
        service = FakeReleaseQdrantService(point_count=0)
        with self.assertRaises(AppError):
            activate_qdrant_collection(
                service,  # type: ignore[arg-type]
                alias="haruhi_rag_live",
            )
        service.exists = False
        with self.assertRaises(AppError):
            activate_qdrant_collection(
                service,  # type: ignore[arg-type]
                alias="haruhi_rag_live",
            )

    def test_collection_name_is_derived_from_corpus_version(self) -> None:
        self.assertEqual(
            versioned_collection_name(
                prefix="haruhi rag/live",
                corpus_version="haruhi-rag-test-version",
            ),
            "haruhi-rag-live__haruhi-rag-test-version",
        )

    def test_corpus_file_must_have_one_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            _write_record(path)
            self.assertEqual(
                corpus_version_from_file(path),
                "haruhi-rag-test-version",
            )


def _write_record(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "document_id": "doc-1",
                "title": "测试语料",
                "character_id": "haruhi",
                "timeline": "melancholy",
                "spoiler_level": 1,
                "language": "zh-CN",
                "source_type": "dialogue",
                "trust_level": "reviewed",
                "content": "阿虚，快点开始社团活动！",
                "metadata": {"corpus_version": "haruhi-rag-test-version"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
