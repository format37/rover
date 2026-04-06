#!/usr/bin/env python3
"""Visualize detected objects and their confidences over time from a session."""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np


def parse_timestamp(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y%m%d_%H%M%S_%f")


def load_detections(session_dir: str):
    jsonl = Path(session_dir) / "yolo" / "detections.jsonl"
    if not jsonl.exists():
        sys.exit(f"Not found: {jsonl}")

    records = []
    with open(jsonl) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def main():
    session_dir = sys.argv[1] if len(sys.argv) > 1 else "sessions/20260405_115449"
    records = load_detections(session_dir)

    # Collect per-label time series: {label: [(time, confidence), ...]}
    label_series = defaultdict(list)
    state_series = []  # [(time, state)]

    for rec in records:
        ts = parse_timestamp(rec["timestamp"])
        state_series.append((ts, rec.get("state", "")))
        for det in rec.get("detections", []):
            label_series[det["label"]].append((ts, det["confidence"]))

    if not label_series:
        sys.exit("No detections found in session.")

    # Sort labels by number of detections (most frequent first)
    sorted_labels = sorted(label_series.keys(), key=lambda l: -len(label_series[l]))

    # Color map
    cmap = plt.cm.tab10
    colors = {label: cmap(i) for i, label in enumerate(sorted_labels)}

    # State colors for background bands
    state_colors = {
        "tracking": "#d4edda",
        "lost": "#f8d7da",
        "searching": "#fff3cd",
        "orienting": "#cce5ff",
    }

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(16, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05},
    )

    # --- Top: confidence scatter per label ---
    for label in sorted_labels:
        times, confs = zip(*label_series[label])
        ax1.scatter(
            times, confs,
            label=f"{label} ({len(confs)})",
            color=colors[label],
            alpha=0.6, s=18, edgecolors="none",
        )

    # Draw state background bands on top plot
    if state_series:
        t0, s0 = state_series[0]
        for t, s in state_series[1:]:
            if s != s0:
                c = state_colors.get(s0, "#f0f0f0")
                ax1.axvspan(t0, t, alpha=0.15, color=c, linewidth=0)
                t0, s0 = t, s
        c = state_colors.get(s0, "#f0f0f0")
        ax1.axvspan(t0, state_series[-1][0], alpha=0.15, color=c, linewidth=0)

    ax1.set_ylabel("Confidence")
    ax1.set_ylim(0, 1.05)
    ax1.legend(loc="upper right", fontsize=8, ncol=2, framealpha=0.9)
    ax1.set_title(f"Detections over time — {Path(session_dir).name}")
    ax1.grid(axis="y", alpha=0.3)

    # --- Bottom: state timeline ---
    state_map = {"searching": 0, "lost": 1, "orienting": 2, "tracking": 3}
    state_labels = ["searching", "lost", "orienting", "tracking"]

    if state_series:
        times_s, states_s = zip(*state_series)
        numeric_states = [state_map.get(s, -1) for s in states_s]
        ax2.fill_between(
            times_s, numeric_states,
            step="post", alpha=0.5, color="#6c757d",
        )
        ax2.step(times_s, numeric_states, where="post", color="#343a40", linewidth=0.8)

    ax2.set_yticks(list(state_map.values()))
    ax2.set_yticklabels(state_labels, fontsize=9)
    ax2.set_ylim(-0.5, 3.5)
    ax2.set_ylabel("State")
    ax2.set_xlabel("Time")
    ax2.grid(axis="y", alpha=0.3)

    # Format x-axis
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate(rotation=30)

    # State legend
    patches = [
        plt.Rectangle((0, 0), 1, 1, fc=c, alpha=0.3)
        for c in state_colors.values()
    ]
    ax1.legend(
        ax1.get_legend_handles_labels()[0] + patches,
        [h.get_label() for h in ax1.get_legend_handles_labels()[0]] + list(state_colors.keys()),
        loc="upper right", fontsize=8, ncol=3, framealpha=0.9,
    )

    plt.tight_layout()
    out = Path(session_dir) / "detections_timeline.png"
    fig.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    main()
