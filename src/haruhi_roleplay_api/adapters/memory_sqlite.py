"""SQLite-backed memory store for local persistence."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    DTOValidationError,
    MemoryDeleteCommand,
    MemoryId,
    MemoryItem,
    MemoryQuery,
    MemoryType,
    MemoryWriteCommand,
    PersonaModeId,
    UserId,
)


class SQLiteMemoryStore:
    def __init__(
        self,
        *,
        path: str | Path,
        busy_timeout_ms: int = 5000,
    ) -> None:
        self._path = _sqlite_path(path)
        self._busy_timeout_ms = busy_timeout_ms
        self._initialize_schema()

    def list_memories(self, query: MemoryQuery) -> tuple[MemoryItem, ...]:
        params: list[object] = [
            str(query.appId),
            str(query.userId),
            str(query.characterId),
            _persona_mode_value(query.personaMode),
        ]
        type_filter = ""
        if query.memoryTypes:
            placeholders = ", ".join("?" for _ in query.memoryTypes)
            type_filter = f" AND type IN ({placeholders})"
            params.extend(memory_type.value for memory_type in query.memoryTypes)
        params.append(query.limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    memory_id,
                    app_id,
                    user_id,
                    character_id,
                    persona_mode,
                    type,
                    content,
                    confidence,
                    reason,
                    created_at,
                    updated_at
                FROM memories
                WHERE app_id = ?
                    AND user_id = ?
                    AND character_id = ?
                    AND persona_mode IS ?
                    {type_filter}
                ORDER BY memory_order ASC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return tuple(_memory_from_row(row) for row in rows)

    def delete_memory(self, command: MemoryDeleteCommand) -> MemoryItem:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    memory_id,
                    app_id,
                    user_id,
                    character_id,
                    persona_mode,
                    type,
                    content,
                    confidence,
                    reason,
                    created_at,
                    updated_at
                FROM memories
                WHERE memory_id = ?
                    AND app_id = ?
                    AND user_id = ?
                    AND character_id = ?
                    AND persona_mode IS ?
                """,
                (
                    str(command.memoryId),
                    str(command.appId),
                    str(command.userId),
                    str(command.characterId),
                    _persona_mode_value(command.personaMode),
                ),
            ).fetchone()
            if row is not None:
                connection.execute(
                    "DELETE FROM memories WHERE memory_id = ?",
                    (str(command.memoryId),),
                )
        if row is None:
            raise AppError(
                code=ErrorCode.MEMORY_NOT_FOUND,
                message="Memory was not found.",
            )
        return _memory_from_row(row)

    def add_memory(self, command: MemoryWriteCommand) -> MemoryItem:
        now = _now()
        item = MemoryItem(
            memoryId=MemoryId(f"mem-{uuid4().hex}"),
            appId=command.appId,
            userId=command.userId,
            characterId=command.characterId,
            personaMode=command.personaMode,
            type=command.candidate.type,
            content=command.candidate.content,
            confidence=command.candidate.confidence,
            reason=command.candidate.reason,
            createdAt=now,
            updatedAt=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memories (
                    memory_id,
                    app_id,
                    user_id,
                    character_id,
                    persona_mode,
                    type,
                    content,
                    confidence,
                    reason,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(item.memoryId),
                    str(item.appId),
                    str(item.userId),
                    str(item.characterId),
                    _persona_mode_value(item.personaMode),
                    item.type.value,
                    item.content,
                    item.confidence,
                    item.reason,
                    item.createdAt,
                    item.updatedAt,
                ),
            )
        return item

    def _initialize_schema(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA_SQL)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self._path,
            timeout=self._busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    memory_order INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL UNIQUE,
    app_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    persona_mode TEXT,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_scope
ON memories(app_id, user_id, character_id, persona_mode, memory_order);

CREATE INDEX IF NOT EXISTS idx_memories_scope_type
ON memories(app_id, user_id, character_id, persona_mode, type, memory_order);
"""


def _memory_from_row(row: sqlite3.Row) -> MemoryItem:
    persona_mode = row["persona_mode"]
    return MemoryItem(
        memoryId=MemoryId(str(row["memory_id"])),
        appId=AppId(str(row["app_id"])),
        userId=UserId(str(row["user_id"])),
        characterId=CharacterId(str(row["character_id"])),
        personaMode=(
            PersonaModeId(str(persona_mode)) if persona_mode is not None else None
        ),
        type=MemoryType(str(row["type"])),
        content=str(row["content"]),
        confidence=float(row["confidence"]),
        reason=str(row["reason"]) if row["reason"] is not None else None,
        createdAt=str(row["created_at"]),
        updatedAt=str(row["updated_at"]),
    )


def _persona_mode_value(persona_mode: PersonaModeId | None) -> str | None:
    return str(persona_mode) if persona_mode is not None else None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sqlite_path(path: str | Path) -> str:
    raw_path = str(path).strip()
    if not raw_path:
        raise DTOValidationError("MEMORY_SQLITE_PATH must not be empty")
    return raw_path

