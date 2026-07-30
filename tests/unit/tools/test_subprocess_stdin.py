"""Unit tests for SubprocessRunnerPort stdin_data support."""

import json

from infrastructure.tools.runner import SubprocessRunner


class TestSubprocessRunnerStdin:
    def test_stdin_data_passed_to_process(self) -> None:
        runner = SubprocessRunner()
        result = runner.run(
            ["cat"],
            timeout=5,
            stdin_data="hello from stdin",
        )
        assert result.returncode == 0
        assert result.stdout == "hello from stdin"

    def test_stdin_data_none_uses_devnull(self) -> None:
        runner = SubprocessRunner()
        result = runner.run(["echo", "no stdin"], timeout=5)
        assert result.returncode == 0
        assert result.stdout.strip() == "no stdin"

    def test_stdin_data_with_json_payload(self) -> None:
        runner = SubprocessRunner()
        payload = json.dumps({"target": "/tmp", "workers": 4})
        result = runner.run(
            ["cat"],
            timeout=5,
            stdin_data=payload,
        )
        parsed = json.loads(result.stdout)
        assert parsed == {"target": "/tmp", "workers": 4}
