import os
import uuid

import bleach
import markdown as md
from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

import storage

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload limit

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")
# SVG is deliberately excluded: it can embed <script> and cause stored XSS.
ALLOWED_IMAGE_EXTENSIONS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "gif": "GIF", "webp": "WEBP"}

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "ul", "ol", "li", "h1", "h2", "h3", "h4",
    "blockquote", "code", "pre", "a", "hr", "table", "thead", "tbody", "tr", "th", "td", "img",
]
ALLOWED_ATTRS = {"a": ["href", "title"], "img": ["src", "alt", "title"]}


def render_markdown(text):
    html = md.markdown(text or "", extensions=["fenced_code", "tables"])
    # Sanitize rendered HTML to prevent stored XSS from page content.
    html = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
    # Bootstrap table styling is applied here (not via ALLOWED_ATTRS) so
    # user content can never inject its own "class" attribute.
    html = html.replace(
        "<table>",
        '<div class="table-responsive"><table class="table table-bordered table-striped table-hover">',
    ).replace("</table>", "</table></div>")
    return html


app.jinja_env.filters["render_markdown"] = render_markdown


@app.context_processor
def inject_sidebar():
    return {"sidebar_pages": storage.list_pages()}


@app.route("/")
def index():
    pages = storage.list_pages()
    if pages:
        return redirect(url_for("view_page", slug=pages[0]["id"]))
    return render_template("index.html")


@app.route("/page/<slug>")
def view_page(slug):
    page = storage.get_page(slug)
    if page is None:
        abort(404)
    return render_template("page.html", page=page)


@app.route("/new", methods=["GET", "POST"])
def new_page():
    if request.method == "POST":
        title = request.form.get("title", "")
        content = request.form.get("content", "")
        try:
            page = storage.create_page(title, content)
        except ValueError as exc:
            return render_template("new_page.html", error=str(exc), title=title, content=content), 400
        return redirect(url_for("view_page", slug=page["id"]))
    return render_template("new_page.html")


@app.route("/preview", methods=["POST"])
def preview():
    content = request.form.get("content", "")
    return render_markdown(content)


@app.route("/upload-image", methods=["POST"])
def upload_image():
    file = request.files.get("image")
    if file is None or not file.filename:
        return jsonify({"error": "No image file provided"}), 400

    ext = secure_filename(file.filename).rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    expected_format = ALLOWED_IMAGE_EXTENSIONS.get(ext)
    if not expected_format:
        return jsonify({"error": "Unsupported image type"}), 400

    try:
        # Verify the payload is actually a valid image of the claimed type,
        # not just a file with a spoofed extension.
        image = Image.open(file.stream)
        image.verify()
        if image.format != expected_format:
            return jsonify({"error": "File content does not match its extension"}), 400
    except (UnidentifiedImageError, OSError):
        return jsonify({"error": "Invalid or corrupt image"}), 400

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.stream.seek(0)
    file.save(os.path.join(UPLOAD_DIR, filename))
    return jsonify({"url": url_for("uploaded_file", filename=filename)})


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    safe_name = secure_filename(filename)
    if safe_name != filename or safe_name.rsplit(".", 1)[-1].lower() not in ALLOWED_IMAGE_EXTENSIONS:
        abort(404)
    return send_from_directory(UPLOAD_DIR, safe_name)


@app.errorhandler(413)
def file_too_large(_exc):
    return jsonify({"error": "Image is too large (max 8 MB)"}), 413


@app.route("/page/<slug>/edit", methods=["GET", "POST"])
def edit_page(slug):
    page = storage.get_page(slug)
    if page is None:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "")
        content = request.form.get("content", "")
        try:
            storage.update_page(slug, title, content)
        except ValueError as exc:
            return render_template("edit_page.html", page=page, error=str(exc), title=title, content=content), 400
        return redirect(url_for("view_page", slug=slug))
    return render_template("edit_page.html", page=page, title=page["title"], content=page["content"])


@app.route("/page/<slug>/favorite", methods=["POST"])
def toggle_favorite(slug):
    page = storage.toggle_favorite(slug)
    if page is None:
        abort(404)
    next_url = request.form.get("next", "")
    # Only allow redirecting back to a same-site path to avoid an open redirect.
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("view_page", slug=slug)
    return redirect(next_url)


@app.errorhandler(404)
def not_found(_exc):
    return render_template("404.html"), 404


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)
