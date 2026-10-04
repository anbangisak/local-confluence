"""SQLite-based storage layer acting as the "database" for pages.

Pages are stored as rows in a single SQLite database under data/pages.db.
Legacy per-page JSON files (data/pages/<slug>.json) are migrated into the
database automatically the first time it is created.
"""

import glob
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pages")
DB_PATH = os.path.join(DATA_DIR, "pages.db")

# Slugs are used as primary keys and in URLs, so restrict them to a safe
# charset to prevent path traversal / injection (e.g. "../../etc/passwd").
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_lock = threading.Lock()
_initialized = False


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_conn():
    _ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        conn = _get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_favorite INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(pages)")}
            if "is_favorite" not in columns:
                conn.execute("ALTER TABLE pages ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
            conn.commit()
            _migrate_json_files(conn)
        finally:
            conn.close()
        _initialized = True


def _migrate_json_files(conn):
    """One-time import of legacy data/pages/<slug>.json files into the DB."""
    for path in glob.glob(os.path.join(DATA_DIR, "*.json")):
        slug = os.path.splitext(os.path.basename(path))[0]
        if not is_valid_slug(slug):
            continue
        existing = conn.execute("SELECT 1 FROM pages WHERE id = ?", (slug,)).fetchone()
        if existing:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                page = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        content = page.get("content")
        if content is None:
            # Migrate older append-only pages that stored a list of blocks.
            content = "\n\n".join(b["content"] for b in page.get("blocks", []))
        now = _now()
        conn.execute(
            "INSERT INTO pages (id, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                slug,
                page.get("title", slug),
                content,
                page.get("created_at", now),
                page.get("updated_at", now),
            ),
        )
    conn.commit()


def slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "page"


def is_valid_slug(slug):
    return bool(SLUG_RE.match(slug))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_page(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "is_favorite": bool(row["is_favorite"]),
    }


def list_pages():
    _init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, title, updated_at, is_favorite FROM pages ORDER BY is_favorite DESC, updated_at DESC"
        ).fetchall()
        return [
            {"id": r["id"], "title": r["title"], "updated_at": r["updated_at"], "is_favorite": bool(r["is_favorite"])}
            for r in rows
        ]
    finally:
        conn.close()


def get_page(slug):
    if not is_valid_slug(slug):
        return None
    _init_db()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM pages WHERE id = ?", (slug,)).fetchone()
        return _row_to_page(row) if row else None
    finally:
        conn.close()


def create_page(title, content):
    title = title.strip()
    if not title:
        raise ValueError("Title is required")
    _init_db()
    with _lock:
        conn = _get_conn()
        try:
            base_slug = slugify(title)
            slug = base_slug
            counter = 2
            while conn.execute("SELECT 1 FROM pages WHERE id = ?", (slug,)).fetchone():
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
            conn.execute(
                "INSERT INTO pages (id, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (page["id"], page["title"], page["content"], page["created_at"], page["updated_at"]),
            )
            conn.commit()
            return page
        finally:
            conn.close()


def update_page(slug, title, content):
    title = title.strip()
    if not title:
        raise ValueError("Title is required")
    _init_db()
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM pages WHERE id = ?", (slug,)).fetchone()
            if row is None:
                return None
            page = _row_to_page(row)
            page["title"] = title
            page["content"] = (content or "").strip()
            page["updated_at"] = _now()
            conn.execute(
                "UPDATE pages SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                (page["title"], page["content"], page["updated_at"], slug),
            )
            conn.commit()
            return page
        finally:
            conn.close()


def toggle_favorite(slug):
    if not is_valid_slug(slug):
        return None
    _init_db()
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM pages WHERE id = ?", (slug,)).fetchone()
            if row is None:
                return None
            page = _row_to_page(row)
            page["is_favorite"] = not page["is_favorite"]
            conn.execute(
                "UPDATE pages SET is_favorite = ? WHERE id = ?",
                (int(page["is_favorite"]), slug),
            )
            conn.commit()
            return page
        finally:
            conn.close()
