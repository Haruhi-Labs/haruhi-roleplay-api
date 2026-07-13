"""Standard-library HTTP server for the roleplay runtime."""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from haruhi_roleplay_api.domain.request_limits import MAX_HTTP_BODY_BYTES
from haruhi_roleplay_api.infrastructure.http_runtime import (
    HttpRuntimeResponse,
    HttpRuntimeSettings,
    HttpRuntimeStreamResponse,
    RoleplayHttpRuntime,
    request_body_too_large_response,
    sse_event_bytes,
)
from haruhi_roleplay_api.infrastructure.runtime_config import RuntimeConfigStore


class _RequestBodyTooLargeError(ValueError):
    pass


class RoleplayRequestHandler(BaseHTTPRequestHandler):
    runtime: ClassVar[object]
    server_version = "HaruhiRoleplayHTTP/0.1"

    def do_OPTIONS(self) -> None:
        self._handle_request()

    def do_GET(self) -> None:
        self._handle_request()

    def do_POST(self) -> None:
        self._handle_request()

    def do_PATCH(self) -> None:
        self._handle_request()

    def do_DELETE(self) -> None:
        self._handle_request()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_request(self) -> None:
        try:
            body = self._read_body()
        except _RequestBodyTooLargeError:
            response = request_body_too_large_response(
                self.headers.get("X-Request-Id")
            )
            _write_response(self, response)
            return
        response = self.runtime.handle(
            method=self.command,
            target=self.path,
            headers=_headers(self),
            body=body,
        )
        _write_response(self, response)

    def _read_body(self) -> bytes:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            return b""
        try:
            length = int(content_length)
        except ValueError:
            return b""
        if length <= 0:
            return b""
        if length > MAX_HTTP_BODY_BYTES:
            raise _RequestBodyTooLargeError
        return self.rfile.read(length)


def run_server(settings: HttpRuntimeSettings | None = None) -> None:
    project_root = _project_root()
    env = dict(os.environ)
    if settings is not None:
        env.update(_settings_env(settings))
    config_store = RuntimeConfigStore.env_file(project_root=project_root, env=env)
    runtime_env = config_store.env()
    runtime_settings = settings or HttpRuntimeSettings.from_env(runtime_env)
    RoleplayRequestHandler.runtime = RoleplayHttpRuntime.local(
        project_root=project_root,
        env=env,
        runtime_config_store=config_store,
    )
    server = ThreadingHTTPServer(
        (runtime_settings.host, runtime_settings.port),
        RoleplayRequestHandler,
    )
    print(
        f"haruhi-roleplay-api listening on "
        f"http://{runtime_settings.host}:{runtime_settings.port}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _headers(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    return {key.lower(): value for key, value in handler.headers.items()}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _settings_env(settings: HttpRuntimeSettings) -> dict[str, str]:
    env: dict[str, str] = {}
    env["ROLEPLAY_HOST"] = settings.host
    env["ROLEPLAY_PORT"] = str(settings.port)
    env["ENABLE_DEBUG_TRACE"] = "true" if settings.debug_trace_enabled else "false"
    if settings.api_key is not None:
        env["ROLEPLAY_API_KEY"] = settings.api_key
    return env


def _write_response(
    handler: BaseHTTPRequestHandler,
    response: HttpRuntimeResponse | HttpRuntimeStreamResponse,
) -> None:
    if isinstance(response, HttpRuntimeStreamResponse):
        _write_stream_response(handler, response)
        return
    handler.send_response(response.status)
    for key, value in response.headers.items():
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(response.body)))
    handler.end_headers()
    if response.body:
        handler.wfile.write(response.body)


def _write_stream_response(
    handler: BaseHTTPRequestHandler,
    response: HttpRuntimeStreamResponse,
) -> None:
    handler.send_response(response.status)
    for key, value in response.headers.items():
        handler.send_header(key, value)
    handler.end_headers()
    for event in response.events:
        handler.wfile.write(sse_event_bytes(event))
        handler.wfile.flush()


if __name__ == "__main__":
    run_server()
