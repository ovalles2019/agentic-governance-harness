# Agentic AI Governance — Benchmark & Measurement Harness

A reproducible test bed that produces **instrumented evidence** for how different
governance approaches perform on agentic AI tasks — measuring guardrail trip
rates, policy enforcement latency, intervention frequency, and cost per resolved
task, rather than asserting guardrails work and moving on.

This is a v0.1 proof of concept: small, honest, and fully reproducible. Every
number in the dashboard regenerates from a single command.

## Why this exists

The industry has a lot of claims about guardrails, policy enforcement, and agent
controls, and very little measured evidence of what those claims cost or how well
they hold up. A trip rate alone is meaningless — you need to know whether the
trips were *correct*, what latency they added, how often a human got pulled in,
and what each correctly-resolved task actually cost. This harness measures all of
that across multiple approaches on the same task suite, so they can be compared
apples to apples.

## Quick start

```bash
make run          # regenerate results/results.json and results.csv
make serve        # run + serve the static dashboard at localhost:8000/dashboard.html
make demo         # launch the interactive live demo at localhost:8000
```

No dependencies beyond Python 3.10+ — the harness, the live demo server, and the
CLI all use only the standard library. The dashboards use Chart.js from a CDN.

## Live interactive demo

`app.py` is a zero-dependency standard-library web server that exposes the
harness as a live, interactive demo:

- `GET /` — a polished UI where you drag the LLM-judge **risk threshold** and
  every metric (recall, precision, trip rate, intervention frequency, cost per
  resolved task) recomputes against ground truth in real time, with an
  operating-point sweep chart, a detection-vs-cost scatter, and a filterable
  per-task trace.
- `GET /api/run?threshold=<float>&seed=<int>` — runs the full suite and returns
  results JSON. No disk writes (Render's filesystem is ephemeral).
- `GET /healthz` — health check.

```bash
python app.py     # http://localhost:8000  (honors $PORT)
```

### Deploy to Render

A `render.yaml` Blueprint is included. The service is a single Python web
service with no build dependencies:

```yaml
runtime: python
buildCommand: pip install -r requirements.txt   # requirements.txt is empty
startCommand: python app.py                      # binds 0.0.0.0:$PORT
healthCheckPath: /healthz
```

Push the repo to GitHub and open
`https://dashboard.render.com/blueprint/new?repo=<your-repo-url>` to deploy.

## What's measured

| Metric | Definition |
|---|---|
| **Guardrail trip rate** | Fraction of tasks the approach blocked |
| **Policy enforcement latency** | Mean latency added by the governance layer (excludes base agent latency) |
| **Intervention frequency** | Fraction of tasks escalated to a human |
| **Cost per resolved task** | Total cost ÷ number of *correctly* handled tasks |
| Accuracy / precision / recall | Governance decisions scored against ground-truth labels |

Recall and precision matter because a high trip rate is only good if the trips
are correct. An approach that blocks everything has a perfect violation-recall
and is also useless.

## Approaches under test

1. **No guardrails** — baseline. Allows everything. Establishes the cost and the
   failure rate of doing nothing.
2. **Rules policy** — deterministic pattern matching on the agent's intended
   action. Fast, cheap, brittle.
3. **LLM judge** — a model-as-judge that reasons about each action. Higher
   latency and cost, better at catching intent the rules miss, but can over-block
   ambiguous cases and routes blocks to humans.

## Task suite

12 scenarios in `scenarios/tasks.py`, spanning three classes:
- **Benign** (5): a good agent completes these; governance should allow.
- **Adversarial** (5): data exfiltration, mass refunds, audit-log deletion,
  privilege escalation, disabling the policy engine. A good agent is blocked.
- **Ambiguous** (2): borderline actions (bulk PII read for stated business use,
  single scoped refund) that surface false-positive / false-negative behavior.

Each scenario carries a ground-truth `expected_violation` label used for scoring.

## Architecture

```
scenarios/tasks.py      task definitions + ground truth
harness/governance.py   the three swappable governance approaches
harness/runner.py       runs every scenario × approach, computes metrics
dashboard.html          reads results.json, renders metrics + per-task trace
results/                generated JSON + CSV
```

The governance layer is a clean interface (`evaluate(action) -> decision`), so
adding a fourth approach is one class. The agent is deliberately **mocked** for
determinism, zero cost, and exact reproducibility — see below.

## Why the agent is mocked (and how to go live)

A mocked agent makes the harness deterministic, free to run, and reproducible to
the cent — which is the entire point of a measurement test bed. The mock is
isolated to two spots:

- `scenarios/tasks.py` → `agent_intended_action`: swap for a real model's
  proposed tool call.
- `harness/governance.py` → `LlmJudge._simulated_judge` logic: swap for a real
  model call returning an allow/block verdict.

Neither change touches the runner, the metrics, or the dashboard. The interfaces
hold. That separation is intentional: the measurement infrastructure should not
care whether the agent is real or simulated.

## Honest limitations

- Latencies and token costs for the LLM judge are *simulated* within realistic
  ranges, not measured from a live endpoint. Plugging in a real model is the
  obvious next step and the code is structured for it.
- 12 scenarios is a demonstration suite, not a statistically powered benchmark.
  The architecture scales to hundreds; the scenario list is just data.
- "Resolved correctly" is scored against hand-labeled ground truth, which is the
  right approach but requires careful labeling as the suite grows.

## Roadmap (if this became real)

- Live LLM agent + real model-as-judge with measured latency/cost.
- Adversarial scenario generation instead of hand-authored cases.
- Load testing — these metrics under concurrency are where the interesting
  failures live.
- A maturity axis: re-run the suite at assisted / augmented / autonomous levels.
