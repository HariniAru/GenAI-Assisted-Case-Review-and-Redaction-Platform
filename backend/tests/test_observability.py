from unittest.mock import sentinel

from langsmith import get_tracing_context

from app import observability
from app.analysis_router import analysis_graph
from app.config import Settings


def test_local_dotenv_settings_enable_tracing_without_exporting_key(tmp_path, monkeypatch):
    for key in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "LANGSMITH_TRACING=true\nLANGSMITH_API_KEY=synthetic-test-key\n"
        "LANGSMITH_PROJECT=synthetic-test-project\n"
    )
    settings = Settings(_env_file=env)
    monkeypatch.setattr(observability, "get_settings", lambda: settings)
    monkeypatch.setattr(observability, "tracing_client", lambda: sentinel.client)
    with observability.analysis_tracing():
        context = get_tracing_context()
        assert context["enabled"] is True
        assert context["project_name"] == "synthetic-test-project"
        assert context["client"] is sentinel.client
    assert "synthetic-test-key" not in repr(settings)


def test_disabled_tracing_does_not_construct_client(monkeypatch):
    monkeypatch.setattr(
        observability, "get_settings", lambda: Settings(_env_file=None, langsmith_tracing=False)
    )

    def forbidden():
        raise AssertionError("Disabled tracing must not create a client")

    monkeypatch.setattr(observability, "tracing_client", forbidden)
    with observability.analysis_tracing():
        assert get_tracing_context()["enabled"] is False


def test_studio_exposes_only_case_id_input_and_expected_graph():
    graph = analysis_graph()
    assert set(graph.get_input_jsonschema()["properties"]) == {"case_id"}
    assert graph.get_input_jsonschema()["required"] == ["case_id"]
    assert set(graph.get_graph().nodes) == {
        "__start__",
        "__end__",
        "load_case",
        "retrieve_rules",
        "recommend",
        "validate",
        "load_summary_guidance",
        "draft_summary",
        "return_drafts",
    }
    assert graph.checkpointer is None


def test_studio_rejects_sqlite_and_config_loads_postgres():
    import json
    import runpy
    from pathlib import Path

    import pytest

    assert json.loads(Path("langgraph.json").read_text())["env"] == ".env.postgres"
    with pytest.raises(RuntimeError, match="Studio requires the PostgreSQL"):
        runpy.run_module("app.studio")
