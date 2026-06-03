from pathlib import Path
from types import SimpleNamespace

import yaml
from langchain.agents.middleware import AgentMiddleware

from deerflow.agents.middlewares.agent_middlewares_loader import load_agent_middlewares
from deerflow.config.agent_middlewares_config import (
    AgentMiddlewareEntry,
    AgentMiddlewaresConfig,
)


class FakeConfiguredMiddleware(AgentMiddleware):
    def __init__(
        self,
        *,
        config: dict | None = None,
        agent_name: str | None = None,
        middleware_name: str | None = None,
        app_config=None,
    ) -> None:
        super().__init__()
        self.config = config or {}
        self.agent_name = agent_name
        self.middleware_name = middleware_name
        self.app_config = app_config


def _app_config(agent_middlewares: AgentMiddlewaresConfig):
    return SimpleNamespace(agent_middlewares=agent_middlewares)


def test_agent_middlewares_disabled_preserves_existing_behavior():
    app_config = _app_config(
        AgentMiddlewaresConfig(
            enabled=False,
            agents={
                "nl2sql-deepresearch": [
                    AgentMiddlewareEntry(
                        name="gate",
                        enabled=True,
                        use="tests:FakeConfiguredMiddleware",
                        config={"mode": "warn"},
                    )
                ]
            },
        )
    )

    assert load_agent_middlewares("nl2sql-deepresearch", app_config=app_config) == []


def test_agent_middlewares_load_only_matching_agent(monkeypatch):
    monkeypatch.setattr(
        "deerflow.agents.middlewares.agent_middlewares_loader.resolve_variable",
        lambda use, expected_type=None: FakeConfiguredMiddleware,
    )
    app_config = _app_config(
        AgentMiddlewaresConfig(
            enabled=True,
            agents={
                "nl2sql-deepresearch": [
                    AgentMiddlewareEntry(
                        name="nl2sql_evidence_gate",
                        enabled=True,
                        use="beijing_deepresearch.deerflow_ext.nl2sql_evidence_gate:Nl2sqlEvidenceGateMiddleware",
                        config={"mode": "warn", "max_retries": 1},
                    )
                ],
                "other-agent": [
                    AgentMiddlewareEntry(
                        name="other",
                        enabled=True,
                        use="tests:FakeConfiguredMiddleware",
                    )
                ],
            },
        )
    )

    loaded = load_agent_middlewares("nl2sql-deepresearch", app_config=app_config)
    skipped = load_agent_middlewares("default", app_config=app_config)

    assert len(loaded) == 1
    assert isinstance(loaded[0], FakeConfiguredMiddleware)
    assert loaded[0].agent_name == "nl2sql-deepresearch"
    assert loaded[0].middleware_name == "nl2sql_evidence_gate"
    assert loaded[0].config == {"mode": "warn", "max_retries": 1}
    assert skipped == []


def test_agent_middlewares_invalid_use_logs_and_continues(monkeypatch, caplog):
    def fail_resolve(use, expected_type=None):
        raise ImportError(f"cannot import {use}")

    monkeypatch.setattr(
        "deerflow.agents.middlewares.agent_middlewares_loader.resolve_variable",
        fail_resolve,
    )
    app_config = _app_config(
        AgentMiddlewaresConfig(
            enabled=True,
            agents={
                "nl2sql-deepresearch": [
                    AgentMiddlewareEntry(
                        name="broken",
                        enabled=True,
                        use="missing.module:Broken",
                    )
                ]
            },
        )
    )

    with caplog.at_level("ERROR"):
        loaded = load_agent_middlewares("nl2sql-deepresearch", app_config=app_config)

    assert loaded == []
    assert "Failed to load agent middleware broken" in caplog.text


def test_agent_middlewares_reject_non_middleware(monkeypatch):
    monkeypatch.setattr(
        "deerflow.agents.middlewares.agent_middlewares_loader.resolve_variable",
        lambda use, expected_type=None: object,
    )
    app_config = _app_config(
        AgentMiddlewaresConfig(
            enabled=True,
            agents={
                "nl2sql-deepresearch": [
                    AgentMiddlewareEntry(
                        name="not_middleware",
                        enabled=True,
                        use="tests:NotMiddleware",
                    )
                ]
            },
        )
    )

    assert load_agent_middlewares("nl2sql-deepresearch", app_config=app_config) == []


def test_nl2sql_evidence_gate_mode_off_is_quoted_in_config_yaml():
    config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    gate_config = config_data["agent_middlewares"]["agents"]["nl2sql-deepresearch"][0]["config"]

    assert gate_config["mode"] == "off"
