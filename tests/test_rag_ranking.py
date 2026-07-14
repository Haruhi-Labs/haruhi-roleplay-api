from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters.rag_ranking import rank_roleplay_chunks  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    RagChunk,
    RagChunkId,
    RagDocumentId,
    RagDocumentMetadata,
)


def _chunk(
    name: str,
    *,
    kind: str,
    scene: str | None,
    score: float,
    content: str | None = None,
    document_id: str | None = None,
) -> RagChunk:
    extra = {
        "record_kind": kind,
        "confidence": 0.95,
        "review_certainty": "certain",
    }
    if scene is not None:
        extra["scene_id"] = scene
    return RagChunk(
        chunkId=RagChunkId(f"chunk-{name}"),
        documentId=RagDocumentId(document_id or f"doc-{name}"),
        content=content or f"{name} 的角色资料",
        score=score,
        metadata=RagDocumentMetadata(
            appId=AppId("web"),
            characterId=CharacterId("haruhi"),
            timeline="mid_late",
            spoilerLevel=5,
            language="zh-CN",
            sourceType="scene",
            extra=extra,
        ),
    )


class RagRankingTests(unittest.TestCase):
    def test_roleplay_quotas_and_scene_dedup_keep_results_diverse(self) -> None:
        candidates = (
            _chunk("d1", kind="dialogue_example", scene="scene-a", score=0.99),
            _chunk("d2", kind="dialogue_example", scene="scene-a", score=0.98),
            _chunk("d3", kind="dialogue_example", scene="scene-b", score=0.97),
            _chunk("d4", kind="dialogue_example", scene="scene-c", score=0.96),
            _chunk("s1", kind="scene_memory", scene=None, score=0.95),
            _chunk("s2", kind="scene_memory", scene=None, score=0.94),
            _chunk("s3", kind="scene_memory", scene=None, score=0.93),
            _chunk("o1", kind="behavior_observation", scene=None, score=0.92),
            _chunk("i1", kind="inner_monologue", scene=None, score=0.91),
        )

        ranked = rank_roleplay_chunks(candidates, query="角色资料", top_k=6)

        kinds = Counter(chunk.metadata.extra["record_kind"] for chunk in ranked)
        scenes = [chunk.metadata.extra.get("scene_id") for chunk in ranked]
        self.assertEqual(len(ranked), 6)
        self.assertLessEqual(kinds["dialogue_example"], 2)
        self.assertLessEqual(kinds["scene_memory"], 2)
        self.assertLessEqual(kinds["behavior_observation"], 1)
        self.assertLessEqual(kinds["inner_monologue"], 1)
        self.assertEqual(scenes.count("scene-a"), 1)

    def test_document_and_normalized_content_duplicates_are_removed(self) -> None:
        candidates = (
            _chunk(
                "first",
                kind="dialogue_example",
                scene="scene-a",
                score=0.9,
                content="春日 现在行动",
                document_id="same-document",
            ),
            _chunk(
                "same-doc",
                kind="dialogue_example",
                scene="scene-b",
                score=0.8,
                content="另一分块",
                document_id="same-document",
            ),
            _chunk(
                "same-content",
                kind="dialogue_example",
                scene="scene-c",
                score=0.7,
                content="  春日   现在行动  ",
            ),
        )

        ranked = rank_roleplay_chunks(candidates, query="春日行动", top_k=3)

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].chunkId, "chunk-first")

    def test_lexical_overlap_can_promote_a_slightly_lower_dense_hit(self) -> None:
        unrelated = _chunk(
            "unrelated",
            kind="scene_memory",
            scene=None,
            score=0.8,
            content="今天在教室里喝茶。",
        )
        relevant = _chunk(
            "relevant",
            kind="scene_memory",
            scene=None,
            score=0.78,
            content="春日决定开展外星人搜寻行动。",
        )

        ranked = rank_roleplay_chunks(
            (unrelated, relevant),
            query="外星人搜寻行动",
            top_k=2,
        )

        self.assertEqual(ranked[0].chunkId, "chunk-relevant")


if __name__ == "__main__":
    unittest.main()
