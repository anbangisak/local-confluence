#!/usr/bin/env python3
"""Generate an HTML sprint report from raw sprint-notes text.

See ../SKILL.md for the full input format, usage examples, and conventions.

Usage:
    python3 generate_report.py --input notes.txt --out reports/sprint-17.html \
        [--owner Guna] [--hours-per-sp 6] [--images chart1.png chart2.png ...]

The input text may also be piped via stdin instead of --input.
"""
import argparse
import html
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sprint_parser import parse_sprint_notes  # noqa: E402

# Statuses meaning the work is fully done (development + closure); rendered as a
# plain past-tense deliverable statement with no status suffix.
DONE_STATUSES = {"done", "dev completed", "devcompleted", "completed", "closed"}
# Statuses meaning dev is finished but the deliverable isn't fully closed out yet;
# still phrased as a past-tense deliverable, with a short suffix noting the state.
REVIEW_STATUSES = {"inreview", "in review", "pending review", "in-review"}
# Statuses meaning the work is still ongoing; the description is left in its
# original (imperative) form since nothing is "done" to report yet.
IN_PROGRESS_STATUSES = {"inprogress", "in progress", "in-progress", "ongoing"}

# Common task-description verbs seen in sprint notes. Only the leading word is
# converted to past tense when it matches one of these, to avoid mangling
# descriptions that start with a noun (e.g. "Pipeline migration to ...").
KNOWN_VERBS = {
    "implement", "remediate", "rotate", "investigate", "explore", "define",
    "validate", "migrate", "fix", "resolve", "create", "update", "add", "build",
    "configure", "setup", "deploy", "test", "review", "document", "automate",
    "integrate", "onboard", "enable", "disable", "refactor", "optimize",
    "monitor", "clean", "audit", "provision", "persist", "design", "develop",
    "analyze", "debug", "upgrade", "patch", "complete", "finalize",
}

LEADING_ANNOTATION_RE = re.compile(r"^((?:[\(\[][^\)\]]*[\)\]]\s*)+)")
LEADING_LABEL_RE = re.compile(r"^([A-Za-z][\w /]{0,40}):\s+(?=[A-Z])")
FIRST_WORD_RE = re.compile(r"^([A-Za-z]+)\b(.*)$", re.DOTALL)


def past_tense(verb):
    """Best-effort regular past-tense conversion (Implement -> Implemented)."""
    lower = verb.lower()
    if lower.endswith("e"):
        past = verb + "d"
    elif len(lower) > 1 and lower[-1] == "y" and lower[-2] not in "aeiou":
        past = verb[:-1] + "ied"
    else:
        past = verb + "ed"
    return past


def phrase_deliverable(description, status):
    """Turn a raw task description + status into a natural deliverable statement
    (no ticket id, no raw status code) for the Key Deliverables table.
    """
    description = description.strip()
    status_key = status.strip().lower()

    annotation = ""
    rest = description
    m = LEADING_ANNOTATION_RE.match(description)
    if m:
        annotation = m.group(1).strip() + " "
        rest = description[m.end():]

    # Only treat "<label>: " as a strippable prefix when the leading word is NOT
    # already a known verb (otherwise phrases like "Remediate vulnerability: CVE-x"
    # would be mistaken for a label and the verb would never get past-tensed).
    wm = FIRST_WORD_RE.match(rest)
    if not (wm and wm.group(1).lower() in KNOWN_VERBS):
        lm = LEADING_LABEL_RE.match(rest)
        if lm:
            annotation += lm.group(1).strip() + ": "
            rest = rest[lm.end():]

    if status_key in IN_PROGRESS_STATUSES:
        return f"{annotation}{rest} (in progress)".strip()

    wm = FIRST_WORD_RE.match(rest)
    if wm and wm.group(1).lower() in KNOWN_VERBS:
        rest = past_tense(wm.group(1)) + wm.group(2)

    if status_key in REVIEW_STATUSES:
        return f"{annotation}{rest} (in review)".strip()

    # Default/DONE_STATUSES/unrecognized statuses: plain completed deliverable statement.
    return f"{annotation}{rest}".strip()


def render_deliverables_rows(components):
    rows = []
    for component, tasks in components.items():
        items = "".join(
            f"<li>{html.escape(phrase_deliverable(t['description'], t['status']))}</li>"
            for t in tasks
        )
        rows.append(
            f"<tr><td>{html.escape(component)}</td><td><ul>{items}</ul></td></tr>"
        )
    return "\n".join(rows)


def render_metrics_images(image_names):
    if not image_names:
        return "<p><em>No sprint metrics images provided for this sprint.</em></p>"
    return "\n".join(
        f'<img src="{html.escape(name)}" alt="Sprint metrics chart">' for name in image_names
    )


def copy_images(image_paths, out_html_path):
    """Copy images next to the output HTML into an '<name>_assets' folder.

    Images that already live inside the target assets folder (e.g. charts written
    there directly by generate_charts.py) are referenced in place rather than copied
    again, to avoid duplicate files.

    Returns the list of relative filenames (as used in the HTML <img src>).
    """
    if not image_paths:
        return []
    out_dir = os.path.dirname(os.path.abspath(out_html_path)) or "."
    base_name = os.path.splitext(os.path.basename(out_html_path))[0]
    assets_dir = os.path.join(out_dir, f"{base_name}_assets")
    os.makedirs(assets_dir, exist_ok=True)
    assets_dir_abs = os.path.abspath(assets_dir)

    relative_names = []
    for idx, src in enumerate(image_paths, start=1):
        src_abs = os.path.abspath(src)
        if os.path.dirname(src_abs) == assets_dir_abs:
            # Already in place (e.g. generated directly into the assets folder).
            relative_names.append(f"{base_name}_assets/{os.path.basename(src_abs)}")
            continue
        ext = os.path.splitext(src)[1] or ".png"
        dest_name = f"metric-{idx}{ext}"
        dest_path = os.path.join(assets_dir, dest_name)
        shutil.copyfile(src, dest_path)
        relative_names.append(f"{base_name}_assets/{dest_name}")
    return relative_names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Path to a text file with the raw sprint notes. Defaults to stdin.")
    parser.add_argument("--out", required=True, help="Path to write the generated HTML report.")
    parser.add_argument("--owner", default="Guna", help="Name shown in the 'Product - Data (<owner>)' column header.")
    parser.add_argument("--hours-per-sp", type=float, default=6.0, help="Hours represented by one story point (default: 6).")
    parser.add_argument("--images", nargs="*", default=[], help="Paths to sprint metrics chart images to embed.")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    data = parse_sprint_notes(text)

    planned_sp = float(data["planned_sp"] or 0)
    actual_sp = float(data["actual_sp"] or 0)

    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "report_template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    image_names = copy_images(args.images, args.out)

    output = (
        template
        .replace("{{SPRINT_ID}}", html.escape(data["sprint_id"]))
        .replace("{{DATE_RANGE}}", html.escape(data["date_range"]))
        .replace("{{OWNER}}", html.escape(args.owner))
        .replace("{{PLANNED_SP}}", f"{planned_sp:g}")
        .replace("{{PLANNED_HRS}}", f"{planned_sp * args.hours_per_sp:g}")
        .replace("{{ACTUAL_SP}}", f"{actual_sp:g}")
        .replace("{{ACTUAL_HRS}}", f"{actual_sp * args.hours_per_sp:g}")
        .replace("{{DELIVERABLES_ROWS}}", render_deliverables_rows(data["components"]))
        .replace("{{METRICS_IMAGES}}", render_metrics_images(image_names))
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"Wrote report: {args.out}")
    if image_names:
        print(f"Copied {len(image_names)} image(s) into: {os.path.dirname(image_names[0]) if image_names else ''}")


if __name__ == "__main__":
    main()
