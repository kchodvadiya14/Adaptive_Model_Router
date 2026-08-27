"""CLI to generate a preference dataset."""

from __future__ import annotations

import argparse
import asyncio

from app.datasets.generator import get_dataset_generator


async def _run(source_path: str, name: str, quality_floor: float, max_prompts: int) -> None:
    generator = get_dataset_generator()
    manifest = await generator.generate(
        source_path=source_path,
        name=name,
        quality_floor=quality_floor,
        max_prompts=max_prompts,
    )
    print(f"Generated dataset {manifest.id} with {manifest.record_count} records")
    print(f"Output: {manifest.output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate preference dataset from prompts")
    parser.add_argument("--source", default="data/benchmarks/sample_prompts.json")
    parser.add_argument("--name", default="preference_dataset")
    parser.add_argument("--quality-floor", type=float, default=0.90)
    parser.add_argument("--max-prompts", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(_run(args.source, args.name, args.quality_floor, args.max_prompts))


if __name__ == "__main__":
    main()
