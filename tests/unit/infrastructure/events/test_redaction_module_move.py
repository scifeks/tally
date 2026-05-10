from infrastructure.security.redaction import redact_config as infra_redact
from infrastructure.security.redaction import (
    redact_query_string as infra_redact_qs,
)
from web.api._redact import redact_config as web_redact
from web.api._redact import redact_query_string as web_redact_qs


def test_redact_config_same_function_object():
    assert web_redact is infra_redact


def test_redact_query_string_same_function_object():
    assert web_redact_qs is infra_redact_qs
