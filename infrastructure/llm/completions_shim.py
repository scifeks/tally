"""Shim that translates OpenAI completions API to Ollama generate API.

This shim bridges the gap between Antares CLI (which expects OpenAI-style
/v1/completions endpoint) and Ollama (which exposes /api/generate).
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_REQUEST_BYTES = 10 * 1024 * 1024


class _QuietHTTPServer(HTTPServer):
    """HTTPServer that silences broken-pipe tracebacks on stderr."""

    def handle_error(self, _request: Any, _client_address: Any) -> None:
        logger.debug("Suppressed HTTP handler error", exc_info=True)


def translate_completions_to_generate(
    openai_req: dict[str, Any], model: str
) -> dict[str, Any]:
    """Map OpenAI completions fields to Ollama generate format."""
    prompt = openai_req.get("prompt", "")
    if not isinstance(prompt, str):
        prompt = str(prompt)

    return {
        "model": model,
        "prompt": prompt,
        "raw": True,
        "stream": openai_req.get("stream", False),
        "options": {
            "temperature": openai_req.get("temperature", 0.7),
            "top_p": openai_req.get("top_p", 1.0),
            "frequency_penalty": openai_req.get("frequency_penalty", 0.0),
            "num_predict": openai_req.get("max_tokens", 512),
            "stop": openai_req.get("stop", []),
        },
    }


def translate_generate_to_completions(ollama_resp: dict[str, Any]) -> dict[str, Any]:
    """Map Ollama generate response to OpenAI completions format."""
    return {
        "choices": [
            {
                "text": ollama_resp.get("response", ""),
                "finish_reason": "stop" if ollama_resp.get("done", False) else None,
            }
        ]
    }


class CompletionsShim:
    """HTTP server that shims OpenAI completions API to Ollama generate API."""

    def __init__(self, ollama_url: str, model: str, timeout: float = 300.0) -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        """Start the shim on a random port and return its URL."""
        handler = self._make_handler()
        self._server = _QuietHTTPServer(("127.0.0.1", 0), handler)
        addr = self._server.server_address
        host = addr[0]
        port = addr[1]
        self._thread = threading.Thread(target=self._server.serve_forever)
        self._thread.daemon = True
        self._thread.start()
        url = f"http://{host}:{port}"
        logger.info("Completions shim started at %s", url)
        return url

    def stop(self) -> None:
        """Shutdown the server and wait for the thread to finish."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Completions shim stopped")

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        """Create a request handler class bound to this shim instance."""
        ollama_url = self._ollama_url
        model = self._model
        request_timeout = self._timeout

        class CompletionsHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                """Handle POST requests to /v1/completions."""
                if self.path != "/v1/completions":
                    self.send_error(404)
                    return

                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                except ValueError as e:
                    logger.error("Invalid Content-Length header: %s", e)
                    self.send_error(400, "Invalid Content-Length")
                    return

                if content_length > MAX_REQUEST_BYTES:
                    self.send_error(413, "Request too large")
                    return

                try:
                    body = self.rfile.read(content_length)
                    openai_req = json.loads(body)
                except json.JSONDecodeError as e:
                    logger.error("Invalid request body: %s", e)
                    self.send_error(400, "Invalid JSON")
                    return

                ollama_req = translate_completions_to_generate(openai_req, model)
                is_streaming = openai_req.get("stream", False)

                try:
                    if is_streaming:
                        self._handle_streaming(ollama_req)
                    else:
                        self._handle_non_streaming(ollama_req)
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as e:
                    logger.error("Error proxying to Ollama: %s", e)
                    try:
                        self.send_error(502, "Bad Gateway")
                    except (BrokenPipeError, ConnectionResetError):
                        return

            def _handle_non_streaming(self, ollama_req: dict[str, Any]) -> None:
                """Handle non-streaming completion request."""
                with httpx.Client() as client:
                    try:
                        response = client.post(
                            f"{ollama_url}/api/generate",
                            json=ollama_req,
                            timeout=httpx.Timeout(
                                request_timeout,
                                read=request_timeout,
                            ),
                        )
                        response.raise_for_status()
                    except httpx.HTTPError:
                        self.send_error(502)
                        return

                ollama_resp = response.json()
                if "response" not in ollama_resp:
                    self.send_error(502, "Invalid Ollama response")
                    return

                completions_resp = translate_generate_to_completions(ollama_resp)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(completions_resp).encode())

            def _handle_streaming(self, ollama_req: dict[str, Any]) -> None:
                """Handle streaming completion request via Server-Sent Events."""
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                with httpx.stream(
                    "POST",
                    f"{ollama_url}/api/generate",
                    json=ollama_req,
                    timeout=httpx.Timeout(
                        request_timeout,
                        read=request_timeout,
                    ),
                ) as http_response:
                    if http_response.status_code != 200:
                        error_resp = json.dumps(
                            {"choices": [{"text": "", "finish_reason": "error"}]}
                        )
                        self.wfile.write(f"data: {error_resp}\n\n".encode())
                        self.wfile.write(b"data: [DONE]\n\n")
                        return

                    for line in http_response.iter_lines():
                        if not line:
                            continue
                        try:
                            ollama_resp = json.loads(line)
                            if "response" not in ollama_resp:
                                continue

                            completions_resp = translate_generate_to_completions(
                                ollama_resp
                            )
                            sse_line = f"data: {json.dumps(completions_resp)}\n\n"
                            self.wfile.write(sse_line.encode())
                        except json.JSONDecodeError as e:
                            logger.debug(
                                "Skipping non-JSON line in Ollama stream: %s",
                                e,
                            )

                self.wfile.write(b"data: [DONE]\n\n")

            def log_message(
                self,
                _format: str,
                *_args: Any,
            ) -> None:
                """Suppress default logging."""
                pass

        return CompletionsHandler
