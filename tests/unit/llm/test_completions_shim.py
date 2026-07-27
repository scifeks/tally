"""Unit tests for completions shim translation and lifecycle."""

from __future__ import annotations

import socket
from typing import Any

from infrastructure.llm.completions_shim import (
    CompletionsShim,
    translate_completions_to_generate,
    translate_generate_to_completions,
)


class TestTranslateCompletionsToGenerate:
    """Tests for OpenAI -> Ollama request translation."""

    def test_maps_prompt(self) -> None:
        result = translate_completions_to_generate(
            {"prompt": "hello world"}, "test-model"
        )
        assert result["prompt"] == "hello world"

    def test_maps_max_tokens_to_num_predict(self) -> None:
        result = translate_completions_to_generate(
            {"prompt": "", "max_tokens": 4096}, "test-model"
        )
        assert result["options"]["num_predict"] == 4096

    def test_maps_temperature(self) -> None:
        result = translate_completions_to_generate(
            {"prompt": "", "temperature": 0.3}, "test-model"
        )
        assert result["options"]["temperature"] == 0.3

    def test_maps_top_p(self) -> None:
        result = translate_completions_to_generate(
            {"prompt": "", "top_p": 0.9}, "test-model"
        )
        assert result["options"]["top_p"] == 0.9

    def test_maps_frequency_penalty(self) -> None:
        result = translate_completions_to_generate(
            {"prompt": "", "frequency_penalty": 0.3}, "test-model"
        )
        assert result["options"]["frequency_penalty"] == 0.3

    def test_maps_stop_tokens(self) -> None:
        stops = ["<|end_of_text|>", "<|start_of_role|>"]
        result = translate_completions_to_generate(
            {"prompt": "", "stop": stops}, "test-model"
        )
        assert result["options"]["stop"] == stops

    def test_sets_raw_true(self) -> None:
        result = translate_completions_to_generate({"prompt": ""}, "test-model")
        assert result["raw"] is True

    def test_sets_model(self) -> None:
        result = translate_completions_to_generate({"prompt": ""}, "granite-3.0-1b")
        assert result["model"] == "granite-3.0-1b"

    def test_maps_stream(self) -> None:
        result_streaming = translate_completions_to_generate(
            {"prompt": "", "stream": True}, "test-model"
        )
        assert result_streaming["stream"] is True

        result_non_streaming = translate_completions_to_generate(
            {"prompt": "", "stream": False}, "test-model"
        )
        assert result_non_streaming["stream"] is False

    def test_defaults_stream_false(self) -> None:
        result = translate_completions_to_generate({"prompt": ""}, "test-model")
        assert result["stream"] is False

    def test_full_antares_request(self) -> None:
        antares_req: dict[str, Any] = {
            "prompt": "<|start_of_role|>system<|end_of_role|>...",
            "max_tokens": 4096,
            "temperature": 0.3,
            "top_p": 1.0,
            "frequency_penalty": 0.3,
            "stop": ["<|end_of_text|>", "<|start_of_role|>"],
            "stream": True,
        }
        result = translate_completions_to_generate(antares_req, "granite-3.0-1b")
        assert result["model"] == "granite-3.0-1b"
        assert result["prompt"] == "<|start_of_role|>system<|end_of_role|>..."
        assert result["raw"] is True
        assert result["stream"] is True
        assert result["options"]["num_predict"] == 4096
        assert result["options"]["temperature"] == 0.3
        assert result["options"]["frequency_penalty"] == 0.3


class TestTranslateGenerateToCompletions:
    """Tests for Ollama -> OpenAI response translation."""

    def test_non_streaming_done(self) -> None:
        ollama_resp = {"response": "The file contains...", "done": True}
        result = translate_generate_to_completions(ollama_resp)
        assert result["choices"][0]["text"] == "The file contains..."
        assert result["choices"][0]["finish_reason"] == "stop"

    def test_streaming_not_done(self) -> None:
        ollama_resp = {"response": "The", "done": False}
        result = translate_generate_to_completions(ollama_resp)
        assert result["choices"][0]["text"] == "The"
        assert result["choices"][0]["finish_reason"] is None

    def test_empty_response(self) -> None:
        ollama_resp = {"response": "", "done": False}
        result = translate_generate_to_completions(ollama_resp)
        assert result["choices"][0]["text"] == ""

    def test_missing_response_field(self) -> None:
        ollama_resp = {"done": True}
        result = translate_generate_to_completions(ollama_resp)
        assert result["choices"][0]["text"] == ""


class TestCompletionsShimLifecycle:
    """Tests for CompletionsShim startup and shutdown."""

    def test_start_returns_url(self) -> None:
        shim = CompletionsShim("http://localhost:11434", "test-model")
        url = shim.start()
        try:
            assert url.startswith("http://127.0.0.1:")
            port_str = url.split(":")[-1]
            port = int(port_str)
            assert 1024 <= port <= 65535
        finally:
            shim.stop()

    def test_stop_shuts_down(self) -> None:
        shim = CompletionsShim("http://localhost:11434", "test-model")
        url = shim.start()
        port = int(url.split(":")[-1])
        shim.stop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex(("127.0.0.1", port))
            assert result != 0
        finally:
            sock.close()

    def test_double_stop_is_safe(self) -> None:
        shim = CompletionsShim("http://localhost:11434", "test-model")
        shim.start()
        shim.stop()
        shim.stop()

    def test_strips_trailing_slash_from_ollama_url(self) -> None:
        shim = CompletionsShim("http://localhost:11434/", "test-model")
        assert shim._ollama_url == "http://localhost:11434"

    def test_stores_model_name(self) -> None:
        shim = CompletionsShim("http://localhost:11434", "granite-3.0-1b")
        assert shim._model == "granite-3.0-1b"
