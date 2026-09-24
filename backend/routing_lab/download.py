"""Fetch SPROUT (CARROT-LLM-Routing/SPROUT) and keep only what routing research needs.

SPROUT: ~44k prompts from MATH, MMLU-Pro, GPQA, MuSR, RAGBench and OpenHermes, each answered by
13 LLMs and scored 0-1 by a judge. We drop the response texts (most of the ~580MB) and keep the
prompt, the per-model score and token counts, plus the dataset's own train/validation/test split.

The dataset card states no license: use it for research and evaluation, and check the terms
before training anything you ship on it.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

REPO = "CARROT-LLM-Routing/SPROUT"
FILES = {
    "train": [f"data/train-0000{i}-of-00003.parquet" for i in range(3)],
    "validation": ["data/validation-00000-of-00001.parquet"],
    "test": ["data/test-00000-of-00001.parquet"],
}
OUT_DIR = Path("data/lab")
COMPACT = OUT_DIR / "sprout_compact.parquet"

# Dollars per million tokens [input, output], as published with the CARROT code
# (github.com/somerstep/CARROT, carrot/constants.py). Used to price every model identically.
PRICES: dict[str, tuple[float, float]] = {
    "aws-claude-3-5-sonnet-v1": (3.0, 15.0),
    "aws-titan-text-premier-v1": (0.8, 3.2),
    "openai-gpt-4o": (2.5, 10.0),
    "openai-gpt-4o-mini": (0.15, 0.6),
    "wxai-granite-3-2b-instruct-8k-max-tokens": (0.1, 0.1),
    "wxai-granite-3-8b-instruct-8k-max-tokens": (0.2, 0.2),
    "wxai-llama-3-1-70b-instruct": (0.9, 0.9),
    "wxai-llama-3-1-8b-instruct": (0.2, 0.2),
    "wxai-llama-3-2-1b-instruct": (0.06, 0.06),
    "wxai-llama-3-2-3b-instruct": (0.06, 0.06),
    "wxai-llama-3-3-70b-instruct": (0.9, 0.9),
    "wxai-llama-3-405b-instruct": (3.5, 3.5),
    "wxai-mixtral-8x7b-instruct-v01": (0.6, 0.6),
}
MODELS = list(PRICES)


def build() -> Path:
    import pandas as pd

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = ["key", "dataset", "dataset_level", "prompt"]

    frames = []
    for split, files in FILES.items():
        for name in files:
            print(f"fetching {name}", flush=True)
            path = hf_hub_download(REPO, name, repo_type="dataset")
            # Whole struct columns are read (responses included) one file at a time, then only
            # the score and token counts are kept.
            table = pq.read_table(path, columns=base + MODELS)
            frame = table.select(base).to_pandas()
            for model in MODELS:
                column = table.column(model).combine_chunks()
                for field in ("score", "num_input_tokens", "num_output_tokens"):
                    frame[f"{model}__{field}"] = column.field(field).to_numpy(zero_copy_only=False)
            frame["split"] = split
            frames.append(frame)
            del table
    data = pd.concat(frames, ignore_index=True)
    data.to_parquet(COMPACT)
    print(f"{len(data)} prompts -> {COMPACT}")
    print(data.groupby(["split", "dataset"]).size().unstack(0))
    return COMPACT


if __name__ == "__main__":
    build()
