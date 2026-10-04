"""File-based storage layer acting as the "database" for pages.

Each page is stored as a single JSON file under data/pages/<slug>.json,
holding a title and its Markdown content, which can be edited in place.
"""

import json
import os
import re
import threading
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pages")

# Slugs are used directly as filenames, so restrict them to a safe charset
# to prevent path traversal (e.g. "../../etc/passwd").
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_lock = threading.Lock()


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "page"


def is_valid_slug(slug):
    return bool(SLUG_RE.match(slug))


def _page_path(slug):
    return os.path.join(DATA_DIR, f"{slug}.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write_page(page):
    path = _page_path(page["id"])
    tmp_path = f"{path}.tmp"
    # Write to a temp file then atomically replace, avoiding a partially
    # written/corrupted page file if the process is interrupted.
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(page, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def list_pages():
    _ensure_data_dir()
    pages = []
    for name in os.listdir(DATA_DIR):
        if not name.endswith(".json"):
            continue
        page = get_page(name[:-5])
        if page:
            pages.append({"id": page["id"], "title": page["title"], "updated_at": page["updated_at"]})
    pages.sort(key=lambda p: p["updated_at"], reverse=True)
    return pages


def get_page(slug):
    if not is_valid_slug(slug):
        return None
    path = _page_path(slug)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        page = json.load(f)
    if "content" not in page:
        # Migrate older append-only pages that stored a list of blocks.
        page["content"] = "\n\n".join(b["content"] for b in page.get("blocks", []))
    return page


def create_page(title, content):
    title = title.strip()
    if not title:
        raise ValueError("Title is required")
    _ensure_data_dir()
    with _lock:
        base_slug = slugify(title)
        slug = base_slug
        counter = 2
        while os.path.isfile(_page_path(slug)):
            slug = f"{base_slug}-{counter}"
            counter += 1
        now = _now()
        page = {
            "id": slug,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "content": (content or "").strip(),
        }
        _write_page(page)
        return page


def update_page(slug, title, content):
    title = title.strip()
    if not title:
        raise ValueError("Title is required")
    with _lock:
        page = get_page(slug)
        if page is None:
            return None
        page["title"] = title
        page["content"] = (content or "").strip()
        page["updated_at"] = _now()
        page.pop("blocks", None)
        _write_page(page)
        return page
