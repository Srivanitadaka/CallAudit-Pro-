from flask import Flask, render_template, request, jsonify, send_file
import os, io, json
from pathlib import Path
from datetime import datetime
from analyzer import analyze_text

app = Flask(__name__, static_folder="static", template_folder="templates")
UPLOAD_FOLDER  = "uploads"
RESULTS_FOLDER = Path(__file__).resolve().parent / "analysis_results"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
RESULTS_FOLDER.mkdir(exist_ok=True)


@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-store"
    return r


# ══════════════════════════════════════════════════════
# MAIN DASHBOARD
# ══════════════════════════════════════════════════════
@app.route("/")
def home():
    return render_template("index.html")


# ══════════════════════════════════════════════════════
# ANALYZE — upload + score
# ══════════════════════════════════════════════════════
@app.route("/analyze_ajax", methods=["POST"])
def analyze_ajax():
    file = request.files.get("file")
    if not file:
        return jsonify({"summary": "No file uploaded"}), 400

    filename = file.filename
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    print(f"\n📁 Processing: {filename}")

    try:
        is_audio = filename.lower().endswith((".m4a", ".mp3", ".wav", ".mp4", ".flac"))
        is_text  = filename.lower().endswith((".txt", ".json"))

        with open(filepath, "rb") as f:
            preview = f.read(200).decode("utf-8", errors="ignore")
        has_text = any(c.isalpha() for c in preview[:100]) and len(preview.strip()) > 10

        if is_audio:
            try:
                from transcription.deepgram_processor import process_call_transcript
                transcript = process_call_transcript(filepath)
                if not transcript or len(transcript.strip()) < 20 or "failed" in transcript.lower():
                    return jsonify({
                        "summary": f"Transcription issue: {transcript[:150]}",
                        "grade": "N/A", "overall_score": 0,
                        "scores": {}, "dimension_scores": {},
                        "satisfaction": {}, "agent_quality": {},
                        "model_metrics": {}, "violations": [],
                        "improvements": [], "highlights": [],
                        "sentiment": "unknown",
                        "issue_detected": "Transcription error",
                        "was_resolved": False, "call_outcome": "Unresolved"
                    }), 200
                result = analyze_text(transcript)
            except Exception as e:
                return jsonify({
                    "summary": f"Audio error: {str(e)[:150]}",
                    "grade": "N/A", "overall_score": 0,
                    "scores": {}, "dimension_scores": {},
                    "satisfaction": {}, "agent_quality": {},
                    "model_metrics": {}, "violations": [],
                    "improvements": [], "highlights": [],
                    "sentiment": "unknown",
                    "issue_detected": "Audio error",
                    "was_resolved": False, "call_outcome": "Unresolved"
                }), 200

        elif is_text or has_text:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            result = analyze_text(content)

        else:
            return jsonify({"summary": "Unsupported format."}), 400

        # Save result to analysis_results/
        out_path = RESULTS_FOLDER / f"scored_{Path(filename).stem}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(
                {**result, "_source": filename, "_type": "live_upload"},
                f, indent=2
            )

        print(f"✅ Grade: {result.get('grade')} | Score: {result.get('overall_score')}/100")

        # Return result WITH the saved filename so frontend can build PDF link
        result["_saved_filename"] = out_path.name
        return jsonify(result)

    except Exception as e:
        print(f"❌ {e}")
        return jsonify({"summary": f"Server error: {str(e)[:150]}"}), 500


# ══════════════════════════════════════════════════════
# GET ALL RESULTS — batch table
# ══════════════════════════════════════════════════════
@app.route("/results")
def get_results():
    results = []
    for f in sorted(RESULTS_FOLDER.glob("scored_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sat  = data.get("satisfaction", {})
            results.append({
                "filename":            f.name,
                "grade":               data.get("grade", "?"),
                "overall_score":       data.get("overall_score", 0),
                "sentiment":           data.get("sentiment", "unknown"),
                "was_resolved":        data.get("was_resolved", False),
                "call_outcome":        data.get("call_outcome", "Unresolved"),
                "issue_detected":      data.get("issue_detected", "—"),
                "summary":             data.get("summary", ""),
                "violations":          len(data.get("violations", [])),
                "scores":              data.get("dimension_scores", data.get("scores", {})),
                "satisfaction_rating": sat.get("rating", 0),
                "satisfaction":        sat,
                "_type":               data.get("_type", "batch"),
                "_source":             data.get("_source", f.stem),
            })
        except Exception:
            pass

    results.sort(key=lambda x: x["overall_score"], reverse=True)
    return jsonify(results)


# ══════════════════════════════════════════════════════
# PDF DOWNLOAD
# ══════════════════════════════════════════════════════
@app.route("/download_pdf/<filename>")
def download_pdf(filename):
    """Generate and download a PDF report for a scored call."""
    try:
        from reports.pdf_report import generate_pdf

        scored_file = RESULTS_FOLDER / filename
        if not scored_file.exists():
            return jsonify({"error": f"File not found: {filename}"}), 404

        result    = json.loads(scored_file.read_text(encoding="utf-8"))
        pdf_bytes = generate_pdf(result, filename=filename)

        pdf_name = filename.replace(".json", "_report.pdf")
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype      = "application/pdf",
            as_attachment = True,
            download_name = pdf_name
        )

    except ImportError:
        return jsonify({
            "error": "reportlab not installed. Run: pip install reportlab"
        }), 500
    except Exception as e:
        print(f"❌ PDF error: {e}")
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════
# EXCEL DOWNLOAD — all calls export
# ══════════════════════════════════════════════════════
@app.route("/download_excel")
def download_excel():
    """Generate and download Excel report for all scored calls."""
    try:
        from reports.excel_report import generate_excel

        excel_bytes = generate_excel(str(RESULTS_FOLDER))
        filename    = f"callaudit_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

        return send_file(
            io.BytesIO(excel_bytes),
            mimetype      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment = True,
            download_name = filename
        )

    except ImportError:
        return jsonify({
            "error": "openpyxl not installed. Run: pip install openpyxl"
        }), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Excel error: {e}")
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════
# LIVE MONITOR PAGE (if realtime module exists)
# ══════════════════════════════════════════════════════
@app.route("/live")
def live_monitor_page():
    try:
        return render_template("live_monitor.html")
    except Exception:
        return "<h2>Live monitor template not found</h2>", 404


# ══════════════════════════════════════════════════════
# RUN
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🚀 Server starting on http://127.0.0.1:5000")
    from waitress import serve
    serve(app, host="127.0.0.1", port=5000)