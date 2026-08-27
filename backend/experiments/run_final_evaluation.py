"""CLI entry point for the Milestone 10 final evaluation suite."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.evaluation.experiment_reports import save_experiment_report
from app.evaluation.experiments import get_experiment_runner
from app.schemas.experiments import ExperimentRequest, ExperimentType


async def _run(config_path: str | None, max_prompts: int | None) -> None:
    payload: dict = {}
    if config_path:
        payload = json.loads(Path(config_path).read_text(encoding="utf-8"))

    if max_prompts is not None:
        payload["max_prompts"] = max_prompts

    request = ExperimentRequest.model_validate(payload)
    if "experiment_type" not in payload:
        request = request.model_copy(update={"experiment_type": ExperimentType.FINAL_EVALUATION})

    runner = get_experiment_runner()
    report = await runner.run(request)
    path = save_experiment_report(report)
    print(f"Experiment report saved to {path}")
    print()
    print(report.summary)
    print()
    print(report.markdown_summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the adaptive router final evaluation suite.")
    parser.add_argument(
        "--config",
        default="../experiments/configs/final_evaluation.json",
        help="Path to experiment config JSON",
    )
    parser.add_argument("--max-prompts", type=int, default=None, help="Override max prompts")
    args = parser.parse_args()
    asyncio.run(_run(args.config, args.max_prompts))


if __name__ == "__main__":
    main()
