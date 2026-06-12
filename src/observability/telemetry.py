"""OpenTelemetry + Prometheus instrumentation."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

AGENT_REQUESTS = Counter(
    "agent_requests_total",
    "Total agent requests",
    ["workflow", "model", "status"],
)
AGENT_LATENCY = Histogram(
    "agent_latency_seconds",
    "Agent end-to-end latency",
    ["workflow"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
TOOL_CALLS = Counter(
    "tool_calls_total",
    "Tool invocations",
    ["tool", "success"],
)
GOVERNANCE_BLOCKS = Counter(
    "governance_blocks_total",
    "Governance policy blocks",
    ["approach"],
)

_otel_configured = False


def setup_telemetry(service_name: str, endpoint: str | None) -> None:
    global _otel_configured
    if _otel_configured or not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        _otel_configured = True
    except Exception:
        pass


def get_tracer():
    try:
        from opentelemetry import trace
        return trace.get_tracer("supply-chain-agent")
    except Exception:
        return None


@contextmanager
def span(name: str, attributes: dict | None = None) -> Generator[None, None, None]:
    tracer = get_tracer()
    if tracer is None:
        yield
        return
    with tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
        yield


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


class Timer:
    def __init__(self):
        self._start = time.perf_counter()
        self.elapsed_ms = 0.0

    def stop(self) -> float:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
        return self.elapsed_ms
