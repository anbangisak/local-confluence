---
name: sprint-report
description: 'Convert raw sprint stand-up notes (team member task lists with ticket IDs, story points, components, and statuses, plus sprint metrics chart screenshots) into a formatted HTML sprint report email. Use when asked to create a sprint report, sprint summary, sprint update, "PFB the sprint report", or convert sprint notes/Jira export into HTML for Confluence or email.'
argument-hint: '[paste sprint notes text, optionally with chart images attached]'
---

# Sprint Report Generator

Converts the raw sprint notes format used for Sprint planning/retro summaries into
a polished HTML report (greeting, summary metrics table, Key Deliverables table
grouped by component, and embedded sprint metrics charts).

## When to Use

- The user pastes sprint notes in the format shown under "Input Format" below and
  asks for a sprint report, sprint summary, or "HTML output" of it.
- The user attaches 1 or more sprint metrics chart images (pie/bar charts) alongside
  the notes for the **current sprint only** — do not reuse chart images from a
  previous invocation/sprint.
- If no images are attached (or the user asks to generate the charts), use
  [scripts/generate_charts.py](./scripts/generate_charts.py) to produce them
  directly from the sprint notes instead of leaving the Sprint Metrics section
  empty.

## Input Format

```
Sprint#<id>:(<start date> - <end date>)
Overall Planned StoryPoints: <number>
Overall Actual StoryPoints: <number>
Delivered Story Points: <number>
<Engineer Name>(<optional leave notes>):
<ticket> - <N>SP - <Component> - <description> - <status>
<ticket> - <N>SP - <Component> - <description> - <status>
<Engineer Name>:
...
```

See a full example in [references/example-input.txt](./references/example-input.txt)
and its rendered result in [references/example-output.html](./references/example-output.html).

## Procedure

1. Save the user's pasted sprint notes text to a temp file (e.g. `/tmp/sprint-notes.txt`),
   preserving line breaks exactly as given.
2. Decide on images for the Sprint Metrics section:
   - **If the user attached chart images** for this sprint, use their file paths directly.
   - **If no images were attached** (or the user asks you to create/generate them),
     run [scripts/generate_charts.py](./scripts/generate_charts.py) to build them
     from the parsed notes:

     ```bash
     python3 .github/skills/sprint-report/scripts/generate_charts.py \
       --input /tmp/sprint-notes.txt \
       --out-dir reports/sprint-<id>-report_assets \
       --history reports/sprint_history.csv
     ```

     This writes 3 PNGs into `--out-dir` and prints their paths:
     - `chart-status.png` — pie chart of Story Points by status for this sprint.
     - `chart-component.png` — bar chart of Story Points by component for this sprint.
     - `chart-trend.png` — grouped bar chart of Forecast vs Actual vs Delivered SP,
       accumulated across every sprint ever run through this script (tracked in
       `--history`, a small CSV keyed by `sprint_id` — commit this file so the trend
       keeps growing sprint over sprint).
3. Run [scripts/generate_report.py](./scripts/generate_report.py):

   ```bash
   python3 .github/skills/sprint-report/scripts/generate_report.py \
     --input /tmp/sprint-notes.txt \
     --out reports/sprint-<id>-report.html \
     --owner <name, default "Guna"> \
     --images <path1> <path2> <path3>
   ```

   - `--out` defaults to this repo's `reports/` folder; create it if missing
     (the script does this automatically via `os.makedirs`).
   - `--owner` is the name shown in the "Product – Data (<owner>)" column header —
     this is the report preparer, default `Guna`. Ask the user if unclear.
   - `--images` is optional; omit it if there are no charts at all. Pass either the
     user-attached images or the `chart-*.png` files from step 2. Images already
     inside the `<report-name>_assets/` folder (e.g. generated charts) are referenced
     in place; any other image path is copied into that folder so the HTML stays
     portable alongside its assets.
   - `--hours-per-sp` defaults to `6` (1 story point = 6 hours), matching the
     reference reports. Override only if the user states a different conversion.
4. Show the user the generated HTML file path and a short summary of what was
   produced (sprint id, date range, number of components, number of images embedded).
5. Open or print the HTML content back to the user if they ask to see it inline.

## Parsing Rules (for reference / troubleshooting)

- `Sprint#<id>:(<start> - <end>)` → sprint id and date range.
- `Overall Planned StoryPoints: <n>` → "Planned forecasted SP's / days".
- `Overall Actual StoryPoints: <n>` → "Actual SP's / days" (falls back to
  `Delivered Story Points` if "Actual" is missing).
- Capacity in hours = story points × `--hours-per-sp` (default 6).
- A task line always starts with a numeric ticket id followed by
  ` - <N>SP - <Component> - <description> - <status>`. The component name is
  everything between the SP value and the next ` - `; the status is the final
  ` - `-delimited segment.
- Engineer name lines (e.g. `Guna:` or `Selvi(1 - special, 1 - casual)`) are
  used only to detect where one engineer's tasks end and the next begin — leave
  details are not included in the report output.
- The Key Deliverables table groups all tasks from all engineers by `Component`,
  regardless of who worked on them.
- Each deliverable is rendered via `phrase_deliverable()` in
  [scripts/generate_report.py](./scripts/generate_report.py), **not** as a raw
  `<ticket> - <description> (<status>)` line:
  - The ticket id and SP are dropped entirely — only the technical description
    is shown (e.g. `3918 - 2SP - Mangrove - Rotate credentials ... - done` →
    "Rotated credentials for sdh service user across Preprod and Prod environments").
  - For completed statuses (`done`, `dev completed`, etc.) the leading verb is
    converted to past tense (`Implement` → `Implemented`) when it's a recognized
    verb (see `KNOWN_VERBS`); a leading `(continued)`/`[Analysis]` annotation or
    an `E2E Testing:`-style label is preserved before the verb conversion.
  - `inReview`-style statuses keep the past-tense phrasing with an `(in review)`
    suffix; `Inprogress`-style statuses keep the original imperative wording with
    an `(in progress)` suffix (never claimed as completed).

## Notes / Assumptions

- The 1 SP = 6 hours conversion was derived from the user's own example
  (33 SP → 198 hrs). Confirm with the user if a sprint's numbers look off.
- When user-provided images exist for the current sprint, prefer those over
  generating new ones — only auto-generate charts when asked to or when none
  were attached.
- Status labels in generated charts are normalized via `STATUS_LABELS` in
  [scripts/generate_charts.py](./scripts/generate_charts.py) (e.g. `dev completed`
  → "Dev Completed - In Review"). Extend that mapping if new status strings appear.
- The trend chart's history file (`reports/sprint_history.csv` by default) is
  keyed by `sprint_id` and upserted on each run, so re-running for the same
  sprint updates its entry rather than duplicating it.
- Past-tense verb conversion only fires on a recognized leading verb (`KNOWN_VERBS`
  in `generate_report.py`); descriptions starting with a free-text label joined by
  ` - ` (e.g. `HP Anyware - Migrate credentials...`) are left in their original
  wording since that prefix can't be reliably distinguished from a verb-first
  sentence. Add more verbs to `KNOWN_VERBS` as new ones show up in practice.
