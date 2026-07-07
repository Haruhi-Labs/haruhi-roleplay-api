from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.infrastructure.http_runtime import (  # noqa: E402
    HttpRuntimeStreamResponse,
)
from haruhi_roleplay_api.infrastructure.http_server import _write_response  # noqa: E402


class CapturingWFile:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.flush_count = 0

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        self.flush_count += 1


class CapturingHandler:
    def __init__(self) -> None:
        self.status: int | None = None
        self.headers: list[tuple[str, str]] = []
        self.headers_ended = False
        self.wfile = CapturingWFile()

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        self.headers_ended = True


class HttpServerStreamTests(unittest.TestCase):
    def test_stream_response_writes_each_sse_event_without_content_length(self) -> None:
        handler = CapturingHandler()
        done_seen_before_second_yield: list[bool] = []

        def events():
            yield {"event": "delta", "data": {"text": "半句"}}
            done_seen_before_second_yield.append(
                b"event: done" in b"".join(handler.wfile.writes)
            )
            yield {"event": "done", "data": {"reply": "半句"}}

        response = HttpRuntimeStreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream; charset=utf-8"},
            events=events(),
        )

        _write_response(handler, response)

        header_names = [key for key, _ in handler.headers]
        body = b"".join(handler.wfile.writes).decode("utf-8")

        self.assertEqual(handler.status, 200)
        self.assertTrue(handler.headers_ended)
        self.assertNotIn("Content-Length", header_names)
        self.assertEqual(done_seen_before_second_yield, [False])
        self.assertEqual(handler.wfile.flush_count, 2)
        self.assertIn("event: delta", body)
        self.assertIn("event: done", body)


if __name__ == "__main__":
    unittest.main()
