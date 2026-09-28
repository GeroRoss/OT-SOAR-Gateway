"""Recreate Figure 5.4 from evaluation/results/performance_metrics.jsonl.

Install: pip install matplotlib
Run: python plot_performance.py evaluation/results/performance_metrics.jsonl
The default run ID matches the run discussed in the report. To use another
complete run, supply --run-id; use --list-runs to see available IDs.
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REPORT_RUN_ID = "perf-20260922-105354-31b7a7"
NEEDED = (
    "quarantine_observation_latency",
    "end_to_end_response_observation_latency",
    "legitimate_request_latency_normal",
)


def load_runs(path):
    runs = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_number}") from exc
            run_id = record.get("context", {}).get("performance_run_id")
            if run_id:
                runs.setdefault(run_id, {})[record["metric"]] = record
    return runs


def plot_run(records, output):
    missing = set(NEEDED) - records.keys()
    if missing:
        raise ValueError(f"Run is missing metrics: {', '.join(sorted(missing))}")

    # The JSONL stores milliseconds. The left panel displays seconds.
    quarantine = [value / 1000 for value in records[NEEDED[0]]["values"]]
    response = [value / 1000 for value in records[NEEDED[1]]["values"]]
    observations = records[NEEDED[2]]["context"]["observations"]
    normal = [item["normal_mean_ms"] for item in observations]
    attack = [item["attack_mean_ms"] for item in observations]
    if not (len(quarantine) == len(response) == len(normal) == len(attack)):
        raise ValueError("The incident and paired-request repetition counts differ")
    repetitions = list(range(1, len(quarantine) + 1))

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.6})
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.35), dpi=200)
    blue, orange = "#146890", "#c36c20"

    axes[0].plot(repetitions, quarantine, "o-", color=blue, lw=1.8, ms=5,
                 label="Quarantine observed")
    axes[0].plot(repetitions, response, "s-", color=orange, lw=1.8, ms=5,
                 label="Response observed")
    axes[0].set(title="(a) Flood incident observations", xlabel="Incident repetition",
                ylabel="Seconds since launch request", xticks=repetitions, ylim=(0, 1.35))
    axes[0].legend(fontsize=7, loc="upper right", frameon=False)

    for x, before, after in zip(repetitions, normal, attack):
        axes[1].plot([x, x], [before, after], color="#a9afb4", lw=1.4, zorder=1)
    axes[1].scatter([x - 0.055 for x in repetitions], normal, color=blue, s=34,
                    label="Normal", zorder=2)
    axes[1].scatter([x + 0.055 for x in repetitions], attack, color=orange, s=34,
                    marker="s", label="Attack run", zorder=2)
    axes[1].set(title="(b) Authorized PDU requests",
                xlabel="Paired repetition (20 requests per condition)",
                ylabel="Mean request latency (ms)", xticks=repetitions, ylim=(0, 72))
    axes[1].legend(fontsize=7, loc="upper right", frameon=False)

    for axis in axes:
        axis.grid(axis="y", alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(pad=1.6, w_pad=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    def mean(values):
        return sum(values) / len(values)

    print(f"Quarantine observed: {mean(quarantine):.3f} s (n={len(quarantine)})")
    print(f"Response observed: {mean(response):.3f} s (n={len(response)})")
    print(f"Normal requests: {mean(normal):.2f} ms; attack-run requests: {mean(attack):.2f} ms")
    print(f"Saved chart: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metrics", type=Path, help="Path to performance_metrics.jsonl")
    parser.add_argument("--run-id", default=REPORT_RUN_ID,
                        help=f"Recorded run (default: {REPORT_RUN_ID})")
    parser.add_argument("--output", type=Path, default=Path("ot_soar_figure_5_4.png"))
    parser.add_argument("--list-runs", action="store_true", help="List run IDs and exit")
    args = parser.parse_args()
    runs = load_runs(args.metrics)
    if args.list_runs:
        for run_id, metrics in runs.items():
            print(f"{run_id}: {len(metrics)} metrics")
        return
    if args.run_id not in runs:
        parser.error(f"Run ID {args.run_id!r} not found. Use --list-runs to inspect the file.")
    plot_run(runs[args.run_id], args.output)


if __name__ == "__main__":
    main()
