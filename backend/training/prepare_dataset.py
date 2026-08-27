"""Prepare preference dataset for ML router training."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.datasets.storage import load_records


def prepare_training_csv(dataset_id: str, output_path: str, label: str = "strong_better") -> Path:
    records = load_records(dataset_id)
    if not records:
        raise ValueError(f"No records found for dataset '{dataset_id}'")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["prompt", "task_type", "difficulty", "small_score", "medium_score", "strong_score", label],
        )
        writer.writeheader()
        for record in records:
            strong_better = 1 if record.strong_score > max(record.small_score, record.medium_score) else 0
            writer.writerow(
                {
                    "prompt": record.prompt,
                    "task_type": record.task_type,
                    "difficulty": record.difficulty,
                    "small_score": record.small_score,
                    "medium_score": record.medium_score,
                    "strong_score": record.strong_score,
                    label: strong_better,
                }
            )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare preference dataset for router training")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", default="data/processed/training_set.csv")
    parser.add_argument("--label", default="strong_better")
    args = parser.parse_args()

    output = prepare_training_csv(args.dataset_id, args.output, args.label)
    print(f"Saved training CSV to {output}")


if __name__ == "__main__":
    main()
