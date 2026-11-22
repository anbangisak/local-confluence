"""Shared parser for the raw sprint-notes text format used by the sprint-report skill.

See ../SKILL.md for the full input format description.
"""
import re

SPRINT_HEADER_RE = re.compile(
    r"Sprint\s*#?\s*(?P<id>\S+?)\s*:?\s*\(\s*(?P<start>[^-]+?)\s*-\s*(?P<end>[^)]+?)\s*\)",
    re.IGNORECASE,
)
PLANNED_SP_RE = re.compile(r"Overall\s+Planned\s+StoryPoints\s*:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
ACTUAL_SP_RE = re.compile(r"Overall\s+Actual\s+StoryPoints\s*:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
DELIVERED_SP_RE = re.compile(r"Delivered\s+Story\s+Points\s*:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
# A task line starts with a numeric ticket id, e.g. "3657 - 3SP - Mangrove - ... - done"
TASK_LINE_RE = re.compile(r"^(?P<ticket>\d+)\s*-\s*(?P<sp>[\d.]+)\s*SP\s*-\s*(?P<rest>.+)$", re.IGNORECASE)


def parse_sprint_notes(text):
    """Parse the raw sprint-notes text into a structured dict.

    Returns:
        {
          "sprint_id": str, "date_range": str,
          "planned_sp": str, "actual_sp": str, "delivered_sp": str,
          "components": {component_name: [ {ticket, sp, description, status}, ... ] },
        }
    """
    data = {
        "sprint_id": "",
        "date_range": "",
        "planned_sp": "",
        "actual_sp": "",
        "delivered_sp": "",
        "components": {},
    }

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        m = SPRINT_HEADER_RE.search(line)
        if m:
            data["sprint_id"] = m.group("id")
            data["date_range"] = f"{m.group('start').strip()} - {m.group('end').strip()}"
            continue

        m = PLANNED_SP_RE.search(line)
        if m:
            data["planned_sp"] = m.group(1)
            continue

        m = ACTUAL_SP_RE.search(line)
        if m:
            data["actual_sp"] = m.group(1)
            continue

        m = DELIVERED_SP_RE.search(line)
        if m:
            data["delivered_sp"] = m.group(1)
            continue

        m = TASK_LINE_RE.match(line)
        if m:
            # rest = "<Component> - <description...> - <status>"
            parts = [p.strip() for p in m.group("rest").split(" - ")]
            component = parts[0] if parts else "General"
            status = parts[-1] if len(parts) > 1 else ""
            description = " - ".join(parts[1:-1]) if len(parts) > 2 else (parts[1] if len(parts) > 1 else "")
            data["components"].setdefault(component, []).append({
                "ticket": m.group("ticket"),
                "sp": m.group("sp"),
                "description": description,
                "status": status,
            })
            continue

        # Otherwise: an engineer name line (e.g. "Guna:" or "Selvi(1 - special, ...)") - ignored for
        # the report body since leave/engineer attribution is not part of the output template.

    if not data["actual_sp"] and data["delivered_sp"]:
        data["actual_sp"] = data["delivered_sp"]

    return data
