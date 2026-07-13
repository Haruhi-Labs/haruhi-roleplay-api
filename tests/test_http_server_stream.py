from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.infrastructure.http_runtime import (  # noqa: E402
    HttpRuntimeSettings,
    HttpRuntimeStreamResponse,
)
from haruhi_roleplay_api.infrastructure.http_server import (  # noqa: E402
    RoleplayRequestHandler,
    _RequestBodyTooLargeError,
    _validate_server_settings,
    _write_response,
)
from haruhi_roleplay_api.domain.request_limits import (  # noqa: E402
    MAX_HTTP_BODY_BYTES,
)


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


class DisconnectingWFile:
    def write(self, data: bytes) -> int:
        del data
        raise BrokenPipeError("client disconnected")

    def flush(self) -> None:
        return


class DisconnectingHandler(CapturingHandler):
    def __init__(self) -> None:
        super().__init__()
        self.wfile = DisconnectingWFile()


class ExplodingRFile:
    def read(self, length: int) -> bytes:
        raise AssertionError("oversized request body must not be read")


class OversizedBodyHandler:
    def __init__(self) -> None:
        self.headers = {"Content-Length": str(MAX_HTTP_BODY_BYTES + 1)}
        self.rfile = ExplodingRFile()


class HttpServerStreamTests(unittest.TestCase):
    def test_loopback_bind_does_not_require_admin_key(self) -> None:
        _validate_server_settings(HttpRuntimeSettings(host="127.0.0.1"))
        _validate_server_settings(HttpRuntimeSettings(host="::1"))
        _validate_server_settings(HttpRuntimeSettings(host="localhost"))

    def test_non_loopback_bind_requires_strong_admin_key(self) -> None:
        for api_key in (None, "short", "change-me-to-a-long-placeholder-value"):
            with self.subTest(api_key=api_key):
                with self.assertRaisesRegex(ValueError, "Non-loopback"):
                    _validate_server_settings(
                        HttpRuntimeSettings(host="0.0.0.0", api_key=api_key)
                    )

    def test_non_loopback_bind_accepts_strong_admin_key(self) -> None:
        _validate_server_settings(
            HttpRuntimeSettings(host="0.0.0.0", api_key="a" * 32)
        )

    def test_oversized_content_length_is_rejected_before_read(self) -> None:
        with self.assertRaises(_RequestBodyTooLargeError):
            RoleplayRequestHandler._read_body(OversizedBodyHandler())

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

    def test_stream_disconnect_closes_event_iterator_without_raising(self) -> None:
        handler = DisconnectingHandler()
        iterator_closed: list[bool] = []

        def events():
            try:
                yield {"event": "delta", "data": {"text": "半句"}}
                yield {"event": "done", "data": {"reply": "半句"}}
            finally:
                iterator_closed.append(True)

        response = HttpRuntimeStreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream; charset=utf-8"},
            events=events(),
        )

        _write_response(handler, response)

        self.assertEqual(iterator_closed, [True])


if __name__ == "__main__":
    unittest.main()
