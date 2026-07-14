"""角色扮演 RAG 语料构建工具。"""

from haruhi_roleplay_api.corpus.haruhi import HARUHI_BOOKS
from haruhi_roleplay_api.corpus.dialogue_review import (
    DialogueReviewExportResult,
    DialogueReviewIndex,
    DialogueReviewUnit,
    ReviewAnnotation,
    export_dialogue_review_candidates,
    load_dialogue_review_index,
    load_dialogue_review_units,
    parse_review_annotations,
)
from haruhi_roleplay_api.corpus.pipeline import (
    BuildResult,
    CorpusRecord,
    build_haruhi_corpus,
    load_corpus_records,
)
from haruhi_roleplay_api.corpus.reviewed_dialogue import (
    DialogueOverlayResult,
    apply_reviewed_dialogue_overlay,
)

__all__ = [
    "HARUHI_BOOKS",
    "BuildResult",
    "CorpusRecord",
    "DialogueReviewExportResult",
    "DialogueReviewIndex",
    "DialogueReviewUnit",
    "DialogueOverlayResult",
    "ReviewAnnotation",
    "build_haruhi_corpus",
    "apply_reviewed_dialogue_overlay",
    "export_dialogue_review_candidates",
    "load_corpus_records",
    "load_dialogue_review_index",
    "load_dialogue_review_units",
    "parse_review_annotations",
]
