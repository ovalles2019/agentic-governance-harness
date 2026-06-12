"""Pydantic request/response contracts for the agent API."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    session_id: str = Field(..., examples=["sess-abc123"])
    query: str = Field(..., min_length=1, examples=["Check stock for SKU 90155 in warehouse DFW-01"])
    workflow: Literal["langgraph", "crew", "governance_eval"] = "langgraph"
    user_role: str = "supply_chain_analyst"


class ToolCallRecord(BaseModel):
    tool: str
    input: dict[str, Any]
    output: dict[str, Any] | str
    latency_ms: float
    success: bool


class GovernanceResult(BaseModel):
    blocked: bool
    reason: str
    approach: str
    risk_score: float | None = None


class AgentResponse(BaseModel):
    session_id: str
    answer: str
    workflow: str
    model_used: str
    tool_calls: list[ToolCallRecord] = []
    governance: GovernanceResult | None = None
    rag_sources: list[str] = []
    latency_ms: float
    cost_usd: float
    trace_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvalRunRequest(BaseModel):
    judge_threshold: float = 0.6
    judge_seed: int = 7
    log_to_mlflow: bool = False
    experiment_name: str = "governance-regression"


class EvalRunResponse(BaseModel):
    scenario_count: int
    metrics: dict[str, dict[str, float | None]]
    mlflow_run_id: str | None = None
    passed_gates: bool
    gate_failures: list[str] = []


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    services: dict[str, str]
