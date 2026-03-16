"""Finding-related MCP tool stubs."""


def get_finding(finding_id: int) -> dict:
    """Retrieve a single finding by its primary-key ID.

    Args:
        finding_id: The integer primary key of the finding row.

    Returns:
        A dict representation of the finding row, including all columns
        from the ``findings`` table (id, tool, severity, confidence, etc.).

    Raises:
        NotImplementedError: Phase 1 skeleton — not yet implemented.
    """
    raise NotImplementedError("not implemented")


def get_findings_batch(
    project: str,
    repo: str | None = None,
    tools: list[str] | None = None,
    domain: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """Retrieve a filtered batch of findings for triage.

    Args:
        project: Project name to query findings for.
        repo: Optional repository filter.
        tools: Optional list of tool names to restrict results to.
        domain: Optional domain filter (e.g. ``"sast"``, ``"secrets"``).
        status: Optional status filter (e.g. ``"open"``, ``"fixed"``).

    Returns:
        A list of finding dicts, each matching the ``findings`` table schema.
        Batch size is capped by ``MAX_BATCH_SIZE`` from ``mcp.config``.

    Raises:
        NotImplementedError: Phase 1 skeleton — not yet implemented.
    """
    raise NotImplementedError("not implemented")


def update_finding(
    finding_id: int,
    confidence: str | None = None,
    finding_type: str | None = None,
    severity: str | None = None,
    reasoning: str | None = None,
    remediation: str | None = None,
    attack_vector: str | None = None,
    call_stack: str | None = None,
) -> bool:
    """Update enrichment fields on a single finding.

    Args:
        finding_id: Primary key of the finding to update.
        confidence: New confidence level (e.g. ``"confirmed"``,
            ``"false_positive"``).
        finding_type: Updated finding type classification.
        severity: Updated severity level.
        reasoning: Free-text reasoning for the triage decision.
        remediation: Suggested remediation steps.
        attack_vector: Identified attack vector, if applicable.
        call_stack: Relevant call stack or code path context.

    Returns:
        ``True`` if the row was updated, ``False`` if the finding was not found.

    Raises:
        NotImplementedError: Phase 1 skeleton — not yet implemented.
    """
    raise NotImplementedError("not implemented")


def update_findings_batch(updates: list[dict]) -> dict:
    """Apply updates to multiple findings in a single call.

    Args:
        updates: A list of update dicts. Each dict must contain
            ``finding_id`` plus any subset of the fields accepted by
            :func:`update_finding`.

    Returns:
        A summary dict with keys ``updated`` (int), ``not_found`` (int),
        and ``errors`` (list of dicts describing any failures).

    Raises:
        NotImplementedError: Phase 1 skeleton — not yet implemented.
    """
    raise NotImplementedError("not implemented")
