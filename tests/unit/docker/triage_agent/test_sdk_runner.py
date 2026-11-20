"""In-process tests for the container-side sdk-runner entrypoint.

Imports sdk-runner.py by file path (it lives in docker/triage-agent/
rather than a Python package) and drives its run_loop() with injected
stdin/stdout and a fake claude_agent_sdk.query.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType

import pytest


def _load_sdk_runner() -> ModuleType:
    runner_path = (
        Path(__file__).resolve().parents[4]
        / "docker"
        / "triage-agent"
        / "sdk-runner.py"
    )
    spec = importlib.util.spec_from_file_location("sdk_runner", runner_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sdk_runner"] = module
    spec.loader.exec_module(module)
    return module


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeAssistantMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeResultMessage:
    def __init__(
        self,
        *,
        is_error: bool,
        result: str = "",
        subtype: str = "success",
        status_code: int | None = None,
    ) -> None:
        self.is_error = is_error
        self.result = result
        self.subtype = subtype
        # The SDK's error attribute name varies between versions.
        self.api_error_status = status_code
        self.status_code = status_code


class _FakeToolUseBlock:
    pass


class _FakeSDK:
    def __init__(self, messages: list[object]) -> None:
        self._messages = messages

    def query(self, *, prompt: str, options: object) -> AsyncIterator[object]:
        async def _go() -> AsyncIterator[object]:
            for message in self._messages:
                yield message

        return _go()


_JOB = {
    "mode": "triage",
    "model": "opus",
    "system_prompt": "sys",
    "user_prompt": "user",
    "allowed_tools": ["Read"],
    "cwd": "/workspace",
    "timeout_seconds": 60,
}


def _run(sdk_runner: ModuleType, jobs: list[dict[str, object]]) -> list[dict]:
    stdin = io.StringIO("".join(json.dumps(job) + "\n" for job in jobs))
    stdout = io.StringIO()
    sdk_runner.run_loop(stdin=stdin, stdout=stdout)
    return [json.loads(line) for line in stdout.getvalue().strip().splitlines()]


@pytest.fixture
def sdk_runner(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = _load_sdk_runner()
    monkeypatch.setattr(module, "_make_options", lambda spec: object())
    # The runner dispatches on isinstance, so swap in the fake message types.
    monkeypatch.setattr(module, "AssistantMessage", _FakeAssistantMessage)
    monkeypatch.setattr(module, "TextBlock", _FakeTextBlock)
    monkeypatch.setattr(module, "ToolUseBlock", _FakeToolUseBlock)
    monkeypatch.setattr(module, "ResultMessage", _FakeResultMessage)
    return module


def test_happy_path_emits_assistant_result_end(
    monkeypatch: pytest.MonkeyPatch, sdk_runner: ModuleType
) -> None:
    fake = _FakeSDK(
        [
            _FakeAssistantMessage("working"),
            _FakeResultMessage(is_error=False, result='{"finding_id":1}'),
        ]
    )
    monkeypatch.setattr(sdk_runner, "query", fake.query)

    lines = _run(sdk_runner, [_JOB])

    assert [x["type"] for x in lines] == ["assistant_text", "result", "end"]


def test_result_error_with_status_code_emits_error_event(
    monkeypatch: pytest.MonkeyPatch, sdk_runner: ModuleType
) -> None:
    fake = _FakeSDK(
        [
            _FakeResultMessage(
                is_error=True,
                result="rate limited",
                subtype="api_error",
                status_code=429,
            ),
        ]
    )
    monkeypatch.setattr(sdk_runner, "query", fake.query)

    lines = _run(sdk_runner, [_JOB])

    error_lines = [x for x in lines if x["type"] == "error"]
    assert len(error_lines) == 1
    assert error_lines[0]["status_code"] == 429


def test_isolated_exception_does_not_kill_loop(
    monkeypatch: pytest.MonkeyPatch, sdk_runner: ModuleType
) -> None:
    """A raised exception on job 1 still emits error + end and reads job 2."""
    calls = {"n": 0}

    def _query(*, prompt: str, options: object) -> AsyncIterator[object]:
        async def _go() -> AsyncIterator[object]:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            yield _FakeResultMessage(is_error=False, result="{}")

        return _go()

    monkeypatch.setattr(sdk_runner, "query", _query)

    lines = _run(sdk_runner, [_JOB, _JOB])

    assert [x["type"] for x in lines] == ["error", "end", "result", "end"]


def test_fake_response_env_bypasses_sdk(
    monkeypatch: pytest.MonkeyPatch, sdk_runner: ModuleType
) -> None:
    fake_text = '{"finding_id":1,"confidence":"confirmed"}'
    monkeypatch.setenv("SDK_RUNNER_FAKE_RESPONSE", fake_text)
    fake = _FakeSDK([_FakeAssistantMessage("must not be emitted")])
    monkeypatch.setattr(sdk_runner, "query", fake.query)

    lines = _run(sdk_runner, [_JOB])

    assert lines == [
        {"type": "result", "text": fake_text, "is_error": False},
        {"type": "end"},
    ]
