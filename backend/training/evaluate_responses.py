"""CLI to evaluate stored responses with the configured judge."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.datasets.storage import load_records, save_records, get_manifest
from app.evaluation.judge import get_judge


async def _run(dataset_id: str) -> None:
    manifest = get_manifest(dataset_id)
    if not manifest:
        raise ValueError(f"Dataset '{dataset_id}' not found")

    judge = get_judge()
    records = load_records(dataset_id)
    updated = []
    for record in records:
        small = await judge.evaluate(record.prompt, record.small_response)
        medium = await judge.evaluate(record.prompt, record.medium_response)
        strong = await judge.evaluate(record.prompt, record.strong_response)
        updated.append(
            record.model_copy(
                update={
                    "small_score": small.overall,
                    "medium_score": medium.overall,
                    "strong_score": strong.overall,
                    "small_judge": small,
                    "medium_judge": medium,
                    "strong_judge": strong,
                    "evaluation_source": "judge",
                }
            )
        )
    save_records(dataset_id, updated)
    print(json.dumps({"dataset_id": dataset_id, "records_updated": len(updated)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-evaluate dataset responses with the judge")
    parser.add_argument("--dataset-id", required=True)
    args = parser.parse_args()
    asyncio.run(_run(args.dataset_id))


if __name__ == "__main__":
    main()
