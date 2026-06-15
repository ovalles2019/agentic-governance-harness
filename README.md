# Supply Chain Agent Platform

**Production-grade agentic AI platform** built to demonstrate the full tech stack from enterprise AI Engineer roles — multi-agent orchestration, MCP tooling, RAG, evaluation discipline, observability, and cloud-native deployment.

> **Resume pitch:** End-to-end supply-chain agent platform with LangGraph + CrewAI orchestration, MCP enterprise connectors, agentic RAG, Redis session memory, model routing, governance evaluation with release gates, and full MLOps/observability stack (MLflow, Prometheus, OpenTelemetry, Grafana, Kafka, gRPC, Docker, Kubernetes).

**Live governance demo:** https://agentic-governance-demo.onrender.com

**Portfolio:** [oscar-valles.com](https://www.oscar-valles.com/) · See also [Nexus SRE Agent](https://cloud-sre-agent.onrender.com/) (Bedrock + CloudWatch + FinOps)

---

## Job Description → Code Mapping

Use this table in interviews to point recruiters to specific implementations.

| Job Requirement | Where It Lives |
|---|---|
| **Python + FastAPI + asyncio + Pydantic** | `src/api/main.py`, `src/api/schemas.py`, `src/config.py` |
| **LangGraph multi-agent orchestration** | `src/agents/langgraph_workflow.py` — RAG → plan → tools → govern → respond |
| **CrewAI multi-agent crews** | `src/agents/crew_demand.py` — analyst / validator / reporter |
| **Advanced prompt engineering + model routing** | `src/router/model_router.py` — complexity scoring, cheap vs premium routing |
| **Custom agent memory (MEM0-style)** | `src/memory/redis_memory.py` — session TTL memory with Redis fallback |
| **Agentic RAG + vector DB** | `src/rag/knowledge_base.py` — Chroma vector store + keyword fallback |
| **MCP connectors for enterprise apps** | `src/mcp/server.py` — inventory, orders, shipments with typed scopes |
| **Evaluation: golden sets, regression, release gates** | `harness/`, `src/eval/mlflow_runner.py`, `scenarios/tasks.py` |
| **MLflow instrumentation** | `src/eval/mlflow_runner.py` — experiment tracking, metric logging |
| **Unit + integration + agent simulation tests** | `tests/test_platform.py` |
| **gRPC enterprise connectors** | `proto/inventory.proto`, `src/tools/inventory_grpc_server.py` |
| **Kafka event streaming** | `src/events/kafka_producer.py` |
| **Redis caching / memory** | `src/memory/redis_memory.py` |
| **Prometheus + OpenTelemetry + Grafana** | `src/observability/telemetry.py`, `infra/` |
| **Docker + Kubernetes** | `Dockerfile`, `docker-compose.yml`, `k8s/deployment.yaml` |
| **Ray distributed eval** | `src/eval/mlflow_runner.py` → `run_ray_distributed_eval()` |
| **Governance / guardrails / policies** | `harness/governance.py` — rules + LLM-as-judge with threshold sweep |
| **Supply-chain domain scenarios** | `scenarios/tasks.py` — inventory, orders, PII, refunds |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Gateway (:8080)                      │
│  /v1/agent/run  ·  /v1/eval/run  ·  /metrics  ·  /healthz       │
└────────┬──────────────────┬──────────────────┬────────────────────┘
         │                  │                  │
    ┌────▼────┐       ┌─────▼─────┐     ┌─────▼─────┐
    │LangGraph│       │  CrewAI   │     │ Eval Harness│
    │ Workflow│       │   Crew    │     │ + MLflow    │
    └────┬────┘       └─────┬─────┘     └───────────┘
         │                  │
    ┌────▼──────────────────▼──────────────────────────────────┐
    │  Model Router · RAG (Chroma) · Memory (Redis) · Governance │
    └────┬──────────────────┬──────────────────┬───────────────┘
         │                  │                  │
    ┌────▼────┐       ┌─────▼─────┐     ┌─────▼─────┐
    │MCP Tools│       │gRPC Invent│     │   Kafka   │
    │ Server  │       │  Service  │     │  Events   │
    └─────────┘       └───────────┘     └───────────┘
         │
    ┌────▼────────────────────────────────────────┐
    │ Prometheus · OpenTelemetry · Grafana        │
    └───────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install & run (no infra required)

Works out of the box with simulated data and in-memory fallbacks:

```bash
make install
make api          # FastAPI at http://localhost:8080
make test         # pytest suite
```

### 2. Try the agent API

```bash
# LangGraph workflow — inventory lookup with RAG + governance
curl -X POST http://localhost:8080/v1/agent/run \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","query":"Check stock for SKU 90155","workflow":"langgraph"}'

# CrewAI demand planning crew
curl -X POST http://localhost:8080/v1/agent/run \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-2","query":"Forecast beverage demand Southwest","workflow":"crew"}'

# Run governance regression eval with release gates
curl -X POST http://localhost:8080/v1/eval/run \
  -H 'Content-Type: application/json' \
  -d '{"judge_threshold": 0.6, "judge_seed": 7}'
```

### 3. Full stack with Docker Compose

```bash
make infra        # Redis, Chroma, Kafka, MLflow, Prometheus, Grafana
make grpc-server  # gRPC inventory service on :50051
make api          # Agent API on :8080
```

| Service | URL |
|---|---|
| Agent API | http://localhost:8080 |
| API docs | http://localhost:8080/docs |
| MLflow | http://localhost:5000 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |
| Chroma | http://localhost:8001 |

### 4. MCP server (Cursor / Claude Desktop)

```bash
make mcp
# Or add mcp.json.example to your MCP config
```

### 5. Governance interactive demo (original project)

```bash
make demo         # http://localhost:8000 — threshold sweep UI
```

---

## Key Features for Resume Bullets

Copy-paste these (customize with your name):

- **Built production-grade agentic AI platform** with LangGraph and CrewAI orchestration, MCP enterprise tool connectors, and agentic RAG over supply-chain SOPs — deployed via Docker/Kubernetes with full observability (Prometheus, OpenTelemetry, Grafana).

- **Designed evaluation framework** with golden-set regression suites, MLflow experiment tracking, statistical release gates (recall/precision/accuracy thresholds), and Ray-distributed threshold sweeps — evidence-first iteration, not gut-feel releases.

- **Implemented model routing layer** with complexity-based task-to-model mapping, mitigating over-escalation to expensive models and under-routing quality loss — validated against runtime telemetry.

- **Delivered MCP integration patterns** with typed tool contracts, scope-based auth, error normalization, retries, and idempotency metadata — accelerating onboarding of new enterprise connectors.

- **Established governance discipline** measuring guardrail trip rate, policy enforcement latency, intervention frequency, and cost-per-resolved-task across rules-based and LLM-as-judge approaches with interactive operating-point analysis.

---

## Project Structure

```
├── src/
│   ├── api/           # FastAPI gateway + Pydantic schemas
│   ├── agents/        # LangGraph workflow + CrewAI crew
│   ├── mcp/           # MCP server for enterprise tools
│   ├── rag/           # Chroma vector RAG
│   ├── memory/        # Redis session memory
│   ├── router/        # Model routing policies
│   ├── tools/         # Enterprise connectors + gRPC service
│   ├── events/        # Kafka event publisher
│   ├── eval/          # MLflow eval + release gates
│   └── observability/ # Prometheus + OpenTelemetry
├── harness/           # Governance benchmark (original)
├── scenarios/         # Golden-set task scenarios
├── tests/             # Unit, integration, agent simulation tests
├── proto/             # gRPC service definitions
├── k8s/               # Kubernetes deployment manifests
├── infra/             # Prometheus, Grafana, OTEL collector configs
├── docker-compose.yml # Full local stack
└── Dockerfile         # Container image
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Enable live LLM judge + CrewAI |
| `USE_LIVE_LLM` | `false` | Enable real CrewAI model calls |
| `REDIS_URL` | `redis://localhost:6379/0` | Session memory |
| `CHROMA_HOST` | `localhost` | Vector store |
| `KAFKA_BOOTSTRAP` | `localhost:9092` | Event streaming |
| `ENABLE_KAFKA` | `false` | Publish agent events to Kafka |
| `MLFLOW_TRACKING_URI` | `http://localhost:5000` | Experiment tracking |
| `OTEL_EXPORTER_ENDPOINT` | `http://localhost:4318` | Distributed tracing |

---

## Deploy

```bash
# Docker
make docker-build && make docker-run

# Kubernetes
kubectl apply -f k8s/deployment.yaml

# Render (governance demo — existing)
# Push to GitHub → render.yaml deploys app.py
```

---

## License

MIT — built as a portfolio/resume demonstration project.
