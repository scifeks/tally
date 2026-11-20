from pathlib import Path
from unittest.mock import MagicMock

from application.triage.factory import TriageAgentFactory
from infrastructure.anthropic.claude_sdk_triage_agent import AgentSDKTriageAgent


def test_factory_returns_sdk_agent_for_claude_sdk_provider() -> None:
    factory = TriageAgentFactory(app_root=Path("/tmp"))
    resolved = MagicMock()
    resolved.provider_name = "claude_sdk"
    resolved.billing_method = "plan"
    resolved.api_key_source = None
    resolved.model = "claude-opus-4-6[1m]"
    agent = factory.create(resolved)
    assert isinstance(agent, AgentSDKTriageAgent)


def test_factory_still_returns_claude_agent_for_claude_provider() -> None:
    from infrastructure.agents.claude_triage_agent import ClaudeTriageAgent

    factory = TriageAgentFactory(app_root=Path("/tmp"))
    resolved = MagicMock()
    resolved.provider_name = "claude"
    resolved.model = "claude-opus-4-6[1m]"
    agent = factory.create(resolved)
    assert isinstance(agent, ClaudeTriageAgent)
