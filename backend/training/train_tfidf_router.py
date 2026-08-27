"""CLI entry point for TF-IDF router training."""

from __future__ import annotations

import argparse

from app.training.train_tfidf import train_tfidf_router


def main() -> None:
    parser = argparse.ArgumentParser(description="Train TF-IDF logistic regression router")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args()
    info = train_tfidf_router(args.dataset_id, args.threshold)
    print(f"Trained TF-IDF router {info.id} | test accuracy={info.metrics.test_accuracy:.3f}")


if __name__ == "__main__":
    main()
