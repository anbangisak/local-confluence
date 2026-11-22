// CMS-style rich text editor with a Visual (WYSIWYG) mode and the original Markdown mode.
// Markdown stays the storage format: the hidden-or-visible #content textarea is always what gets submitted.
function initCmsEditor({ textareaId, editorId }) {
  const root = document.getElementById(editorId);
  const textarea = document.getElementById(textareaId);
  if (!root || !textarea) return;

  const form = textarea.form;
  const surface = root.querySelector("#cms-surface");
  const toolbar = root.querySelector("#cms-toolbar");
  const tableTools = root.querySelector("#cms-table-tools");
  const imageInput = root.querySelector("#cms-image-input");
  const visualPane = root.querySelector("#cms-visual-pane");
  const markdownPane = root.querySelector("#cms-markdown-pane");
  const countEl = root.querySelector("#cms-count");
  const messageEl = root.querySelector("#cms-message");
  const fullscreenBtn = root.querySelector("#cms-fullscreen");
  const tabs = root.querySelectorAll(".cms-tab");

  const MODE_KEY = "cms-editor-mode";
  const MAX_ROWS = 50;
  const MAX_COLS = 12;
  const BLOCKS = [
    ["p", "Paragraph"],
    ["h1", "Heading 1"],
    ["h2", "Heading 2"],
    ["h3", "Heading 3"],
    ["h4", "Heading 4"],
    ["blockquote", "Quote"],
    ["pre", "Code block"],
  ];
  const BLOCK_TAGS = new Set(BLOCKS.map(([tag]) => tag.toUpperCase()));

  let mode = "visual";
  let visualReady = false; // surface holds the rendered content (guards against overwriting it with an empty surface)
  let visualDirty = false; // surface edited since it was loaded / last converted
  let dirty = false;
  let submitting = false;
  let savedRange = null;

  try {
    document.execCommand("defaultParagraphSeparator", false, "p");
  } catch (e) {
    /* not supported: browser default separator is used */
  }

  // ---------- helpers ----------
  function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function say(text) {
    messageEl.textContent = text || "";
  }

  function closestIn(node, selector) {
    const el = node && node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    const found = el && el.closest ? el.closest(selector) : null;
    return found && surface.contains(found) ? found : null;
  }

  function selectionInSurface() {
    const sel = window.getSelection();
    return sel && sel.rangeCount > 0 && surface.contains(sel.anchorNode);
  }

  function restoreSelection() {
    surface.focus();
    if (savedRange) {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(savedRange);
    }
  }

  function markChanged() {
    visualDirty = true;
    dirty = true;
    updateCount();
  }

  function exec(command, value) {
    restoreSelection();
    document.execCommand(command, false, value);
    markChanged();
    refreshState();
  }

  function insertHtml(html) {
    restoreSelection();
    document.execCommand("insertHTML", false, html);
    markChanged();
    refreshState();
  }

  function normalizeUrl(raw) {
    const url = raw.trim();
    if (!url) return null;
    if (/^(https?:|mailto:)/i.test(url) || /^[/#]/.test(url)) return url;
    if (/^[a-z][a-z0-9+.-]*:/i.test(url)) return null; // blocks javascript:, data:, etc.
    return "https://" + url;
  }

  function renderMarkdown(markdown) {
    return fetch("/preview", { method: "POST", body: new URLSearchParams({ content: markdown }) }).then((res) => {
      if (!res.ok) throw new Error("Preview failed");
      return res.text();
    });
  }

  // ---------- HTML -> Markdown ----------
  const turndown = new TurndownService({
    headingStyle: "atx",
    codeBlockStyle: "fenced",
    bulletListMarker: "-",
    emDelimiter: "*",
    hr: "---",
  });
  turndown.use(turndownPluginGfm.tables);
  turndown.addRule("preBlock", {
    filter: "pre",
    replacement: (_content, node) => "\n\n```\n" + node.textContent.replace(/\n$/, "") + "\n```\n\n",
  });
  turndown.addRule("responsiveTableWrapper", {
    filter: (node) => node.nodeName === "DIV" && node.classList.contains("table-responsive"),
    replacement: (content) => "\n\n" + content.trim() + "\n\n",
  });

  function toMarkdown() {
    const clone = surface.cloneNode(true);
    clone.querySelectorAll("td, th").forEach((cell) => {
      if (!cell.textContent.trim() && !cell.querySelector("img")) cell.textContent = "";
    });
    return turndown.turndown(clone).replace(/\n{3,}/g, "\n\n").trim() + "\n";
  }

  // ---------- mode switching ----------
  function loadVisual() {
    say("Loading...");
    return renderMarkdown(textarea.value)
      .then((html) => {
        surface.innerHTML = html.trim() || "<p><br></p>";
        visualReady = true;
        visualDirty = false;
        say("");
        updateCount();
        return true;
      })
      .catch(() => {
        say("Visual editor unavailable; use Markdown mode.");
        return false;
      });
  }

  function syncToTextarea() {
    if (mode === "visual" && visualReady && visualDirty) {
      textarea.value = toMarkdown();
      visualDirty = false;
      textarea.dispatchEvent(new Event("input"));
    }
  }

  function setMode(next) {
    if (next === mode && (next !== "visual" || visualReady)) return;
    if (next === "markdown") {
      syncToTextarea();
      mode = "markdown";
      applyMode();
      return;
    }
    loadVisual().then((ok) => {
      mode = ok ? "visual" : "markdown";
      applyMode();
    });
  }

  function applyMode() {
    visualPane.hidden = mode !== "visual";
    markdownPane.hidden = mode !== "markdown";
    tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.mode === mode));
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch (e) {
      /* storage unavailable */
    }
    updateCount();
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.mode)));

  // ---------- toolbar ----------
  function makeButton(label, title, onClick, extraClass) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cms-btn" + (extraClass ? " " + extraClass : "");
    btn.innerHTML = label;
    btn.title = title;
    btn.addEventListener("mousedown", (event) => event.preventDefault()); // keep the editor selection
    btn.addEventListener("click", onClick);
    return btn;
  }

  function addSeparator(parent) {
    const sep = document.createElement("span");
    sep.className = "cms-sep";
    parent.appendChild(sep);
  }

  const stateButtons = [];
  function addCommand(cmd, label, title, extraClass) {
    const btn = makeButton(label, title, () => exec(cmd), extraClass);
    btn.dataset.cmd = cmd;
    toolbar.appendChild(btn);
    stateButtons.push(btn);
    return btn;
  }

  addCommand("undo", "↶", "Undo (Ctrl+Z)");
  addCommand("redo", "↷", "Redo (Ctrl+Y)");
  addSeparator(toolbar);

  const blockSelect = document.createElement("select");
  blockSelect.className = "cms-select";
  blockSelect.title = "Text style";
  BLOCKS.forEach(([tag, label]) => blockSelect.add(new Option(label, tag)));
  blockSelect.addEventListener("change", () => {
    exec("formatBlock", `<${blockSelect.value}>`);
  });
  toolbar.appendChild(blockSelect);
  addSeparator(toolbar);

  addCommand("bold", "<b>B</b>", "Bold (Ctrl+B)");
  addCommand("italic", "<i>I</i>", "Italic (Ctrl+I)");
  toolbar.appendChild(makeButton("&lt;/&gt;", "Inline code", toggleInlineCode, ""));
  addSeparator(toolbar);

  addCommand("insertUnorderedList", "• List", "Bulleted list");
  addCommand("insertOrderedList", "1. List", "Numbered list");
  addCommand("outdent", "⇤", "Decrease indent");
  addCommand("indent", "⇥", "Increase indent");
  addSeparator(toolbar);

  toolbar.appendChild(makeButton("🔗 Link", "Insert / edit link (Ctrl+K)", insertLink));
  toolbar.appendChild(makeButton("Unlink", "Remove link", () => exec("unlink")));
  toolbar.appendChild(makeButton("🖼 Image", "Insert image", () => imageInput.click()));
  toolbar.appendChild(makeButton("―", "Horizontal rule", () => exec("insertHorizontalRule")));
  addSeparator(toolbar);

  // Table insertion panel
  const tablePanel = document.createElement("span");
  tablePanel.className = "cms-table-insert";
  tablePanel.innerHTML = `
    <button type="button" class="cms-btn cms-table-toggle" title="Insert table">▦ Table</button>
    <span class="cms-table-panel" hidden>
      <label>Rows <input type="number" class="cms-rows" min="1" max="${MAX_ROWS}" value="3"></label>
      <label>Cols <input type="number" class="cms-cols" min="1" max="${MAX_COLS}" value="3"></label>
      <button type="button" class="btn btn-sm cms-table-go">Insert</button>
    </span>`;
  toolbar.appendChild(tablePanel);
  const tableToggle = tablePanel.querySelector(".cms-table-toggle");
  const tableBox = tablePanel.querySelector(".cms-table-panel");
  const rowsInput = tablePanel.querySelector(".cms-rows");
  const colsInput = tablePanel.querySelector(".cms-cols");
  tableToggle.addEventListener("mousedown", (event) => event.preventDefault());
  tableToggle.addEventListener("click", () => {
    tableBox.hidden = !tableBox.hidden;
    if (!tableBox.hidden) rowsInput.focus();
  });
  tablePanel.querySelector(".cms-table-go").addEventListener("click", insertTable);
  [rowsInput, colsInput].forEach((input) =>
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        insertTable();
      }
    })
  );

  addSeparator(toolbar);
  toolbar.appendChild(makeButton("Clear format", "Remove inline formatting", () => exec("removeFormat")));

  // ---------- actions ----------
  function toggleInlineCode() {
    restoreSelection();
    const sel = window.getSelection();
    if (!sel.rangeCount) return;
    const existing = closestIn(sel.anchorNode, "code");
    if (existing && !closestIn(existing, "pre")) {
      existing.replaceWith(document.createTextNode(existing.textContent));
      markChanged();
      return;
    }
    const text = sel.toString();
    if (!text || text.includes("\n")) return;
    insertHtml(`<code>${escapeHtml(text)}</code>`);
  }

  function insertLink() {
    restoreSelection();
    const sel = window.getSelection();
    if (!sel.rangeCount) return;
    const existing = closestIn(sel.anchorNode, "a");
    const raw = window.prompt("Link URL", existing ? existing.getAttribute("href") : "https://");
    if (raw === null) return;
    const url = normalizeUrl(raw);
    if (!url) {
      say("That link type is not supported.");
      return;
    }
    say("");
    if (sel.isCollapsed && !existing) {
      insertHtml(`<a href="${escapeHtml(url)}">${escapeHtml(url)}</a>`);
    } else {
      exec("createLink", url);
    }
  }

  function uploadImage(file) {
    say("Uploading...");
    const formData = new FormData();
    formData.append("image", file, file.name);
    fetch("/upload-image", { method: "POST", body: formData })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Upload failed");
        insertHtml(`<img src="${escapeHtml(data.url)}" alt="${escapeHtml(file.name)}">`);
        say("");
      })
      .catch((err) => say(err.message));
  }

  imageInput.addEventListener("change", () => {
    if (imageInput.files[0]) uploadImage(imageInput.files[0]);
    imageInput.value = "";
  });

  surface.addEventListener("paste", (event) => {
    const items = event.clipboardData ? event.clipboardData.items : [];
    for (const item of items) {
      if (!item.type.startsWith("image/")) continue;
      const blob = item.getAsFile();
      if (!blob) continue;
      event.preventDefault();
      const ext = item.type.split("/")[1].replace("jpeg", "jpg");
      uploadImage(new File([blob], `pasted-image-${Date.now()}.${ext}`, { type: item.type }));
      return;
    }
  });

  // ---------- tables ----------
  function clamp(value, max) {
    const n = parseInt(value, 10);
    return Math.min(Math.max(Number.isNaN(n) ? 1 : n, 1), max);
  }

  function insertTable() {
    const rows = clamp(rowsInput.value, MAX_ROWS);
    const cols = clamp(colsInput.value, MAX_COLS);
    const head = Array.from({ length: cols }, (_, i) => `<th>Header ${i + 1}</th>`).join("");
    const body = Array.from({ length: rows }, () => `<tr>${"<td><br></td>".repeat(cols)}</tr>`).join("");
    const html =
      `<table class="table table-bordered table-striped table-hover" data-new="1">` +
      `<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table><p><br></p>`;

    restoreSelection();
    const cell = savedRange ? closestIn(savedRange.startContainer, "td, th") : null;
    if (cell) {
      // Never nest tables: insert after the table the caret is in.
      const table = cell.closest("table");
      const range = document.createRange();
      range.setStartAfter(table.parentElement.classList.contains("table-responsive") ? table.parentElement : table);
      range.collapse(true);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      savedRange = range;
    }
    insertHtml(html);
    tableBox.hidden = true;
    const fresh = surface.querySelector("table[data-new]");
    if (fresh) {
      fresh.removeAttribute("data-new");
      const first = fresh.querySelector("th");
      const range = document.createRange();
      range.selectNodeContents(first);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      refreshState();
    }
  }

  function currentCell() {
    const sel = window.getSelection();
    return sel && sel.rangeCount && selectionInSurface() ? closestIn(sel.anchorNode, "td, th") : null;
  }

  function newCell(inHead) {
    const cell = document.createElement(inHead ? "th" : "td");
    cell.innerHTML = inHead ? "Header" : "<br>";
    return cell;
  }

  function focusCell(cell) {
    if (!cell) return;
    const range = document.createRange();
    range.selectNodeContents(cell);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    savedRange = range;
  }

  function tableAction(action) {
    restoreSelection();
    const cell = currentCell();
    if (!cell) return;
    const row = cell.parentElement;
    const table = cell.closest("table");
    const inHead = row.parentElement.tagName === "THEAD";
    const index = cell.cellIndex;
    const cols = row.cells.length;

    if (action === "row-above" || action === "row-below") {
      if (inHead && action === "row-above") return;
      const fresh = document.createElement("tr");
      for (let i = 0; i < cols; i++) fresh.appendChild(newCell(false));
      if (inHead) {
        let tbody = table.tBodies[0];
        if (!tbody) tbody = table.appendChild(document.createElement("tbody"));
        tbody.insertBefore(fresh, tbody.firstChild);
      } else {
        row.parentElement.insertBefore(fresh, action === "row-above" ? row : row.nextSibling);
      }
      focusCell(fresh.cells[Math.min(index, fresh.cells.length - 1)]);
    } else if (action === "row-delete") {
      if (inHead) {
        say("The header row can't be deleted.");
        return;
      }
      const next = row.nextElementSibling || row.previousElementSibling || table.tHead.rows[0];
      row.remove();
      focusCell(next.cells[Math.min(index, next.cells.length - 1)]);
    } else if (action === "col-left" || action === "col-right") {
      const at = action === "col-left" ? index : index + 1;
      Array.from(table.rows).forEach((tr) => {
        const fresh = newCell(tr.parentElement.tagName === "THEAD");
        tr.insertBefore(fresh, tr.cells[at] || null);
      });
      focusCell(row.cells[at]);
    } else if (action === "col-delete") {
      if (cols === 1) {
        removeTable(table);
        return;
      }
      Array.from(table.rows).forEach((tr) => tr.cells[index] && tr.cells[index].remove());
      focusCell(row.cells[Math.min(index, row.cells.length - 1)]);
    } else if (action === "table-delete") {
      removeTable(table);
      return;
    }
    say("");
    markChanged();
    refreshState();
  }

  function removeTable(table) {
    const wrapper = table.parentElement.classList.contains("table-responsive") ? table.parentElement : table;
    wrapper.remove();
    markChanged();
    refreshState();
  }

  [
    ["row-above", "Row ↑", "Insert row above"],
    ["row-below", "Row ↓", "Insert row below"],
    ["row-delete", "Delete row", "Delete this row"],
    ["col-left", "Col ←", "Insert column to the left"],
    ["col-right", "Col →", "Insert column to the right"],
    ["col-delete", "Delete col", "Delete this column"],
    ["table-delete", "Delete table", "Delete the whole table"],
  ].forEach(([action, label, title], i) => {
    if (i === 0) {
      const heading = document.createElement("span");
      heading.className = "cms-tools-label";
      heading.textContent = "Table:";
      tableTools.appendChild(heading);
    }
    if (action === "col-left" || action === "table-delete") addSeparator(tableTools);
    tableTools.appendChild(makeButton(label, title, () => tableAction(action), action.endsWith("delete") ? "danger" : ""));
  });

  // Tab / Shift+Tab moves between cells; Tab in the last cell appends a row.
  surface.addEventListener("keydown", (event) => {
    if (event.key === "k" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      insertLink();
      return;
    }
    if (event.key !== "Tab") return;
    const cell = currentCell();
    if (!cell) return;
    event.preventDefault();
    const cells = Array.from(cell.closest("table").querySelectorAll("th, td"));
    const at = cells.indexOf(cell) + (event.shiftKey ? -1 : 1);
    if (at >= cells.length) {
      tableAction("row-below");
      const added = currentCell();
      if (added) focusCell(added.parentElement.cells[0]);
    } else if (at >= 0) {
      focusCell(cells[at]);
    }
  });

  // ---------- state, counts, misc ----------
  function refreshState() {
    if (!selectionInSurface()) return;
    const sel = window.getSelection();
    savedRange = sel.getRangeAt(0).cloneRange();

    stateButtons.forEach((btn) => {
      let active = false;
      try {
        active = ["bold", "italic", "insertUnorderedList", "insertOrderedList"].includes(btn.dataset.cmd)
          && document.queryCommandState(btn.dataset.cmd);
      } catch (e) {
        active = false;
      }
      btn.classList.toggle("active", !!active);
    });

    let node = sel.anchorNode;
    node = node && node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    while (node && node !== surface && !BLOCK_TAGS.has(node.tagName)) node = node.parentElement;
    blockSelect.value = node && node !== surface ? node.tagName.toLowerCase() : "p";

    tableTools.hidden = !currentCell();
  }

  function updateCount() {
    const text = mode === "visual" ? surface.innerText : textarea.value;
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    countEl.textContent = `${words} word${words === 1 ? "" : "s"} · ${text.length} characters`;
  }

  document.addEventListener("selectionchange", refreshState);
  surface.addEventListener("input", markChanged);
  textarea.addEventListener("input", () => {
    dirty = true;
    updateCount();
  });

  function setFullscreen(on) {
    root.classList.toggle("cms-fullscreen", on);
    document.body.classList.toggle("cms-no-scroll", on);
    fullscreenBtn.textContent = on ? "✕ Exit full screen" : "⛶ Full screen";
  }
  fullscreenBtn.addEventListener("click", () => setFullscreen(!root.classList.contains("cms-fullscreen")));

  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && root.classList.contains("cms-fullscreen")) setFullscreen(false);
    if (event.key.toLowerCase() === "s" && (event.ctrlKey || event.metaKey) && form) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  if (form) {
    form.addEventListener("submit", () => {
      syncToTextarea();
      submitting = true;
    });
  }

  window.addEventListener("beforeunload", (event) => {
    if (dirty && !submitting) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  // ---------- start ----------
  let stored = null;
  try {
    stored = localStorage.getItem(MODE_KEY);
  } catch (e) {
    stored = null;
  }
  if (stored === "markdown") {
    mode = "markdown";
    applyMode();
  } else {
    applyMode();
    loadVisual().then((ok) => {
      if (!ok) {
        mode = "markdown";
        applyMode();
      }
    });
  }
}
