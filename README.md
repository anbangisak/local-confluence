# Local Confluence

A tiny self-hosted, Confluence-style wiki. Pages are stored as JSON files on
disk (no external database), each page can be created and edited in place,
and a sidebar lists all pages for quick navigation.

## Features

- Create pages with Markdown content
- Edit an existing page's title and content
- Sidebar listing all pages, sorted by most recently updated
- Markdown rendering, sanitized to prevent XSS
- Split code/preview editor with live Markdown preview
- CMS-style editor with a Visual (WYSIWYG) mode and the original Markdown mode:
  headings, bold/italic, inline code, code blocks, quotes, lists/indent, links,
  images (upload or paste), horizontal rules, tables with row/column add/delete
  (Tab moves between cells), undo/redo, full screen, word count, Ctrl+S to save,
  and an unsaved-changes warning. Content is always stored as Markdown.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe app.py
```

Then open http://127.0.0.1:5000 in your browser.

## Storage

Pages live under `data/pages/<slug>.json`. Deleting a file removes the page.
There's no external DB — it's all plain files, making it easy to back up,
sync, or version with git.
