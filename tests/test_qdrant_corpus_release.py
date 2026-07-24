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
    embedding_release_fingerprint,
    publish_qdrant_corpus,
    versioned_collection_name,
)


class FakeReleaseQdrantService:
    collection = "haruhi_rag__haruhi-rag-test-version"

    def __init__(self, *, point_count: int = 1) -> None:
        self.point_count = point_count
        self.schema_ensured = False
        self.alias_switched = False
        self.exists = False
        self.increment_on_ingest = False
        self.ingested_document_ids: list[str] = []
        self.existing_documents: tuple[object, ...] = ()
        self.active_aliases: dict[str, str] = {}

    def ensure_collection_schema(self) -> None:
        self.schema_ensured = True

    def ingest(self, ingest_input: object) -> object:
        self.ingested_document_ids.append(str(ingest_input.documentId))
        if self.increment_on_ingest:
            self.point_count += 1
        return SimpleNamespace(chunkCount=1)

    def count_points(self, *, app_id: str | None = None) -> int:
        return self.point_count

    def switch_alias(self, alias: str) -> str:
        self.alias_switched = True
        return "haruhi_rag__old"

    def collection_exists(self) -> bool:
        return self.exists

    def aliases(self) -> dict[str, str]:
        return dict(self.active_aliases)

    def list_documents(self, *, app_id: str | None = None) -> tuple[object, ...]:
        return self.existing_documents


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

    def test_publish_rejects_existing_immutable_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            _write_record(path)
            service = FakeReleaseQdrantService()
            service.exists = True

            with self.assertRaisesRegex(AppError, "拒绝覆盖"):
                publish_qdrant_corpus(
                    service,  # type: ignore[arg-type]
                    path=path,
                    app_id="web-demo",
                    alias="haruhi_rag_live",
                )

        self.assertFalse(service.schema_ensured)
        self.assertFalse(service.alias_switched)

    def test_publish_resumes_verified_unreferenced_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            _write_records(path, count=2)
            service = FakeReleaseQdrantService(point_count=1)
            service.exists = True
            service.increment_on_ingest = True
            service.existing_documents = (
                SimpleNamespace(documentId="doc-1", chunkCount=1),
            )

            summary = publish_qdrant_corpus(
                service,  # type: ignore[arg-type]
                path=path,
                app_id="web-demo",
                alias="haruhi_rag_live",
                resume_existing=True,
            )

        self.assertEqual(service.ingested_document_ids, ["doc-2"])
        self.assertTrue(service.alias_switched)
        self.assertEqual(summary.ingest.documentCount, 2)
        self.assertEqual(summary.ingest.skippedDocumentCount, 1)
        self.assertEqual(summary.pointCount, 2)

    def test_publish_refuses_to_resume_active_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            _write_record(path)
            service = FakeReleaseQdrantService()
            service.exists = True
            service.active_aliases = {
                "haruhi_rag_live": service.collection,
            }

            with self.assertRaisesRegex(AppError, "拒绝续传"):
                publish_qdrant_corpus(
                    service,  # type: ignore[arg-type]
                    path=path,
                    app_id="web-demo",
                    alias="haruhi_rag_live",
                    resume_existing=True,
                )

        self.assertFalse(service.schema_ensured)
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
                embedding_fingerprint="emb-1234567890abcdef",
            ),
            "haruhi-rag-live__haruhi-rag-test-version__emb-1234567890abcdef",
        )

    def test_embedding_fingerprint_excludes_secret_and_changes_with_release(self) -> None:
        env = {
            "EMBEDDING_PROVIDER": "openai_compatible",
            "EMBEDDING_MODEL": "bge-m3",
            "EMBEDDING_BASE_URL": "https://embedding.internal",
            "EMBEDDING_DIMENSIONS": "1024",
            "EMBEDDING_API_KEY": "secret-a",
        }
        first = embedding_release_fingerprint(env)
        changed_secret = embedding_release_fingerprint(
            {**env, "EMBEDDING_API_KEY": "secret-b"}
        )
        changed_release = embedding_release_fingerprint(env, release_id="weights-v2")

        self.assertEqual(first, changed_secret)
        self.assertNotEqual(first, changed_release)
        self.assertRegex(first, r"^emb-[0-9a-f]{16}$")

    def test_corpus_file_must_have_one_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            _write_record(path)
            self.assertEqual(
                corpus_version_from_file(path),
                "haruhi-rag-test-version",
            )


def _write_record(path: Path) -> None:
    _write_records(path, count=1)


def _write_records(path: Path, *, count: int) -> None:
    records = []
    for index in range(1, count + 1):
        records.append(
            {
                "document_id": f"doc-{index}",
                "title": "测试语料",
                "character_id": "kyon",
                "timeline": "melancholy",
                "spoiler_level": 1,
                "language": "zh-CN",
                "source_type": "scene",
                "trust_level": "reviewed",
                "content": (
                    "作品：凉宫春日系列；篇章：测试；资料类型：场景；角色：阿虚。\n"
                    f"阿虚准备开始第 {index} 次社团活动。"
                ),
                "metadata": {
                    "corpus_version": "haruhi-rag-test-version",
                    "dataset_version": "haruhi-rag-test-version",
                    "record_schema_version": "haruhi-rag-record.v2",
                    "record_kind": "scene_memory",
                    "perspective": "kyon_first_person",
                    "retrieval_channel": "canonical_memory",
                    "knowledge_owner": "kyon",
                    "subject_character_id": "kyon",
                    "usage": "knowledge",
                },
            }
        )
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
