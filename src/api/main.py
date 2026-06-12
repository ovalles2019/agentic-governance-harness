"""FastAPI gateway — production-grade agent API with observability."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from src.agents.crew_demand import DemandPlanningCrew
from src.agents.langgraph_workflow import LangGraphAgent
from src.api.schemas import AgentRequest, AgentResponse, EvalRunRequest, EvalRunResponse, HealthResponse, ToolCallRecord, GovernanceResult
from src.config import get_settings
from src.eval.mlflow_runner import EvalRunner
from src.events.kafka_producer import EventPublisher
from src.memory.redis_memory import AgentMemory
from src.observability.telemetry import (
    AGENT_LATENCY,
    AGENT_REQUESTS,
    GOVERNANCE_BLOCKS,
    Timer,
    metrics_payload,
    setup_telemetry,
    span,
)
from src.rag.knowledge_base import KnowledgeBase

settings = get_settings()
events = EventPublisher(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry(settings.app_name, settings.otel_exporter_endpoint)
    await events.connect()
    yield
    await events.close()


app = FastAPI(
    title=settings.app_name,
    description="Production-grade agentic AI platform for supply-chain workflows",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

langgraph_agent = LangGraphAgent(settings)
crew_agent = DemandPlanningCrew(settings)
eval_runner = EvalRunner(settings)
memory = AgentMemory(settings)
kb = KnowledgeBase(settings)


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    services = {
        "redis": memory.health(),
        "chroma": kb.health(),
        "kafka": events.health(),
    }
    status = "ok" if all(v != "error" for v in services.values()) else "degraded"
    return HealthResponse(status=status, services=services)


@app.get("/metrics")
async def metrics() -> Response:
    body, content_type = metrics_payload()
    return Response(content=body, media_type=content_type)


@app.post("/v1/agent/run", response_model=AgentResponse)
async def run_agent(req: AgentRequest) -> AgentResponse:
    trace_id = str(uuid.uuid4())
    timer = Timer()

    with span("api.agent.run", {"workflow": req.workflow, "trace_id": trace_id}):
        try:
            if req.workflow == "langgraph":
                result = langgraph_agent.run(req.session_id, req.query)
            elif req.workflow == "crew":
                result = crew_agent.run(req.session_id, req.query)
            else:
                raise HTTPException(400, f"Unknown workflow: {req.workflow}")
        except Exception as exc:
            AGENT_REQUESTS.labels(workflow=req.workflow, model="n/a", status="error").inc()
            raise HTTPException(500, str(exc)) from exc

    latency = timer.stop()
    AGENT_LATENCY.labels(workflow=req.workflow).observe(latency / 1000)
    AGENT_REQUESTS.labels(
        workflow=req.workflow,
        model=result.get("model", "unknown"),
        status="ok",
    ).inc()

    gov = result.get("governance", {})
    if gov.get("blocked"):
        GOVERNANCE_BLOCKS.labels(approach=gov.get("approach", "unknown")).inc()

    await events.publish("agent.completed", {
        "trace_id": trace_id,
        "session_id": req.session_id,
        "workflow": req.workflow,
        "latency_ms": latency,
    })

    tool_calls = [
        ToolCallRecord(**tc) for tc in result.get("tool_calls", [])
    ]
    governance = GovernanceResult(**gov) if gov else None

    return AgentResponse(
        session_id=req.session_id,
        answer=result["answer"],
        workflow=req.workflow,
        model_used=result.get("model", settings.default_model),
        tool_calls=tool_calls,
        governance=governance,
        rag_sources=result.get("rag_sources", []),
        latency_ms=round(latency, 2),
        cost_usd=result.get("cost_usd", 0.0),
        trace_id=trace_id,
    )


@app.post("/v1/eval/run", response_model=EvalRunResponse)
async def run_eval(req: EvalRunRequest) -> EvalRunResponse:
    result = eval_runner.run_regression(
        judge_threshold=req.judge_threshold,
        judge_seed=req.judge_seed,
        log_to_mlflow=req.log_to_mlflow,
        experiment_name=req.experiment_name,
    )
    return EvalRunResponse(**result)


@app.get("/v1/tools/metadata")
async def tool_metadata() -> dict:
    from src.tools.connectors import SupplyChainTools
    return SupplyChainTools.TOOL_METADATA
