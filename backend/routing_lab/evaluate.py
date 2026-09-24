"""Honest offline evaluation of routers on SPROUT.

    python -m routing_lab.evaluate [embedding-model]

Protocol
  * Train on SPROUT's train split; choose hyper-parameters (kNN k, the static router's model
    mapping, the best single model) on validation; report on the untouched test split.
  * Test prompts that also occur in train/validation are dropped (leakage guard).
  * Every curve is compared with: each single model, the best single model, the "zero router"
    (random mixing of single models), the oracle, and the gateway's existing static router.
  * 95% confidence intervals by bootstrapping test prompts (paired across routers).
  * Leave-one-source-out: train without a data source, test on it (distribution shift).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from routing_lab import metrics
from routing_lab.download import COMPACT, MODELS, OUT_DIR, PRICES
from routing_lab.embed import DEFAULT_MODEL, embeddings_path
from routing_lab.routers import (
    LAMBDAS, KnnRouter, MlpRouter, RuleTier, Table, expected_cost, realised, rule_based_choices, select,
)

FLOORS = np.linspace(0.5, 1.0, 26)
SOURCES = {"MMLU-Pro": "MMLU-Pro", "gpqa": "GPQA", "MuSR": "MuSR", "MATH": "MATH", "ragbench": "RAGBench", "openhermes": "OpenHermes"}
SHORT = {m: m.replace("wxai-", "").replace("aws-", "").replace("openai-", "").replace("-instruct", "") for m in MODELS}

# Candidate mappings of the static router's small/medium/strong tiers onto SPROUT models.
RULE_MAPPINGS = {
    "llama-8b / llama-70b / gpt-4o": ("wxai-llama-3-1-8b-instruct", "wxai-llama-3-3-70b-instruct", "openai-gpt-4o"),
    "gpt-4o-mini / gpt-4o / claude-3.5": ("openai-gpt-4o-mini", "openai-gpt-4o", "aws-claude-3-5-sonnet-v1"),
    "llama-3b / gpt-4o-mini / gpt-4o": ("wxai-llama-3-2-3b-instruct", "openai-gpt-4o-mini", "openai-gpt-4o"),
}
TIER_PRIORS = (0.82, 0.88, 0.92)  # the gateway registry's hand-set quality_score per tier


def source_of(dataset: str) -> str:
    for needle, label in SOURCES.items():
        if needle.lower() in dataset.lower():
            return label
    return "other"


def load(embedding_model: str) -> tuple[pd.DataFrame, Table, np.ndarray]:
    df = pd.read_parquet(COMPACT)
    emb = np.load(embeddings_path(embedding_model))
    assert len(df) == len(emb), "embeddings out of sync with the dataset; re-run routing_lab.embed"
    scores = np.column_stack([df[f"{m}__score"] for m in MODELS]).astype(float)
    tin = np.column_stack([df[f"{m}__num_input_tokens"] for m in MODELS]).astype(float)
    tout = np.column_stack([df[f"{m}__num_output_tokens"] for m in MODELS]).astype(float)
    prices = np.array([PRICES[m] for m in MODELS])
    keep = ~np.isnan(scores).any(axis=1)
    dropped_nan = int((~keep).sum())
    # Leakage guard: evaluation prompts must not also appear in train.
    train_prompts = set(df.loc[df.split == "train", "prompt"])
    leaked = (df.split != "train") & df.prompt.isin(train_prompts)
    keep &= ~leaked.to_numpy()
    print(f"dropped {dropped_nan} rows with missing scores and {int(leaked.sum())} val/test prompts also in train")
    df = df[keep].reset_index(drop=True)
    df["source"] = df.dataset.map(source_of)
    table = Table(emb[keep], scores[keep], (tin[keep] * prices[:, 0] + tout[keep] * prices[:, 1]) / 1e6, tin[keep], tout[keep])
    return df, table, prices


def learned_curve(router, train: Table, test: Table, prices: np.ndarray, cost_ref: float):
    pred_q, pred_out = router.predict(test.emb)
    choice = select(pred_q, expected_cost(test.in_tokens, pred_out, prices), cost_ref)
    return realised(choice, test)


def curve_of(cost: np.ndarray, quality: np.ndarray) -> np.ndarray:
    return np.column_stack([cost.mean(axis=0), quality.mean(axis=0)])


def evaluate_split(name: str, cost, quality, test: Table, best_idx: int, rounds: int = 500) -> dict:
    single_cost, single_quality = test.cost, test.scores
    lo, hi = single_cost.mean(axis=0).min(), single_cost.mean(axis=0).max()
    point = summary_point(cost, quality, test, best_idx, lo, hi)
    point["ci"] = metrics.bootstrap(
        cost, quality, best_idx, single_cost, single_quality, rounds=rounds, baseline=(single_cost, single_quality)
    )
    point["name"] = name
    return point


def summary_point(cost, quality, test: Table, best_idx: int, lo: float, hi: float) -> dict:
    best = (test.cost[:, best_idx].mean(), test.scores[:, best_idx].mean())
    s = metrics.summarise(curve_of(cost, quality), best, lo, hi)
    return {
        "aiq": s.aiq,
        "quality_at_half_best_single_cost": s.quality_at_best_single_cost_half,
        "saving_equal_quality": s.cost_saving_at_best_single_quality,
        "saving_at_95pct_quality": s.cost_saving_at_95pct_best_single_quality,
    }


def best_q_early(test: Table, best_idx: int) -> float:
    return float(test.scores[:, best_idx].mean())


def operating_point(cost: np.ndarray, quality: np.ndarray, target_quality: float) -> int | None:
    """Dial setting with the lowest mean cost whose mean quality reaches the target."""
    means_q, means_c = quality.mean(axis=0), cost.mean(axis=0)
    ok = np.where(means_q >= target_quality)[0]
    return int(ok[np.argmin(means_c[ok])]) if len(ok) else None


def run(embedding_model: str = DEFAULT_MODEL) -> dict:
    df, table, prices = load(embedding_model)
    split = df.split.to_numpy()
    idx = {s: np.where(split == s)[0] for s in ("train", "validation", "test")}
    train, val, test = (table.take(idx[s]) for s in ("train", "validation", "test"))
    fit_pool = table.take(np.concatenate([idx["train"], idx["validation"]]))
    print({s: len(v) for s, v in idx.items()})

    # Best single model is chosen without looking at test.
    best_idx = int(np.argmax(fit_pool.scores.mean(axis=0)))
    cost_ref = float(fit_pool.cost.mean(axis=0).max())
    lo, hi = test.cost.mean(axis=0).min(), test.cost.mean(axis=0).max()

    # --- Tune on validation ---
    val_best = int(np.argmax(train.scores.mean(axis=0)))
    val_lo, val_hi = val.cost.mean(axis=0).min(), val.cost.mean(axis=0).max()
    best_k, best_aiq = 40, -1.0
    for k in (20, 40, 80):
        c, q = learned_curve(KnnRouter(k).fit(train), train, val, prices, cost_ref)
        a = summary_point(c, q, val, val_best, val_lo, val_hi)["aiq"]
        print(f"  kNN k={k}: validation AIQ {a:.4f}")
        if a > best_aiq:
            best_k, best_aiq = k, a
    best_map, best_map_aiq, best_tiers = None, -1.0, None
    val_prompts = df.prompt.to_numpy()[idx["validation"]].tolist()
    for label, models in RULE_MAPPINGS.items():
        tiers = [RuleTier(t, MODELS.index(m), p) for t, m, p in zip(("small", "medium", "strong"), models, TIER_PRIORS)]
        choice = rule_based_choices(val_prompts, tiers, FLOORS)
        c, q = realised(choice, val)
        a = summary_point(c, q, val, val_best, val_lo, val_hi)["aiq"]
        print(f"  static router {label}: validation AIQ {a:.4f}")
        if a > best_map_aiq:
            best_map, best_map_aiq, best_tiers = label, a, tiers

    # --- Fit on train+validation, report on test ---
    results, curves = {}, {}
    knn = KnnRouter(best_k).fit(fit_pool)
    curves["kNN"] = learned_curve(knn, fit_pool, test, prices, cost_ref)
    print("fitting MLP ...", flush=True)
    mlp = MlpRouter().fit(fit_pool)
    curves["MLP"] = learned_curve(mlp, fit_pool, test, prices, cost_ref)
    test_prompts = df.prompt.to_numpy()[idx["test"]].tolist()
    curves["Static rules (current gateway)"] = realised(rule_based_choices(test_prompts, best_tiers, FLOORS), test)
    for label, (c, q) in curves.items():
        results[label] = evaluate_split(label, c, q, test, best_idx)
    # The bar every router must clear: randomly mixing the single models (no intelligence at all).
    results["Random mix of single models"] = evaluate_split("Random mix of single models", test.cost, test.scores, test, best_idx)

    # The cheapest single model that already reaches 95% of the best single model's quality:
    # a customer can do this with no router, so it is the fair "saving" baseline.
    single_q, single_c = test.scores.mean(axis=0), test.cost.mean(axis=0)
    good_enough = np.where(single_q >= 0.95 * best_q_early(test, best_idx))[0]
    cheap = int(good_enough[np.argmin(single_c[good_enough])])
    cheap_single = {"model": SHORT[MODELS[cheap]], "cost_per_1k_prompts": float(single_c[cheap] * 1000), "quality": float(single_q[cheap])}

    singles = {
        SHORT[m]: {"cost_per_1k_prompts": float(test.cost[:, i].mean() * 1000), "quality": float(test.scores[:, i].mean())}
        for i, m in enumerate(MODELS)
    }
    oracle_quality = test.scores.max(axis=1)
    cheapest_best = np.where(test.scores >= oracle_quality[:, None] - 1e-9, test.cost, np.inf).min(axis=1)
    best_cost, best_q = float(test.cost[:, best_idx].mean()), float(test.scores[:, best_idx].mean())

    # --- Per-source view at each router's matched-quality operating point ---
    src = df.source.to_numpy()[idx["test"]]
    per_source: dict[str, dict] = {}
    for label, (c, q) in curves.items():
        op = operating_point(c, q, 0.95 * best_q)
        if op is None:
            continue
        rows = {}
        for s in sorted(set(src)):
            m = src == s
            rows[s] = {
                "n": int(m.sum()),
                "router_cost": float(c[m, op].mean()), "router_quality": float(q[m, op].mean()),
                "best_single_cost": float(test.cost[m, best_idx].mean()), "best_single_quality": float(test.scores[m, best_idx].mean()),
            }
        per_source[label] = rows

    # --- Leave-one-source-out (kNN) ---
    loso = {}
    srcs_all = df.source.to_numpy()
    for s in sorted(set(srcs_all[idx["test"]])):
        tr = np.concatenate([idx["train"], idx["validation"]])
        tr = tr[srcs_all[tr] != s]
        te = idx["test"][srcs_all[idx["test"]] == s]
        if len(te) < 30:
            continue
        tr_t, te_t = table.take(tr), table.take(te)
        b = int(np.argmax(tr_t.scores.mean(axis=0)))
        c, q = learned_curve(KnnRouter(best_k).fit(tr_t), tr_t, te_t, prices, float(tr_t.cost.mean(axis=0).max()))
        loso[s] = evaluate_split("kNN (source held out)", c, q, te_t, b, rounds=200) | {"n_test": int(len(te)), "best_single": SHORT[MODELS[b]]}

    report = {
        "embedding_model": embedding_model, "n": {s: int(len(v)) for s, v in idx.items()},
        "best_single": {"model": SHORT[MODELS[best_idx]], "cost_per_1k_prompts": best_cost * 1000, "quality": best_q},
        "oracle": {"quality": float(oracle_quality.mean()), "cost_per_1k_prompts": float(cheapest_best.mean() * 1000)},
        "cheapest_single_at_95pct": cheap_single,
        "static_router_mapping": best_map, "knn_k": best_k, "singles": singles,
        "routers": results, "per_source": per_source, "leave_one_source_out": loso,
        "curves": {k: {"cost": curve_of(*v)[:, 0].tolist(), "quality": curve_of(*v)[:, 1].tolist()} for k, v in curves.items()},
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    from routing_lab.report import write_report

    write_report(report)
    return report


if __name__ == "__main__":
    run(*sys.argv[1:2])
