"""
OMR Checker web app.

Designer:  makes a printable sheet + template with designer/sheet.js (the same
           sheet designer/index.html prints), or uploads an existing
           layout (template.json, optional config.json, blank sheet).
Professor: creates an exam on a layout, enters the answer key on a clickable
           grid, uploads scans (single, batch or ZIP) and downloads
           results.csv (marked options) and scores.csv (scores per student).

Run locally:  python webapp/app.py      (http://localhost:8000)
"""

import os
import sys
from pathlib import Path

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, request,
    send_from_directory, url_for,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline as pl  # noqa: E402
from pipeline import PipelineError  # noqa: E402

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("OMR_MAX_UPLOAD_MB", "2048")) * 1024 * 1024
app.secret_key = os.environ.get("OMR_SECRET_KEY", "omr-checker-local")


def load_exam(exam_id):
    exam = pl.get_exam(exam_id)
    if exam is None:
        abort(404)
    return exam


def load_layout(layout_id):
    layout = pl.get_layout(layout_id)
    if layout is None:
        abort(404)
    return layout


def upload_bytes(field):
    f = request.files.get(field)
    return (f.filename, f.read()) if f and f.filename else (None, None)


@app.errorhandler(413)
def too_large(_e):
    flash("Upload is too large. Split it into smaller batches.", "error")
    return redirect(request.referrer or url_for("index"))


@app.route("/")
def index():
    return render_template("index.html", layouts=pl.list_layouts(), exams=pl.list_exams())


# ---------------------------------------------------------------------------
# Designer
# ---------------------------------------------------------------------------

def render_designer(form=None, name=""):
    try:
        form = form or pl.design_defaults()
        error = None
    except PipelineError as e:
        form, error = {}, str(e)
    return render_template("designer.html", layouts=pl.list_layouts(), form=form, name=name,
                           designer_error=error)


@app.route("/designer")
def designer():
    return render_designer()


@app.route("/designer/sheet.js")
def designer_sheet_js():
    """designer/sheet.js, so the live preview is drawn by the same code as designer/index.html."""
    return send_from_directory(pl.REPO_ROOT / "designer", "sheet.js", mimetype="text/javascript", max_age=0)


@app.post("/designer/layouts")
def create_layout():
    _, template = upload_bytes("template")
    _, config = upload_bytes("config")
    sheet_name, sheet = upload_bytes("sheet")
    assets = [(f.filename, f.read()) for f in request.files.getlist("assets") if f.filename]
    if not template:
        flash("template.json is required", "error")
        return redirect(url_for("designer"))
    try:
        layout_id, warning = pl.create_layout(
            request.form.get("name", ""), template, config, sheet_name, sheet, assets
        )
    except PipelineError as e:
        flash(str(e), "error")
        return redirect(url_for("designer"))
    flash("Layout created. Check that the green boxes sit on the bubbles.", "ok")
    if warning:
        flash(warning, "warn")
    return redirect(url_for("layout_detail", layout_id=layout_id))


@app.post("/designer/generate")
def generate_layout():
    settings = {}
    try:
        settings = pl.design_settings(request.form)
        layout_id = pl.create_generated_layout(request.form.get("name", ""), settings)
    except PipelineError as e:
        flash(str(e), "error")
        return render_designer(settings or None, request.form.get("name", ""))
    flash("Sheet created. Download the PDF and print it at 100%; scans of it can be read straight away.", "ok")
    return redirect(url_for("layout_detail", layout_id=layout_id))


@app.route("/designer/layouts/<layout_id>")
def layout_detail(layout_id):
    layout = load_layout(layout_id)
    return render_template("layout.html", layout=layout, in_use=pl.layout_in_use(layout["id"]),
                           files=pl.layout_files(layout))


@app.route("/designer/layouts/<layout_id>/file/<path:name>")
def layout_file(layout_id, name):
    layout = load_layout(layout_id)
    if name == "preview.png":
        return send_from_directory(layout["dir"], name, max_age=0)
    if name not in pl.layout_files(layout):
        abort(404)
    return send_from_directory(layout["dir"], name, as_attachment=True,
                               download_name=f"{layout['id']}_{name}")


@app.route("/designer/layouts/<layout_id>/download.zip")
def layout_bundle(layout_id):
    layout = load_layout(layout_id)
    return app.response_class(
        pl.layout_zip(layout), mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{layout["id"]}_layout.zip"'},
    )


@app.post("/designer/layouts/<layout_id>/delete")
def delete_layout(layout_id):
    try:
        pl.delete_layout(layout_id)
        flash("Layout deleted", "ok")
    except PipelineError as e:
        flash(str(e), "error")
        return redirect(url_for("layout_detail", layout_id=layout_id))
    return redirect(url_for("designer"))


# ---------------------------------------------------------------------------
# Professor
# ---------------------------------------------------------------------------

@app.route("/professor")
def professor():
    return render_template("professor.html", exams=pl.list_exams(), layouts=pl.list_layouts())


@app.post("/exams")
def create_exam():
    try:
        exam_id = pl.create_exam(request.form.get("name", ""), request.form.get("layout", ""))
    except PipelineError as e:
        flash(str(e), "error")
        return redirect(url_for("professor"))
    return redirect(url_for("answer_key", exam_id=exam_id))


@app.route("/exams/<exam_id>")
def exam_detail(exam_id):
    exam = load_exam(exam_id)
    layout = pl.get_layout(exam["layout"])
    summary = pl.exam_summary(exam)
    return render_template(
        "exam.html", exam=exam, layout=layout, summary=summary,
        job=pl.active_job(exam["id"]), questions=layout["info"]["questions"],
    )


@app.route("/exams/<exam_id>/key", methods=["GET", "POST"])
def answer_key(exam_id):
    exam = load_exam(exam_id)
    layout = pl.get_layout(exam["layout"])
    if request.method == "GET":
        return render_template("key.html", exam=exam, layout=layout, info=layout["info"])

    data = request.get_json(silent=True) or {}
    try:
        with pl.exam_lock(exam["id"]):
            exam = pl.get_exam(exam_id)
            pl.save_keys(exam, data.get("keys", {}), int(data.get("num_questions", 0)))
            pl.save_exam(exam)
            message = pl.score_exam(exam)
    except (PipelineError, ValueError) as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, message=f"Answer key saved. {message}")


@app.post("/exams/<exam_id>/settings")
def exam_settings(exam_id):
    exam = load_exam(exam_id)
    try:
        with pl.exam_lock(exam["id"]):
            exam = pl.get_exam(exam_id)
            exam["name"] = request.form.get("name", exam["name"]).strip() or exam["name"]
            exam["marking"] = {
                "correct": float(request.form["correct"]),
                "wrong": float(request.form["wrong"]),
                "blank": float(request.form["blank"]),
                "multi": "blank" if request.form.get("multi") == "blank" else "wrong",
                "partial": bool(request.form.get("partial")),
            }
            _, roster = upload_bytes("roster")
            if roster:
                pl.set_roster(exam, roster)
            elif request.form.get("remove_roster"):
                pl.set_roster(exam, None)
            pl.save_exam(exam)
            flash(f"Settings saved. {pl.score_exam(exam)}", "ok")
    except (PipelineError, ValueError, KeyError) as e:
        flash(f"Could not save settings: {e}", "error")
    return redirect(url_for("exam_detail", exam_id=exam_id) + "#settings")


@app.post("/exams/<exam_id>/upload")
def upload_scans(exam_id):
    exam = load_exam(exam_id)
    files = [(f.filename, f.read()) for f in request.files.getlist("scans") if f.filename]
    if not files:
        return jsonify(ok=False, error="Choose at least one scan to upload"), 400
    try:
        job_id = pl.submit_scans(exam, files)
    except PipelineError as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, job=pl.get_job(job_id))


@app.route("/jobs/<job_id>")
def job_status(job_id):
    job = pl.get_job(job_id)
    if job is None:
        abort(404)
    return jsonify(job)


@app.post("/exams/<exam_id>/rescore")
def rescore(exam_id):
    exam = load_exam(exam_id)
    try:
        with pl.exam_lock(exam["id"]):
            flash(pl.score_exam(pl.get_exam(exam_id)), "ok")
    except PipelineError as e:
        flash(str(e), "error")
    return redirect(url_for("exam_detail", exam_id=exam_id))


@app.route("/exams/<exam_id>/download/<kind>")
def download(exam_id, kind):
    exam = load_exam(exam_id)
    names = {"results": "results.csv", "scores": "scores.csv", "roster": "roster.csv"}
    if kind not in names or not (exam["dir"] / names[kind]).exists():
        abort(404)
    return send_from_directory(exam["dir"], names[kind], as_attachment=True,
                               download_name=f"{exam['id']}_{names[kind]}")


@app.route("/exams/<exam_id>/scan/<path:file_id>")
def scan_image(exam_id, file_id):
    exam = load_exam(exam_id)
    name = pl.safe_name(file_id)
    for folder in ("overlays", "uploads"):
        if (exam["dir"] / folder / name).exists():
            return send_from_directory(exam["dir"] / folder, name)
    abort(404)


@app.route("/exams/<exam_id>/sheet/<path:file_id>", methods=["GET", "POST"])
def edit_sheet(exam_id, file_id):
    exam = load_exam(exam_id)
    if request.method == "POST":
        try:
            with pl.exam_lock(exam["id"]):
                exam = pl.get_exam(exam_id)
                pl.update_sheet(exam, file_id, request.form.to_dict())
                flash(f"{file_id} corrected. {pl.score_exam(exam)}", "ok")
        except PipelineError as e:
            flash(str(e), "error")
        return redirect(url_for("exam_detail", exam_id=exam_id) + "#results")

    header, rows = pl.read_csv(exam["dir"] / "results.csv")
    row = next((r for r in rows if r["file_id"] == file_id), None)
    if row is None:
        abort(404)
    layout = pl.get_layout(exam["layout"])
    return render_template("sheet.html", exam=exam, row=row, header=header, info=layout["info"])


@app.post("/exams/<exam_id>/sheet/<path:file_id>/delete")
def delete_sheet(exam_id, file_id):
    exam = load_exam(exam_id)
    with pl.exam_lock(exam["id"]):
        exam = pl.get_exam(exam_id)
        pl.delete_sheet(exam, file_id)
        try:
            msg = pl.score_exam(exam)
        except PipelineError as e:
            msg = str(e)
    flash(f"Removed {file_id}. {msg}", "ok")
    return redirect(url_for("exam_detail", exam_id=exam_id) + "#results")


@app.post("/exams/<exam_id>/delete")
def delete_exam(exam_id):
    load_exam(exam_id)
    with pl.exam_lock(exam_id):
        pl.delete_exam(exam_id)
    flash("Exam deleted", "ok")
    return redirect(url_for("professor"))


pl.seed_default_layout()

if __name__ == "__main__":
    from waitress import serve

    port = int(os.environ.get("PORT", "8000"))
    print(f"OMR Checker running on http://localhost:{port}  (data: {pl.DATA_DIR})")
    serve(app, host="0.0.0.0", port=port, threads=8, max_request_body_size=app.config["MAX_CONTENT_LENGTH"])
