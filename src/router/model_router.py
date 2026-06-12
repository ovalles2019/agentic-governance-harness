"""Task-to-model routing with rules + lightweight complexity classifier."""

from __future__ import annotations

import re

from src.config import Settings

# Heuristics for routing failure-mode mitigation (over/under-escalation).
_COMPLEXITY_PATTERNS = [
    (r"\b(forecast|optimize|simulate|what.?if)\b", 0.4),
    (r"\b(all|every|bulk|mass|enterprise.?wide)\b", 0.35),
    (r"\b(escalat|compliance|audit|policy)\b", 0.25),
    (r"\b(compare|analyze|trend|root.?cause)\b", 0.2),
]
_SIMPLE_PATTERNS = [
    (r"\b(status|lookup|check|what is)\b", -0.3),
    (r"\b(sku|order|shipment)\s*#?\d+", -0.2),
]


class ModelRouter:
    """Routes tasks to cheap vs premium models based on complexity score."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def score_complexity(self, query: str) -> float:
        text = query.lower()
        score = 0.3  # baseline
        for pattern, weight in _COMPLEXITY_PATTERNS:
            if re.search(pattern, text, re.I):
                score += weight
        for pattern, weight in _SIMPLE_PATTERNS:
            if re.search(pattern, text, re.I):
                score += weight
        return max(0.0, min(1.0, score))

    def select_model(self, query: str) -> tuple[str, float, str]:
        complexity = self.score_complexity(query)
        threshold = self.settings.router_complexity_threshold
        if complexity >= threshold:
            return self.settings.premium_model, complexity, "premium"
        return self.settings.default_model, complexity, "default"
