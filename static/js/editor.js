// Wires a textarea to a live, server-rendered Markdown preview pane.
function initSplitEditor(textareaId, previewId) {
  const textarea = document.getElementById(textareaId);
  const preview = document.getElementById(previewId);
  if (!textarea || !preview) return;

  let debounceTimer = null;

  function renderPreview() {
    const body = new URLSearchParams({ content: textarea.value });
    fetch("/preview", { method: "POST", body })
      .then((res) => (res.ok ? res.text() : ""))
      .then((html) => {
        preview.innerHTML = html || '<p class="empty-hint">Nothing to preview yet.</p>';
      })
      .catch(() => {
        preview.innerHTML = '<p class="error">Preview unavailable.</p>';
      });
  }

  textarea.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(renderPreview, 250);
  });

  renderPreview();
}

// Inserts text at the current caret position of a textarea and re-triggers preview rendering.
function insertAtCursor(textarea, text) {
  const start = textarea.selectionStart ?? textarea.value.length;
  const end = textarea.selectionEnd ?? textarea.value.length;
  textarea.value = textarea.value.slice(0, start) + text + textarea.value.slice(end);
  const cursorPos = start + text.length;
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = cursorPos;
  textarea.dispatchEvent(new Event("input"));
}

// Wires a file input + status label to upload an image and insert its Markdown into a textarea.
// Also supports pasting an image directly from the clipboard into the textarea.
function initImageUpload(textareaId, fileInputId, statusId) {
  const textarea = document.getElementById(textareaId);
  const fileInput = document.getElementById(fileInputId);
  const status = document.getElementById(statusId);
  if (!textarea) return;

  const EXTENSION_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
  };

  function uploadFile(file) {
    if (!file) return;

    if (status) status.textContent = "Uploading...";
    const formData = new FormData();
    formData.append("image", file, file.name);

    fetch("/upload-image", { method: "POST", body: formData })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Upload failed");
        insertAtCursor(textarea, `![${file.name}](${data.url})\n`);
        if (status) status.textContent = "";
      })
      .catch((err) => {
        if (status) status.textContent = err.message;
      });
  }

  if (fileInput) {
    fileInput.addEventListener("change", () => {
      uploadFile(fileInput.files[0]);
      fileInput.value = "";
    });
  }

  textarea.addEventListener("paste", (event) => {
    const items = event.clipboardData ? event.clipboardData.items : null;
    if (!items) return;

    for (const item of items) {
      const ext = EXTENSION_BY_MIME[item.type];
      if (!ext) continue;
      event.preventDefault();
      const blob = item.getAsFile();
      if (!blob) continue;
      const file = new File([blob], `pasted-image-${Date.now()}.${ext}`, { type: item.type });
      uploadFile(file);
      break;
    }
  });
}


// Adds an "Insert Table" button (rows/columns picker) to a toolbar; inserts a Markdown table at the caret.
function initTableBuilder(textareaId, toolbarId) {
  const textarea = document.getElementById(textareaId);
  const toolbar = document.getElementById(toolbarId);
  if (!textarea || !toolbar) return;

  const MAX_ROWS = 50;
  const MAX_COLS = 12;

  const wrapper = document.createElement("span");
  wrapper.className = "table-builder";
  wrapper.innerHTML = `
    <button type="button" class="btn btn-sm btn-secondary table-builder-toggle">Insert Table</button>
    <span class="table-builder-panel" hidden>
      <label>Rows <input type="number" class="tb-rows" min="1" max="${MAX_ROWS}" value="3"></label>
      <label>Cols <input type="number" class="tb-cols" min="1" max="${MAX_COLS}" value="3"></label>
      <button type="button" class="btn btn-sm tb-insert">Insert</button>
      <button type="button" class="btn btn-sm btn-secondary tb-cancel">Cancel</button>
    </span>`;
  toolbar.insertBefore(wrapper, toolbar.firstChild);

  const toggle = wrapper.querySelector(".table-builder-toggle");
  const panel = wrapper.querySelector(".table-builder-panel");
  const rowsInput = wrapper.querySelector(".tb-rows");
  const colsInput = wrapper.querySelector(".tb-cols");

  function clamp(value, max) {
    const n = parseInt(value, 10);
    return Math.min(Math.max(Number.isNaN(n) ? 1 : n, 1), max);
  }

  function buildTable(rows, cols) {
    const row = (cell) => "| " + Array.from({ length: cols }, (_, i) => cell(i)).join(" | ") + " |";
    const lines = [row((i) => `Header ${i + 1}`), row(() => "---")];
    for (let r = 0; r < rows; r++) lines.push(row(() => "   "));
    return lines.join("\n");
  }

  function insertTable() {
    const table = buildTable(clamp(rowsInput.value, MAX_ROWS), clamp(colsInput.value, MAX_COLS));
    const pos = textarea.selectionStart ?? textarea.value.length;
    const before = textarea.value.slice(0, pos);
    // Markdown tables must be preceded by a blank line.
    const prefix = before === "" || before.endsWith("\n\n") ? "" : before.endsWith("\n") ? "\n" : "\n\n";
    insertAtCursor(textarea, `${prefix}${table}\n\n`);
    panel.hidden = true;
  }

  toggle.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) rowsInput.focus();
  });
  wrapper.querySelector(".tb-cancel").addEventListener("click", () => {
    panel.hidden = true;
  });
  wrapper.querySelector(".tb-insert").addEventListener("click", insertTable);
  [rowsInput, colsInput].forEach((input) =>
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        insertTable();
      }
    })
  );
}
