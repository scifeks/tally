"""Unit tests for QueryEngine.chat() context label building.

Verifies that profile is included in the LLM prompt context labels
when metadata contains a profile value.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestQueryChatContextLabel:
    """chat() builds context lines that include profile when present."""

    def _make_query_engine(self) -> object:
        """Return a QueryEngine with mocked RAGEngine and LLMProvider."""
        from application.rag.query import QueryEngine

        rag_engine = MagicMock()
        rag_engine.base_path = "/tmp/fake"
        rag_engine.count_documents.return_value = 1

        llm_provider = MagicMock()
        llm_provider.is_available.return_value = True
        llm_provider.complete.return_value = "mocked response"

        with patch("application.rag.query.ConfigManager") as mock_cfg:
            mock_cfg.return_value.load_commands_config.return_value = {
                "composer-audit": {}
            }
            engine = QueryEngine(
                rag_engine=rag_engine,
                llm_provider=llm_provider,
            )

        engine._engine = rag_engine
        engine._provider = llm_provider
        return engine

    def test_chat_prompt_contains_profile_when_present(self) -> None:
        """Prompt sent to LLM contains the profile value from metadata."""
        engine = self._make_query_engine()

        search_result = [
            {
                "document": "Package: lodash@1.0.0",
                "metadata": {
                    "tool": "composer-audit",
                    "profile": "php-goof",
                },
                "distance": 0.1,
            }
        ]

        captured_prompts: list[str] = []

        def capture_complete(prompt: str, **kwargs: object) -> str:
            captured_prompts.append(prompt)
            return "mocked response"

        engine._provider.complete.side_effect = capture_complete  # type: ignore[attr-defined]

        with patch.object(engine, "search", return_value=search_result):  # type: ignore[arg-type]
            engine.chat("what did composer-audit find?")  # type: ignore[attr-defined]

        assert captured_prompts, "LLM complete() was not called"
        prompt = captured_prompts[0]
        assert "php-goof" in prompt, f"Expected 'php-goof' in prompt; got:\n{prompt}"

    def test_chat_context_label_format_includes_repo(self) -> None:
        """Context label is formatted as [tool repo=profile]."""
        engine = self._make_query_engine()

        search_result = [
            {
                "document": "Package: lodash@1.0.0",
                "metadata": {
                    "tool": "composer-audit",
                    "profile": "php-goof",
                },
                "distance": 0.1,
            }
        ]

        captured_prompts: list[str] = []

        def capture_complete(prompt: str, **kwargs: object) -> str:
            captured_prompts.append(prompt)
            return "mocked response"

        engine._provider.complete.side_effect = capture_complete  # type: ignore[attr-defined]

        with patch.object(engine, "search", return_value=search_result):  # type: ignore[arg-type]
            engine.chat("what did composer-audit find?")  # type: ignore[attr-defined]

        assert captured_prompts, "LLM complete() was not called"
        prompt = captured_prompts[0]
        assert "[composer-audit repo=php-goof]" in prompt, (
            f"Expected label '[composer-audit repo=php-goof]' in prompt; got:\n{prompt}"
        )

    def test_chat_context_label_omits_repo_when_profile_empty(self) -> None:
        """When profile is absent, label is just [tool] with no repo= part."""
        engine = self._make_query_engine()

        search_result = [
            {
                "document": "Package: lodash@1.0.0",
                "metadata": {
                    "tool": "composer-audit",
                    "profile": "",
                },
                "distance": 0.1,
            }
        ]

        captured_prompts: list[str] = []

        def capture_complete(prompt: str, **kwargs: object) -> str:
            captured_prompts.append(prompt)
            return "mocked response"

        engine._provider.complete.side_effect = capture_complete  # type: ignore[attr-defined]

        with patch.object(engine, "search", return_value=search_result):  # type: ignore[arg-type]
            engine.chat("what did composer-audit find?")  # type: ignore[attr-defined]

        assert captured_prompts, "LLM complete() was not called"
        prompt = captured_prompts[0]
        assert "repo=" not in prompt, (
            f"Expected no 'repo=' in prompt when profile is empty; got:\n{prompt}"
        )
        assert "[composer-audit]" in prompt, (
            f"Expected label '[composer-audit]' in prompt; got:\n{prompt}"
        )
