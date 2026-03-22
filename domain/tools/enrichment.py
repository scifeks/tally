"""Domain models for per-field LLM enrichment specifications."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PromptStrategy(Enum):
    """Prompt strategy for a single enrichment field."""

    GENERIC = "generic"
    """Shared multi-field template with free-form reasoning. Appropriate for
    fields like risk_type, remediation, confidence where open-ended classification
    over finding context is correct."""

    DEDICATED = "dedicated"
    """Field-specific prompt template with structured constraints. Appropriate for
    constrained fields like owasp_name that require an exact enum value."""


@dataclass(frozen=True)
class FieldEnrichmentSpec:
    """Declaration of how a single enrichment field should be inferred.

    Chunk builders that opt into per-field enrichment declare a tuple of these
    on a class attribute named ``enrichment_fields``. The enrichment pipeline
    reads this attribute via ``getattr`` and, when present, makes one focused
    LLM call per spec rather than a single batch call over the full chunk text.

    Attributes:
        field_name: The enrichment field key (must be in ENRICHMENT_FIELDS).
        source_fields: Ordered tuple of metadata keys to extract from the
            finding and send as context. Keys absent from the finding are
            silently omitted. Listed in priority order — most diagnostic first.
        strategy: Whether to use the shared generic template or a dedicated
            field-specific prompt module. Defaults to GENERIC.
    """

    field_name: str
    source_fields: tuple[str, ...]
    strategy: PromptStrategy = PromptStrategy.GENERIC
