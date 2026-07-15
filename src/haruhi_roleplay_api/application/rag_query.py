"""角色扮演对话的确定性 RAG 查询构造。"""

from __future__ import annotations

from collections.abc import Iterable

from haruhi_roleplay_api.domain.request_limits import MAX_RAG_QUERY_LENGTH


def build_roleplay_rag_query(
    *,
    character_id: str,
    persona_mode: str,
    timeline: str,
    current_message: str,
    recent_messages: Iterable[tuple[str, str]] = (),
) -> str:
    header = (
        f"目标角色：{character_id}\n"
        f"角色模式：{persona_mode}\n"
        f"当前时间线：{timeline}"
    )
    current_label = "当前用户输入：\n"
    current_budget = MAX_RAG_QUERY_LENGTH - len(header) - len(current_label) - 2
    current = _bounded_rag_excerpt(current_message, max_chars=current_budget)
    suffix = f"{current_label}{current}"
    selected: list[str] = []
    messages = tuple(recent_messages)
    for role, content in reversed(messages[-6:]):
        line = f"{role}: {_bounded_rag_excerpt(content, max_chars=600)}"
        candidate = [line, *selected]
        history = "最近对话：\n" + "\n".join(candidate) + "\n"
        if len(f"{header}\n{history}{suffix}") > MAX_RAG_QUERY_LENGTH:
            break
        selected = candidate
    history = "最近对话：\n" + "\n".join(selected) + "\n" if selected else ""
    return f"{header}\n{history}{suffix}"


def _bounded_rag_excerpt(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    marker = "……[中间省略]……"
    available = max_chars - len(marker)
    if available <= 0:
        return text[:max_chars]
    head = (available * 2) // 3
    tail = available - head
    return f"{text[:head]}{marker}{text[-tail:]}"
