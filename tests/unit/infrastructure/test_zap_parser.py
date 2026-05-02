"""Unit tests for the ZAP JSON parser."""

from __future__ import annotations

import json

from infrastructure.tools.parsers.zap import (
    _parse_zap_data,
    parse_zap_json_string,
)

_INSTANCE = [{"uri": "https://example.com", "method": "GET"}]


def _one_alert(riskcode: str = "3", instances: list | None = None) -> dict:
    alert: dict = {"name": "XSS", "riskcode": riskcode}
    if instances is not None:
        alert["instances"] = instances
    return alert


def _site(alerts: list) -> dict:
    return {"site": [{"alerts": alerts}]}


class TestZapParser:
    def test_empty_string_returns_empty_alerts(self) -> None:
        result = parse_zap_json_string("")
        assert result["alerts"] == []
        assert result["summary"]["total_alerts"] == 0

    def test_malformed_json_returns_error_key(self) -> None:
        result = parse_zap_json_string("{not valid}")
        assert "error" in result

    def test_non_dict_root_returns_error(self) -> None:
        result = _parse_zap_data([])
        assert "error" in result

    def test_risk_code_3_maps_to_high(self) -> None:
        data = _site([_one_alert("3", _INSTANCE)])
        result = parse_zap_json_string(json.dumps(data))
        assert result["alerts"][0]["risk"] == "high"

    def test_risk_code_2_maps_to_medium(self) -> None:
        data = _site([_one_alert("2", _INSTANCE)])
        result = parse_zap_json_string(json.dumps(data))
        assert result["alerts"][0]["risk"] == "medium"

    def test_informational_riskcode_zero_dropped(self) -> None:
        data = _site([_one_alert("0", _INSTANCE)])
        result = parse_zap_json_string(json.dumps(data))
        assert result["alerts"] == []
        assert result["summary"]["total_alerts"] == 0

    def test_unknown_risk_code_dropped(self) -> None:
        """Unknown risk codes map to informational and are dropped."""
        data = _site([_one_alert("99", _INSTANCE)])
        result = parse_zap_json_string(json.dumps(data))
        assert result["alerts"] == []
        assert result["summary"]["total_alerts"] == 0

    def test_cwe_negative_one_produces_none_cwe_id(self) -> None:
        alert: dict = {"name": "XSS", "riskcode": "3", "cweid": "-1"}
        data = _site([{**alert, "instances": _INSTANCE}])
        result = parse_zap_json_string(json.dumps(data))
        assert result["alerts"][0]["cwe_id"] is None

    def test_alert_without_instances_produces_one_record(self) -> None:
        data = _site([_one_alert("3")])
        result = parse_zap_json_string(json.dumps(data))
        assert len(result["alerts"]) == 1

    def test_alert_with_two_instances_produces_two_records(self) -> None:
        instances = [
            {"uri": "https://example.com/a", "method": "GET"},
            {"uri": "https://example.com/b", "method": "POST"},
        ]
        data = _site([_one_alert("3", instances)])
        result = parse_zap_json_string(json.dumps(data))
        assert len(result["alerts"]) == 2

    def test_summary_total_alerts_matches_expanded_count(self) -> None:
        instances = [
            {"uri": "https://example.com/a", "method": "GET"},
            {"uri": "https://example.com/b", "method": "POST"},
        ]
        data = _site([_one_alert("3", instances), _one_alert("2", instances)])
        result = parse_zap_json_string(json.dumps(data))
        assert result["summary"]["total_alerts"] == 4

    def test_field_mapping_includes_expected_keys(self) -> None:
        data = _site([_one_alert("3", _INSTANCE)])
        result = parse_zap_json_string(json.dumps(data))
        alert = result["alerts"][0]
        expected_keys = (
            "alert_name",
            "risk",
            "confidence",
            "url",
            "method",
            "cwe_id",
            "wasc_id",
        )
        for key in expected_keys:
            assert key in alert
