"""Unit tests for KatanaLocalTool.build_command and base properties."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.tools.wrappers.local.katana import KatanaLocalTool


class _NullConverter:
    def convert(self, source, output_dir):
        raise AssertionError("not used in this test")


_CONVERTER = _NullConverter()

# Base properties


class TestBaseProperties:
    def test_name(self) -> None:
        assert KatanaLocalTool(endpoint_converter=_CONVERTER).name == "katana"

    def test_scan_segment(self) -> None:
        assert KatanaLocalTool(endpoint_converter=_CONVERTER).scan_segment == "web"

    def test_requires_base_urls(self) -> None:
        assert KatanaLocalTool(endpoint_converter=_CONVERTER).requires_base_urls is True

    def test_is_discovery_tool(self) -> None:
        assert KatanaLocalTool(endpoint_converter=_CONVERTER).is_discovery_tool is True

    def test_findings_exit_ok(self) -> None:
        assert KatanaLocalTool(endpoint_converter=_CONVERTER).findings_exit_ok is False

    def test_always_run(self) -> None:
        assert KatanaLocalTool(endpoint_converter=_CONVERTER).always_run is True

    def test_skip_is_true(self) -> None:
        # Katana is a discovery tool; no triage-able findings.
        assert KatanaLocalTool(endpoint_converter=_CONVERTER).skip is True

    def test_should_visualize_is_false(self) -> None:
        assert KatanaLocalTool(endpoint_converter=_CONVERTER).should_visualize is False

    def test_count_findings_from_summary(self) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        parsed = {
            "endpoints": [{}, {}],
            "summary": {"total_endpoints": 2},
        }
        assert tool.count_findings(parsed) == 2

    def test_count_findings_fallback_to_list_length(self) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        parsed = {"endpoints": [{}, {}, {}]}
        assert tool.count_findings(parsed) == 3

    def test_count_findings_empty(self) -> None:
        assert KatanaLocalTool(endpoint_converter=_CONVERTER).count_findings({}) == 0


# build_command: basic flags


class TestBuildCommandBasic:
    def test_base_url_in_command(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        assert "http://localhost:8080" in cmd

    def test_u_flag_present(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        assert "-u" in cmd

    def test_depth_default_is_5(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        idx = cmd.index("-d")
        assert cmd[idx + 1] == "5"

    def test_jc_flag_present(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        assert "-jc" in cmd

    def test_kf_all_present(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        assert "-kf" in cmd
        idx = cmd.index("-kf")
        assert cmd[idx + 1] == "all"

    def test_xhr_flag_present(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        assert "-xhr" in cmd

    def test_j_flag_present(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        assert "-j" in cmd

    def test_o_flag_points_to_output_file(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        output = str(tmp_path / "out.jsonl")
        cmd = tool.build_command(base_url="http://localhost:8080", output_file=output)
        idx = cmd.index("-o")
        assert cmd[idx + 1] == output

    def test_no_headless_flag_by_default(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        assert "-hl" not in cmd

    def test_sets_last_jsonl_path(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        output = str(tmp_path / "out.jsonl")
        tool.build_command(base_url="http://localhost:8080", output_file=output)
        assert tool._last_jsonl_path == Path(output)

    def test_sets_last_oas3_path_when_provided(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        oas3 = str(tmp_path / "out_oas3.json")
        tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
            oas3_target=oas3,
        )
        assert tool._last_oas3_path == Path(oas3)

    def test_last_oas3_path_none_when_not_provided(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        assert tool._last_oas3_path is None


# build_command: headless flag


class TestBuildCommandHeadless:
    def test_hl_appended_when_headless_true(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
            headless=True,
        )
        assert "-hl" in cmd

    def test_hl_absent_when_headless_false(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
            headless=False,
        )
        assert "-hl" not in cmd


# build_command: depth override


class TestBuildCommandDepth:
    def test_custom_depth_in_command(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
            depth=5,
        )
        idx = cmd.index("-d")
        assert cmd[idx + 1] == "5"

    def test_depth_one(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
            depth=1,
        )
        idx = cmd.index("-d")
        assert cmd[idx + 1] == "1"


# build_command: headers


class TestBuildCommandHeaders:
    def test_no_headers_omits_h_flag(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
        )
        assert "-H" not in cmd

    def test_single_header_adds_h_flag(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
            headers={"Cookie": "session=abc"},
        )
        assert "-H" in cmd

    def test_header_formatted_as_key_colon_value(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
            headers={"Cookie": "session=abc"},
        )
        idx = cmd.index("-H")
        assert cmd[idx + 1] == "Cookie: session=abc"

    def test_multiple_headers_produce_multiple_h_flags(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        cmd = tool.build_command(
            base_url="http://localhost:8080",
            output_file=str(tmp_path / "out.jsonl"),
            headers={"Cookie": "s=1", "X-Token": "tok"},
        )
        assert cmd.count("-H") == 2


# build_command: error cases


class TestBuildCommandErrors:
    def test_missing_base_url_raises(self, tmp_path: Path) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        with pytest.raises(ValueError, match="base_url"):
            tool.build_command(output_file=str(tmp_path / "out.jsonl"))

    def test_missing_output_file_raises(self) -> None:
        tool = KatanaLocalTool(endpoint_converter=_CONVERTER)
        with pytest.raises(ValueError, match="output_file"):
            tool.build_command(base_url="http://localhost:8080")
