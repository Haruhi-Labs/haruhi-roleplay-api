"""Standard-library HTTP server for the roleplay runtime."""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

from haruhi_roleplay_api.infrastructure.http_runtime import (
    HttpRuntimeResponse,
    HttpRuntimeSettings,
    create_local_runtime,
)


class RoleplayRequestHandler(BaseHTTPRequestHandler):
    runtime: ClassVar[object]
    server_version = "HaruhiRoleplayHTTP/0.1"

    def do_OPTIONS(self) -> None:
        self._handle_request()

    def do_GET(self) -> None:
        self._handle_request()

    def do_POST(self) -> None:
        self._handle_request()

    def do_DELETE(self) -> None:
        self._handle_request()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_request(self) -> None:
        response = self.runtime.handle(
            method=self.command,
            target=self.path,
            headers=_headers(self),
            body=self._read_body(),
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
        return self.rfile.read(length)


def run_server(settings: HttpRuntimeSettings | None = None) -> None:
    runtime_settings = settings or HttpRuntimeSettings.from_env(os.environ)
    runtime_env = _runtime_env(runtime_settings)
    RoleplayRequestHandler.runtime = create_local_runtime(runtime_env)
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


def _runtime_env(settings: HttpRuntimeSettings) -> dict[str, str]:
    env = dict(os.environ)
    env["ROLEPLAY_HOST"] = settings.host
    env["ROLEPLAY_PORT"] = str(settings.port)
    env["ENABLE_DEBUG_TRACE"] = "true" if settings.debug_trace_enabled else "false"
    if settings.api_key is not None:
        env["ROLEPLAY_API_KEY"] = settings.api_key
    return env


def _write_response(
    handler: BaseHTTPRequestHandler,
    response: HttpRuntimeResponse,
) -> None:
    handler.send_response(response.status)
    for key, value in response.headers.items():
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(response.body)))
    handler.end_headers()
    if response.body:
        handler.wfile.write(response.body)


if __name__ == "__main__":
    run_server()
