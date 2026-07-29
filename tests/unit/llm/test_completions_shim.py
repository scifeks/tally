"""Unit tests for completions shim translation."""

from __future__ import annotations

from typing import Any

from infrastructure.llm.completions_shim import (
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
        result = translate_completions_to_generate({"prompt": ""}, "granite3-dense:2b")
        assert result["model"] == "granite3-dense:2b"

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
        result = translate_completions_to_generate(antares_req, "granite3-dense:2b")
        assert result["model"] == "granite3-dense:2b"
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
