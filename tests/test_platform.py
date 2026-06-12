"""Tests for the supply-chain agent platform."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import Settings
from src.eval.mlflow_runner import EvalRunner, _RELEASE_GATES
from src.router.model_router import ModelRouter


@pytest.fixture
def client():
    return TestClient(app)


class TestModelRouter:
    def test_simple_query_routes_to_default(self):
        router = ModelRouter(Settings())
        model, score, tier = router.select_model("Check status of order #44821")
        assert tier == "default"
        assert score < 0.65

    def test_complex_query_routes_to_premium(self):
        router = ModelRouter(Settings())
        model, score, tier = router.select_model(
            "Forecast demand and optimize inventory across all warehouses"
        )
        assert tier == "premium"
        assert score >= 0.65


class TestEvalGates:
    def test_regression_passes_default_thresholds(self):
        runner = EvalRunner(Settings())
        result = runner.run_regression(judge_threshold=0.6, judge_seed=7)
        assert result["scenario_count"] == 12
        assert "llm_judge" in result["metrics"]
        assert "rules_policy" in result["metrics"]


class TestAPI:
    def test_healthz(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("ok", "degraded")

    def test_metrics_endpoint(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "agent_requests_total" in resp.text

    def test_langgraph_agent_run(self, client):
        resp = client.post("/v1/agent/run", json={
            "session_id": "test-session",
            "query": "Check stock for SKU 90155",
            "workflow": "langgraph",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert data["workflow"] == "langgraph"
        assert len(data["tool_calls"]) >= 1

    def test_crew_workflow(self, client):
        resp = client.post("/v1/agent/run", json={
            "session_id": "test-crew",
            "query": "Forecast beverage demand for Southwest",
            "workflow": "crew",
        })
        assert resp.status_code == 200
        assert "Demand Planning Report" in resp.json()["answer"]

    def test_eval_run(self, client):
        resp = client.post("/v1/eval/run", json={
            "judge_threshold": 0.6,
            "judge_seed": 7,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_count"] == 12
        assert "passed_gates" in data

    def test_tool_metadata(self, client):
        resp = client.get("/v1/tools/metadata")
        assert resp.status_code == 200
        assert "inventory_lookup" in resp.json()


class TestGovernanceContract:
    def test_rules_block_exfiltration(self):
        from harness.governance import RulesPolicy
        decision = RulesPolicy().evaluate(
            "read:customers fields=email,phone export_to=external_url"
        )
        assert decision.blocked is True

    def test_rules_allow_single_order(self):
        from harness.governance import RulesPolicy
        decision = RulesPolicy().evaluate(
            "write:refunds amount=order scope=single id=44821"
        )
        assert decision.blocked is False
