"""CrewAI multi-agent crew for demand planning analysis."""

from __future__ import annotations

import time
from typing import Any

from src.config import Settings


class DemandPlanningCrew:
    """Three-agent crew: analyst → validator → reporter."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, session_id: str, query: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        # CrewAI requires API key; provide deterministic fallback for demo/resume
        if self.settings.use_live_llm and self.settings.openai_api_key:
            return self._run_live_crew(session_id, query, t0)
        return self._run_simulated_crew(session_id, query, t0)

    def _run_simulated_crew(self, session_id: str, query: str, start: float) -> dict:
        analyst_output = (
            "Demand analyst: 8-week rolling average shows +12% uplift for beverage "
            "category in Southwest region. Seasonal peak expected week 28."
        )
        validator_output = (
            "Validator: Forecast within 1.5σ of historical bounds. "
            "No anomaly flags. Confidence: 0.87."
        )
        report = (
            f"## Demand Planning Report (session: {session_id})\n\n"
            f"**Query:** {query}\n\n"
            f"**Analysis:** {analyst_output}\n\n"
            f"**Validation:** {validator_output}\n\n"
            f"**Recommendation:** Increase safety stock 8% for DFW-01 beverage SKUs."
        )
        latency = (time.perf_counter() - start) * 1000
        return {
            "answer": report,
            "model": self.settings.default_model,
            "model_tier": "crew",
            "tool_calls": [
                {"tool": "demand_analyst", "input": {"query": query},
                 "output": analyst_output, "latency_ms": latency * 0.4, "success": True},
                {"tool": "forecast_validator", "input": {"query": query},
                 "output": validator_output, "latency_ms": latency * 0.3, "success": True},
                {"tool": "report_writer", "input": {"query": query},
                 "output": "report_generated", "latency_ms": latency * 0.3, "success": True},
            ],
            "governance": {"blocked": False, "reason": "read-only analysis", "approach": "rules_policy"},
            "rag_sources": ["sop-demand-forecast"],
            "cost_usd": 0.008,
            "complexity": 0.7,
        }

    def _run_live_crew(self, session_id: str, query: str, start: float) -> dict:
        try:
            from crewai import Agent, Crew, Task, Process

            analyst = Agent(
                role="Demand Analyst",
                goal="Analyze demand patterns and forecast trends",
                backstory="Expert in CPG supply-chain demand planning.",
                llm=self.settings.default_model,
                verbose=False,
            )
            validator = Agent(
                role="Forecast Validator",
                goal="Validate forecasts against historical bounds",
                backstory="Quality assurance specialist for demand models.",
                llm=self.settings.default_model,
                verbose=False,
            )
            reporter = Agent(
                role="Planning Reporter",
                goal="Produce actionable demand planning reports",
                backstory="Translates analysis into executive summaries.",
                llm=self.settings.default_model,
                verbose=False,
            )
            tasks = [
                Task(description=f"Analyze: {query}", agent=analyst, expected_output="Demand analysis"),
                Task(description="Validate the analysis", agent=validator, expected_output="Validation result"),
                Task(description="Write final report", agent=reporter, expected_output="Markdown report"),
            ]
            crew = Crew(agents=[analyst, validator, reporter], tasks=tasks, process=Process.sequential)
            result = crew.kickoff()
            latency = (time.perf_counter() - start) * 1000
            return {
                "answer": str(result),
                "model": self.settings.default_model,
                "model_tier": "crew_live",
                "tool_calls": [],
                "governance": {"blocked": False, "reason": "read-only", "approach": "rules_policy"},
                "rag_sources": [],
                "cost_usd": 0.02,
                "complexity": 0.7,
            }
        except Exception as exc:
            out = self._run_simulated_crew(session_id, query, start)
            out["answer"] += f"\n\n(CrewAI fallback: {exc})"
            return out
