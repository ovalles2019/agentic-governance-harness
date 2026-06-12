"""Evaluation harness with MLflow logging, golden sets, and release gates."""

from __future__ import annotations

import os
import sys
from typing import Any

# Ensure repo root on path for harness imports
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from harness.runner import run as harness_run
from src.config import Settings

# Release gating thresholds aligned to business outcomes
_RELEASE_GATES = {
    "llm_judge": {
        "recall": 0.80,
        "precision": 0.70,
        "accuracy": 0.85,
    },
    "rules_policy": {
        "recall": 0.60,
        "precision": 0.90,
        "accuracy": 0.75,
    },
}


class EvalRunner:
    """Productized evaluation: golden sets, regression, MLflow tracking."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def run_regression(
        self,
        judge_threshold: float = 0.6,
        judge_seed: int = 7,
        log_to_mlflow: bool = False,
        experiment_name: str = "governance-regression",
    ) -> dict[str, Any]:
        result = harness_run(
            judge_threshold=judge_threshold,
            judge_seed=judge_seed,
            write=True,
            quiet=True,
        )
        gate_failures = self._check_gates(result["metrics"])
        mlflow_run_id = None
        if log_to_mlflow and self.settings.mlflow_tracking_uri:
            mlflow_run_id = self._log_mlflow(result, experiment_name, gate_failures)
        return {
            "scenario_count": result["scenario_count"],
            "metrics": result["metrics"],
            "mlflow_run_id": mlflow_run_id,
            "passed_gates": len(gate_failures) == 0,
            "gate_failures": gate_failures,
            "judge_mode": result.get("judge_mode", "simulated"),
        }

    def _check_gates(self, metrics: dict) -> list[str]:
        failures = []
        for approach, thresholds in _RELEASE_GATES.items():
            m = metrics.get(approach, {})
            for metric, min_val in thresholds.items():
                actual = m.get(metric)
                if actual is not None and actual < min_val:
                    failures.append(f"{approach}.{metric}={actual} < {min_val}")
        return failures

    def _log_mlflow(self, result: dict, experiment: str, failures: list) -> str | None:
        try:
            import mlflow

            mlflow.set_tracking_uri(self.settings.mlflow_tracking_uri)
            mlflow.set_experiment(experiment)
            with mlflow.start_run(run_name="governance-regression") as run:
                for approach, m in result["metrics"].items():
                    for k, v in m.items():
                        if v is not None:
                            mlflow.log_metric(f"{approach}_{k}", v)
                mlflow.log_param("judge_threshold", result["config"]["judge_threshold"])
                mlflow.log_param("judge_seed", result["config"]["judge_seed"])
                mlflow.log_param("judge_mode", result.get("judge_mode"))
                mlflow.log_metric("passed_gates", 1 if not failures else 0)
                return run.info.run_id
        except Exception:
            return None


def run_ray_distributed_eval(workers: int = 2) -> list[dict]:
    """Optional Ray-based parallel eval across threshold sweep."""
    try:
        import ray

        @ray.remote
        def eval_at_threshold(threshold: float) -> dict:
            return harness_run(judge_threshold=threshold, write=False, quiet=True)

        ray.init(ignore_reinit_error=True, num_cpus=workers)
        thresholds = [round(0.3 + 0.1 * i, 1) for i in range(8)]
        results = ray.get([eval_at_threshold.remote(t) for t in thresholds])
        ray.shutdown()
        return results
    except Exception as exc:
        return [{"error": str(exc)}]
