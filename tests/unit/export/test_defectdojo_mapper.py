"""Unit tests for DefectDojo Generic Findings mapper."""

from __future__ import annotations

from domain.findings.entry import Finding
from infrastructure.export.defectdojo.mapper import (
    is_static_asset_path,
    map_finding,
    map_findings,
)


class TestDefectDojoMapper:
    def test_default_mapping_unknown_tool(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="unknown_tool",
            domain="code",
            segment="sast",
            finding_type=["vulnerability"],
            severity="high",
            confidence="confirmed",
            file="src/app.py",
            rule_id="xss-rule",
            url=None,
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            description="XSS vulnerability",
            package_version=None,
            cwe=[],
            enriched=True,
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)

        assert result["title"] == "unknown_tool: xss-rule in src/app.py"
        assert result["severity"] == "High"
        assert result["description"] == "XSS vulnerability"
        assert result["active"] is True
        assert "verified" in result

    def test_severity_mapping(self) -> None:
        severities = {
            "critical": "Critical",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
            "informational": "Info",
        }

        for input_sev, expected_sev in severities.items():
            finding = Finding(
                id=1,
                fingerprint="fp1",
                run_id=1,
                tool="test",
                domain="code",
                segment="sast",
                severity=input_sev,
                confidence=None,
                description="Test",
                file="test.py",
                rule_id="rule1",
                cwe=[],
                meta={},
                first_seen="2024-01-15T10:00:00",
                last_seen="2024-01-15T10:00:00",
                seen_count=1,
                status="active",
            )
            result = map_finding(finding)
            assert result["severity"] == expected_sev

    def test_severity_none_defaults_to_info(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity=None,
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["severity"] == "Info"

    def test_cwe_parsing(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=["CWE-79", "CWE-89"],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["cwe"] == 79

    def test_cwe_empty_list(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert "cwe" not in result

    def test_title_from_meta(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="semgrep",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={"title": "XSS in login form"},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["title"] == "XSS in login form"

    def test_title_synthesized(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="semgrep",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test description",
            file="src/app.py",
            rule_id="xss-check",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["title"] == "semgrep: xss-check in src/app.py"

    def test_semgrep_adds_line_and_sast_path(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="semgrep",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="src/app.py",
            rule_id="rule1",
            cwe=[],
            meta={"line_start": 42},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["line"] == 42
        assert result["sast_source_file_path"] == "src/app.py"

    def test_semgrep_maps_dataflow_fields(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="semgrep",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Taint finding",
            file="app/views.py",
            rule_id="xss-taint",
            cwe=["CWE-79"],
            meta={
                "line_start": 42,
                "sast_source_line": 30,
                "sast_source_file_path": "app/views.py",
                "sast_source_object": "request.args.get('q')",
                "sast_sink_object": ("render_template_string(user_input)"),
            },
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)

        assert result["sast_source_line"] == 30
        assert result["sast_source_object"] == ("request.args.get('q')")
        assert result["sast_sink_object"] == ("render_template_string(user_input)")
        assert result["sast_source_file_path"] == "app/views.py"

    def test_semgrep_omits_absent_dataflow_fields(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="semgrep",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Pattern-only finding",
            file="app/config.py",
            rule_id="hardcoded-secret",
            cwe=[],
            meta={"line_start": 10},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)

        assert "sast_source_line" not in result
        assert "sast_source_object" not in result
        assert "sast_sink_object" not in result
        assert result["sast_source_file_path"] == "app/config.py"

    def test_gitleaks_adds_line(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="gitleaks",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="aws-key",
            cwe=[],
            meta={"end_line": 100},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["line"] == 100

    def test_zap_adds_endpoints(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="zap",
            domain="web",
            segment="dast",
            severity="high",
            confidence=None,
            description="Test",
            file=None,
            rule_id="rule1",
            url="https://example.com/api",
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["endpoints"] == ["https://example.com/api"]

    def test_dalfox_adds_param_payload(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="dalfox",
            domain="web",
            segment="dast",
            severity="high",
            confidence=None,
            description="Test",
            file=None,
            rule_id="rule1",
            url="https://example.com/page",
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={"param": "id", "payload": "<img src=x>"},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["param"] == "id"
        assert result["payload"] == "<img src=x>"
        assert result["endpoints"] == ["https://example.com/page"]

    def test_xsstrike_adds_param_payload(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="xsstrike",
            domain="web",
            segment="dast",
            severity="high",
            confidence=None,
            description="Test",
            file=None,
            rule_id="rule1",
            url="https://example.com/search",
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={"param": "q", "payload": "alert(1)"},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["param"] == "q"
        assert result["payload"] == "alert(1)"

    def test_sca_adds_component_info(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="osv",
            domain="code",
            segment="sca",
            severity="high",
            confidence=None,
            description="Vulnerability in package",
            file=None,
            rule_id=None,
            url=None,
            vulnerability_id="CVE-2024-1234",
            package_name="requests",
            ecosystem="pypi",
            package_version="2.28.0",
            cwe=[],
            meta={"fixed_version": "2.32.0", "cvss_score": 7.5},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["component_name"] == "requests"
        assert result["component_version"] == "2.28.0"
        assert result["fix_version"] == "2.32.0"
        assert result["cvssv3_score"] == 7.5
        assert result["cve"] == "CVE-2024-1234"

    def test_garak_adds_service_and_description(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="garak",
            domain="web",
            segment="testing",
            severity="high",
            confidence=None,
            description="LLM produced harmful output",
            file=None,
            rule_id=None,
            url=None,
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={
                "probe_description": "Profanity detection probe",
                "goal": "Detect harmful content",
                "probe": "probe1",
                "detector": "detector1",
            },
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["service"] == "llm"
        assert result["dynamic_finding"] is True
        assert "Profanity detection probe" in result["description"]
        assert "Goal:" in result["description"]

    def test_confidence_to_verified(self) -> None:
        finding_confirmed = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity="high",
            confidence="confirmed",
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding_confirmed)
        assert result["verified"] is True

        finding_probable = Finding(
            id=2,
            fingerprint="fp2",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity="high",
            confidence="probable",
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding_probable)
        assert result["verified"] is False

    def test_status_to_active_false_p(self) -> None:
        finding_active = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding_active)
        assert result["active"] is True
        assert result["false_p"] is False

        finding_fp = Finding(
            id=2,
            fingerprint="fp2",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="false_positive",
        )
        result = map_finding(finding_fp)
        assert result["active"] is False
        assert result["false_p"] is True

    def test_tags_assembly(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="semgrep",
            domain="code",
            segment="sast",
            finding_type=["vulnerability", "injection"],
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={"tags": ["custom-tag"]},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        tags = result["tags"]
        assert "vulnerability" in tags
        assert "injection" in tags
        assert "domain:code" in tags
        assert "segment:sast" in tags
        assert "tool:semgrep" in tags
        assert "custom-tag" in tags

    def test_map_findings_skips_failures(self) -> None:
        good_finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity="high",
            confidence=None,
            description="Test",
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        bad_finding = Finding(
            id=2,
            fingerprint="fp2",
            run_id=1,
            tool="test",
            domain="code",
            segment="sast",
            severity=None,
            confidence=None,
            description=None,
            file="test.py",
            rule_id="rule1",
            cwe=[],
            meta={"cwe": "not-a-list"},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )

        findings = [good_finding, bad_finding]
        results = map_findings(findings)

        assert len(results) >= 1
        assert results[0]["title"]
        assert results[0]["severity"]

    def test_dalfox_strips_payload_from_endpoint(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="dalfox",
            domain="web",
            segment="dast",
            severity="high",
            confidence=None,
            description="Test",
            file=None,
            rule_id="rule1",
            url=(
                "http://127.0.0.1:8081/search.php"
                "?q=test%3E%3Cbase+href%3Djavascript"
                "%3Aalert%281%29%2F%2F"
            ),
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={"param": "q", "payload": "<base href=javascript:alert(1)//>"},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["endpoints"] == ["http://127.0.0.1:8081/search.php"]

    def test_dalfox_strips_fragment_from_endpoint(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="dalfox",
            domain="web",
            segment="dast",
            severity="high",
            confidence=None,
            description="Test",
            file=None,
            rule_id="rule1",
            url=(
                "http://127.0.0.1:8081/account/profile.php"
                "#jaVasCript:/*-/*`/*\\`/*'/*\"/**/"
            ),
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["endpoints"] == ["http://127.0.0.1:8081/account/profile.php"]

    def test_zap_strips_query_from_endpoint(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="zap",
            domain="web",
            segment="dast",
            severity="medium",
            confidence=None,
            description="Test",
            file=None,
            rule_id="rule1",
            url="https://example.com/api/users?id=1&action=delete",
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={"param": "id"},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert result["endpoints"] == ["https://example.com/api/users"]

    def test_xss_mapper_skips_static_asset_endpoint(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="xsstrike",
            domain="web",
            segment="dast",
            severity="high",
            confidence=None,
            description="Test",
            file=None,
            rule_id="rule1",
            url=("https://cdnjs.cloudflare.com/ajax/libs/jquery/1.12.4/jquery.min.js"),
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert "endpoints" not in result

    def test_dalfox_description_includes_payload_and_param(
        self,
    ) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="dalfox",
            domain="web",
            segment="dast",
            severity="high",
            confidence="confirmed",
            description=None,
            file=None,
            rule_id=None,
            url=(
                "http://127.0.0.1:8081/search.php?q=%3Cscript%3Ealert(1)%3C/script%3E"
            ),
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=["CWE-79"],
            meta={
                "title": "Cross-Site Scripting (XSS) in 'q'",
                "param": "q",
                "payload": "<script>alert(1)</script>",
                "method": "GET",
                "inject_type": "inHTML-URL",
                "evidence": "<script>alert(1)</script>",
            },
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        desc = result["description"]
        assert "<script>alert(1)</script>" in desc
        assert "q" in desc
        assert "GET" in desc
        assert "inHTML-URL" in desc
        assert "http://127.0.0.1:8081/search.php" in desc

    def test_dalfox_preserves_explicit_description(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="dalfox",
            domain="web",
            segment="dast",
            severity="high",
            confidence=None,
            description="Enriched XSS description from LLM",
            file=None,
            rule_id=None,
            url="http://example.com/page.php",
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={
                "param": "q",
                "payload": "<img src=x>",
            },
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        desc = result["description"]
        assert "Enriched XSS description from LLM" in desc
        assert "<img src=x>" in desc

    def test_dalfox_description_handles_missing_meta(self) -> None:
        finding = Finding(
            id=1,
            fingerprint="fp1",
            run_id=1,
            tool="dalfox",
            domain="web",
            segment="dast",
            severity="high",
            confidence=None,
            description=None,
            file=None,
            rule_id=None,
            url="http://example.com/page.php",
            vulnerability_id=None,
            package_name=None,
            ecosystem=None,
            package_version=None,
            cwe=[],
            meta={},
            first_seen="2024-01-15T10:00:00",
            last_seen="2024-01-15T10:00:00",
            seen_count=1,
            status="active",
        )
        result = map_finding(finding)
        assert "description" in result


class TestStaticAssetFilter:
    def test_js_is_static(self) -> None:
        assert is_static_asset_path("/jquery.min.js") is True

    def test_css_is_static(self) -> None:
        assert is_static_asset_path("/styles/main.css") is True

    def test_svg_is_static(self) -> None:
        assert is_static_asset_path("/images/logo.svg") is True

    def test_png_is_static(self) -> None:
        assert is_static_asset_path("/img/banner.png") is True

    def test_php_is_not_static(self) -> None:
        assert is_static_asset_path("/search.php") is False

    def test_no_extension_is_not_static(self) -> None:
        assert is_static_asset_path("/api/users") is False

    def test_html_is_not_static(self) -> None:
        assert is_static_asset_path("/index.html") is False

    def test_empty_path_is_not_static(self) -> None:
        assert is_static_asset_path("") is False

    def test_case_insensitive(self) -> None:
        assert is_static_asset_path("/bundle.JS") is True
