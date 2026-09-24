"""Turn the evaluation result into a markdown report and a cost-vs-quality chart."""

from __future__ import annotations

from routing_lab.download import OUT_DIR


def _pct(x: float | None) -> str:
    return "never reaches it" if x is None else f"{x:+.1%}"


def _ci(triple: tuple[float, float, float], pct: bool = True) -> str:
    mean, lo, hi = triple
    return f"{mean:.1%} ({lo:.1%} to {hi:.1%})" if pct else f"{mean:.3f} ({lo:.3f} to {hi:.3f})"


def chart(report: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from routing_lab import metrics
    import numpy as np

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    singles = report["singles"]
    ax.scatter([v["cost_per_1k_prompts"] for v in singles.values()], [v["quality"] for v in singles.values()],
               c="#888", s=28, label="single models", zorder=3)
    for name, v in singles.items():
        ax.annotate(name, (v["cost_per_1k_prompts"], v["quality"]), fontsize=6, xytext=(3, 3), textcoords="offset points")
    pts = np.array([[v["cost_per_1k_prompts"], v["quality"]] for v in singles.values()])
    hull = metrics.upper_hull(pts)
    ax.plot(hull[:, 0], hull[:, 1], "--", c="#888", lw=1, label="random mix of single models")
    colours = {"kNN": "#1f77b4", "MLP": "#2ca02c", "Static rules (current gateway)": "#d62728"}
    for name, curve in report["curves"].items():
        h = metrics.upper_hull(np.column_stack([np.array(curve["cost"]) * 1000, curve["quality"]]))
        ax.plot(h[:, 0], h[:, 1], c=colours.get(name), lw=2, label=name)
    ax.scatter([report["oracle"]["cost_per_1k_prompts"]], [report["oracle"]["quality"]], marker="*", s=140, c="gold",
               edgecolors="k", label="oracle", zorder=4)
    ax.set_xscale("log")
    ax.set_xlabel("cost per 1,000 prompts (USD, log scale)")
    ax.set_ylabel("mean judged quality (0-1)")
    ax.set_title("Router cost vs quality on held-out SPROUT prompts")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "curves.png", dpi=150)
    plt.close(fig)


def write_report(report: dict) -> None:
    chart(report)
    best = report["best_single"]
    lines = [
        "# Offline router evaluation (SPROUT)",
        "",
        f"Encoder: `{report['embedding_model']}`. Train/val/test prompts: {report['n']['train']}/{report['n']['validation']}/{report['n']['test']}. "
        f"Prices are per-model list prices from the CARROT project; quality is SPROUT's judge score (0-1). "
        "Everything below is measured on test prompts the routers never saw; intervals are 95% bootstrap over prompts.",
        "",
        f"**Best single model** (chosen without the test set): `{best['model']}` - quality {best['quality']:.3f} at ${best['cost_per_1k_prompts']:.2f} per 1k prompts. "
        f"**Oracle** (always the best model, cheapest on ties): quality {report['oracle']['quality']:.3f} at ${report['oracle']['cost_per_1k_prompts']:.2f} per 1k prompts.",
        "",
        "## Routers vs the best single model",
        "",
        "| Router | AIQ | AIQ uplift over random mixing | Cost saving at equal quality | Cost saving at 95% of best-single quality |",
        "|---|---|---|---|---|",
    ]
    for name, r in report["routers"].items():
        ci = r["ci"]
        uplift = _ci(ci["aiq_uplift"], pct=False) if "aiq_uplift" in ci else "-"
        lines.append(f"| {name} | {_ci(ci['aiq'], pct=False)} | {uplift} | {_ci(ci['saving_equal_quality'])} | {_ci(ci['saving_at_95pct'])} |")
    cheap = report["cheapest_single_at_95pct"]
    lines += [
        "",
        "AIQ = mean quality over the cost range from the cheapest to the priciest single model (higher is better). "
        "Uplift over random mixing is the fair measure of routing intelligence: it is what the router adds beyond simply "
        "blending models. A saving of 0% means the router could not match the best single model any cheaper.",
        "",
        f"**Caution on the savings columns.** A customer needs no router to save money against the best model: "
        f"`{cheap['model']}` alone reaches quality {cheap['quality']:.3f} (95% of the best single model's) at "
        f"${cheap['cost_per_1k_prompts']:.2f} per 1k prompts. Only savings *beyond* that single-model choice, and the AIQ uplift, "
        f"are credit to the router.",
        "",
        "## Single models",
        "",
        "| Model | Cost / 1k prompts | Quality |",
        "|---|---|---|",
    ]
    for name, v in sorted(report["singles"].items(), key=lambda kv: kv[1]["cost_per_1k_prompts"]):
        lines.append(f"| {name} | ${v['cost_per_1k_prompts']:.3f} | {v['quality']:.3f} |")
    lines += ["", "## Per data source at each router's operating point matching 95% of best-single quality", ""]
    for router, rows in report["per_source"].items():
        lines += [f"**{router}**", "", "| Source | n | Router cost | Router quality | Best-single cost | Best-single quality |", "|---|---|---|---|---|---|"]
        for s, r in rows.items():
            lines.append(f"| {s} | {r['n']} | ${r['router_cost']*1000:.3f} | {r['router_quality']:.3f} | ${r['best_single_cost']*1000:.3f} | {r['best_single_quality']:.3f} |")
        lines.append("")
    lines += ["## Distribution shift: kNN router with one data source held out of training", "",
              "| Held-out source | n test | Best single | AIQ | Saving at equal quality | Saving at 95% |", "|---|---|---|---|---|---|"]
    for s, r in report["leave_one_source_out"].items():
        ci = r["ci"]
        lines.append(f"| {s} | {r['n_test']} | {r['best_single']} | {_ci(ci['aiq'], pct=False)} | {_ci(ci['saving_equal_quality'])} | {_ci(ci['saving_at_95pct'])} |")
    lines += ["", "![cost vs quality](curves.png)", "",
              f"Static router tiers mapped as: {report['static_router_mapping']} (mapping chosen on validation). kNN k={report['knn_k']}.", ""]
    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_DIR / 'report.md'}")
