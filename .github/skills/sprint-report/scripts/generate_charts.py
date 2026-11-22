#!/usr/bin/env python3
"""Generate sprint metrics chart images from raw sprint-notes text.

Produces 3 PNGs matching the style of a manually-maintained sprint metrics deck:
  1. chart-status.png   - pie chart of Story Points by status for this sprint
  2. chart-component.png - bar chart of Story Points by component for this sprint
  3. chart-trend.png    - grouped bar chart of Forecast vs Actual vs Delivered SP,
                           accumulated across every sprint this script has been run for
                           (tracked in a small history CSV so the trend grows over time)

Usage:
    python3 generate_charts.py --input notes.txt --out-dir reports/sprint-17-report_assets \
        [--history reports/sprint_history.csv]

Prints the generated file paths (one per line) so they can be passed straight to
generate_report.py's --images argument.
"""
import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sprint_parser import parse_sprint_notes  # noqa: E402

# Friendly display names for the free-text statuses used in sprint notes.
STATUS_LABELS = {
    "done": "Done",
    "dev completed": "Dev Completed - In Review",
    "inreview": "In Review",
    "in review": "In Review",
    "inprogress": "In Progress",
    "in progress": "In Progress",
}


def status_label(raw_status):
    return STATUS_LABELS.get(raw_status.strip().lower(), raw_status.strip().title() or "Unknown")


def build_status_pie(data, out_path):
    totals = {}
    for tasks in data["components"].values():
        for t in tasks:
            label = status_label(t["status"])
            totals[label] = totals.get(label, 0) + float(t["sp"])

    labels = list(totals.keys())
    values = list(totals.values())

    fig, ax = plt.subplots(figsize=(6, 5))
    colors = plt.cm.Set2.colors
    ax.pie(values, labels=None, autopct=lambda pct: f"{pct * sum(values) / 100:g}", colors=colors,
           startangle=90, textprops={"fontsize": 11})
    ax.set_title(f"Sprint {data['sprint_id']}", fontsize=14)
    ax.legend(labels, loc="lower center", bbox_to_anchor=(0.5, -0.15), ncol=min(len(labels), 3), frameon=False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def build_component_bar(data, out_path):
    totals = {}
    for component, tasks in data["components"].items():
        totals[component] = sum(float(t["sp"]) for t in tasks)

    components = list(totals.keys())
    values = list(totals.values())

    fig, ax = plt.subplots(figsize=(7, 5))
    colors = plt.cm.tab10.colors
    bars = ax.bar(components, values, color=colors[: len(components)])
    ax.bar_label(bars, fmt="%g", padding=3)
    ax.set_title(f"Sprint {data['sprint_id']}", fontsize=14)
    ax.set_ylim(0, max(values) * 1.2 if values else 1)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def update_history(history_path, sprint_id, planned_sp, actual_sp, delivered_sp):
    rows = []
    if os.path.exists(history_path):
        with open(history_path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    rows = [r for r in rows if r["sprint_id"] != str(sprint_id)]
    rows.append({
        "sprint_id": str(sprint_id),
        "planned_sp": str(planned_sp),
        "actual_sp": str(actual_sp),
        "delivered_sp": str(delivered_sp),
    })

    def sort_key(r):
        try:
            return (0, int(r["sprint_id"]))
        except ValueError:
            return (1, r["sprint_id"])

    rows.sort(key=sort_key)

    os.makedirs(os.path.dirname(os.path.abspath(history_path)) or ".", exist_ok=True)
    with open(history_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["sprint_id", "planned_sp", "actual_sp", "delivered_sp"])
        writer.writeheader()
        writer.writerows(rows)

    return rows


def build_trend_chart(rows, out_path):
    sprint_labels = [f"Sprint {r['sprint_id']}" for r in rows]
    planned = [float(r["planned_sp"]) for r in rows]
    actual = [float(r["actual_sp"]) for r in rows]
    delivered = [float(r["delivered_sp"]) for r in rows]

    x = range(len(rows))
    width = 0.25

    fig, ax = plt.subplots(figsize=(max(7, len(rows) * 1.1), 5))
    b1 = ax.bar([i - width for i in x], planned, width, label="Forecast Capacity", color="#1f77b4")
    b2 = ax.bar(list(x), actual, width, label="Actual Capacity", color="#ff7f0e")
    b3 = ax.bar([i + width for i in x], delivered, width, label="Delivered", color="#2ca02c")
    for bars in (b1, b2, b3):
        ax.bar_label(bars, fmt="%g", padding=2, fontsize=8)

    ax.set_title("Forecast Vs Actual Vs Delivered (SP)", fontsize=14)
    ax.set_xticks(list(x))
    ax.set_xticklabels(sprint_labels)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Path to a text file with the raw sprint notes. Defaults to stdin.")
    parser.add_argument("--out-dir", required=True, help="Directory to write the generated chart PNGs into.")
    parser.add_argument("--history", default=None,
                         help="CSV file tracking planned/actual/delivered SP per sprint, used for the trend "
                              "chart. Defaults to '<out-dir>/../sprint_history.csv'.")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    data = parse_sprint_notes(text)
    os.makedirs(args.out_dir, exist_ok=True)

    history_path = args.history or os.path.join(args.out_dir, "..", "sprint_history.csv")

    status_path = os.path.join(args.out_dir, "chart-status.png")
    component_path = os.path.join(args.out_dir, "chart-component.png")
    trend_path = os.path.join(args.out_dir, "chart-trend.png")

    build_status_pie(data, status_path)
    build_component_bar(data, component_path)
    rows = update_history(
        history_path,
        data["sprint_id"],
        data["planned_sp"] or 0,
        data["actual_sp"] or 0,
        data["delivered_sp"] or data["actual_sp"] or 0,
    )
    build_trend_chart(rows, trend_path)

    for p in (status_path, component_path, trend_path):
        print(p)


if __name__ == "__main__":
    main()
