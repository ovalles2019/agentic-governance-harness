"""LangGraph multi-agent workflow for supply-chain task orchestration."""

from __future__ import annotations

import re
import time
from typing import Any, TypedDict

from src.config import Settings
from src.memory.redis_memory import AgentMemory
from src.observability.telemetry import span
from src.rag.knowledge_base import KnowledgeBase
from src.router.model_router import ModelRouter
from src.tools.connectors import SupplyChainTools

# Import existing governance harness
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from harness.governance import RulesPolicy, LlmJudge


class AgentState(TypedDict):
    session_id: str
    query: str
    model: str
    rag_context: str
    rag_sources: list[str]
    memory_context: str
    planned_action: str
    tool_calls: list[dict]
    governance: dict
    answer: str
    cost_usd: float


class LangGraphAgent:
    """Composable agent: RAG → tool-use → governance → response."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.memory = AgentMemory(settings)
        self.kb = KnowledgeBase(settings)
        self.tools = SupplyChainTools(settings)
        self.router = ModelRouter(settings)
        self.rules = RulesPolicy()
        self.judge = LlmJudge(seed=settings.judge_seed, threshold=settings.judge_threshold)
        self._graph = self._build_graph()

    def _build_graph(self):
        try:
            from langgraph.graph import END, StateGraph

            graph = StateGraph(AgentState)
            graph.add_node("retrieve", self._retrieve)
            graph.add_node("plan", self._plan)
            graph.add_node("execute", self._execute)
            graph.add_node("govern", self._govern)
            graph.add_node("respond", self._respond)
            graph.set_entry_point("retrieve")
            graph.add_edge("retrieve", "plan")
            graph.add_edge("plan", "execute")
            graph.add_edge("execute", "govern")
            graph.add_edge("govern", "respond")
            graph.add_edge("respond", END)
            return graph.compile()
        except ImportError:
            return None

    def run(self, session_id: str, query: str) -> dict[str, Any]:
        model, complexity, tier = self.router.select_model(query)
        state: AgentState = {
            "session_id": session_id,
            "query": query,
            "model": model,
            "rag_context": "",
            "rag_sources": [],
            "memory_context": "",
            "planned_action": "",
            "tool_calls": [],
            "governance": {},
            "answer": "",
            "cost_usd": 0.002,
        }
        with span("langgraph.run", {"session_id": session_id, "model_tier": tier}):
            if self._graph:
                result = self._graph.invoke(state)
            else:
                result = self._linear_run(state)
        self.memory.append(session_id, "user", query)
        self.memory.append(session_id, "assistant", result["answer"])
        return {**result, "model_tier": tier, "complexity": complexity}

    def _linear_run(self, state: AgentState) -> AgentState:
        for step in (self._retrieve, self._plan, self._execute, self._govern, self._respond):
            state = step(state)
        return state

    def _retrieve(self, state: AgentState) -> AgentState:
        docs = self.kb.retrieve(state["query"])
        state["rag_sources"] = [d["id"] for d in docs]
        state["rag_context"] = "\n".join(d["text"] for d in docs)
        state["memory_context"] = self.memory.summarize_context(state["session_id"])
        return state

    def _plan(self, state: AgentState) -> AgentState:
        q = state["query"].lower()
        if re.search(r"sku\s*#?\s*(\d+)", q, re.I):
            sku = re.search(r"sku\s*#?\s*(\d+)", q, re.I).group(1)
            state["planned_action"] = f"read:inventory where sku={sku}"
        elif re.search(r"order\s*#?\s*(\d+)", q, re.I):
            oid = re.search(r"order\s*#?\s*(\d+)", q, re.I).group(1)
            state["planned_action"] = f"read:orders where id={oid}"
        else:
            state["planned_action"] = f"read:general query={state['query'][:80]}"
        return state

    def _execute(self, state: AgentState) -> AgentState:
        q = state["query"]
        calls = []
        sku_match = re.search(r"sku\s*#?\s*(\d+)", q, re.I)
        order_match = re.search(r"order\s*#?\s*(\d+)", q, re.I)
        if sku_match:
            result = self.tools.inventory_lookup(sku_match.group(1))
            calls.append({
                "tool": result.tool,
                "input": {"sku": sku_match.group(1)},
                "output": result.data,
                "latency_ms": result.latency_ms,
                "success": result.success,
            })
        if order_match:
            result = self.tools.order_status(order_match.group(1))
            calls.append({
                "tool": result.tool,
                "input": {"order_id": order_match.group(1)},
                "output": result.data,
                "latency_ms": result.latency_ms,
                "success": result.success,
            })
        state["tool_calls"] = calls
        return state

    def _govern(self, state: AgentState) -> AgentState:
        decision = self.judge.evaluate(state["planned_action"])
        state["governance"] = {
            "blocked": decision.blocked,
            "reason": decision.reason,
            "approach": "llm_judge",
            "risk_score": None,
        }
        state["cost_usd"] += decision.added_cost_usd
        return state

    def _respond(self, state: AgentState) -> AgentState:
        if state["governance"].get("blocked"):
            state["answer"] = (
                f"Action blocked by governance policy: {state['governance']['reason']}. "
                "Please escalate to a human reviewer."
            )
            return state
        parts = []
        for call in state["tool_calls"]:
            if call["success"]:
                parts.append(f"{call['tool']}: {call['output']}")
        if parts:
            state["answer"] = "Here's what I found:\n" + "\n".join(parts)
        else:
            ctx = state["rag_context"][:500] if state["rag_context"] else "No specific data."
            state["answer"] = (
                f"Based on supply-chain policies: {ctx}\n\n"
                f"Re: {state['query']}"
            )
        return state
