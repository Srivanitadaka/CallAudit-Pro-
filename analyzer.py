import os
import json
from dotenv import load_dotenv
from pathlib import Path
from rag_pipeline.rag_pipeline import RAGPipeline
from llm.langchain_scorer import score_with_langchain
from realtime.alert_engine import AlertEngine

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "config" / ".env")

API_KEY = os.getenv("GROQ_API_KEY")
print(f"🔑 Groq API Key: {API_KEY[:10]}..." if API_KEY else "❌ GROQ_API_KEY missing!")

# ── Single instances reused for every request ──────────
_alert_engine = AlertEngine(socketio=None)

BACKEND   = os.getenv("VECTOR_BACKEND", "chromadb")
_pipeline = RAGPipeline(backend=BACKEND)
_pipeline.setup()

print(f"🗄️  Vector backend: {BACKEND}")


# ══════════════════════════════════════════════════════
# MAIN ANALYZE FUNCTION
# ══════════════════════════════════════════════════════
def analyze_text(text: str) -> dict:
    print(f"📝 Text length: {len(text)} chars")

    if not text or len(text.strip()) < 10:
        return _short_result()

    # ── Step 1: RAG enrichment ─────────────────────────
    enriched = _pipeline.enrich(text)

    # ── Step 2: LangChain scoring ──────────────────────
    print("🔗 LangChain scoring...")
    scored = score_with_langchain(enriched)

    if scored is None:
        print("❌ LangChain scoring failed")
        return _short_result()

    # ── Step 3: Compliance alerts ──────────────────────
    alerts = _check_compliance_alerts(scored, text)
    scored["compliance_alerts"] = alerts

    # ── Step 4: Performance label ──────────────────────
    overall = scored.get("overall_score", 0)
    if   overall >= 90: performance = "excellent"
    elif overall >= 75: performance = "good"
    elif overall >= 60: performance = "average"
    else:               performance = "poor"

    violations   = scored.get("violations", [])
    improvements = scored.get("improvements", [])

    result = {
        # Core fields
        "summary":          scored.get("summary", ""),
        "sentiment":        scored.get("sentiment", "neutral"),
        "performance":      performance,
        "issue":            violations[0]["explanation"] if violations else "No violations",
        "resolution":       improvements[0]["suggestion"] if improvements else "No improvements needed",
        "overall_score":    scored.get("overall_score", 0),
        "grade":            scored.get("grade", "F"),
        "call_outcome":     scored.get("call_outcome", "Unresolved"),
        "was_resolved":     scored.get("was_resolved", False),
        "issue_detected":   scored.get("issue_detected", "Unknown"),

        # Detailed sections
        "satisfaction":     scored.get("satisfaction", {}),
        "agent_quality":    scored.get("agent_quality", {}),
        "dimension_scores": scored.get("dimension_scores", {}),
        "scores":           scored.get("dimension_scores", {}),
        "model_metrics":    scored.get("model_metrics", {}),
        "violations":       scored.get("violations", []),
        "improvements":     scored.get("improvements", []),
        "highlights":       scored.get("highlights", []),

        # Alerts
        "compliance_alerts": alerts,
    }

    # ── Step 5: Save result ────────────────────────────
    _save_result(result, text)

    return result


# ══════════════════════════════════════════════════════
# COMPLIANCE ALERTS
# ══════════════════════════════════════════════════════
def _check_compliance_alerts(scored: dict, transcript: str) -> list:
    """
    Check scored result for compliance violations.
    Returns list of alert dicts.
    Sends email if configured.
    """
    alerts = _alert_engine.check_and_alert(scored, transcript)
    return alerts or []


# ══════════════════════════════════════════════════════
# SAVE RESULT TO FILE
# ══════════════════════════════════════════════════════
def _save_result(result: dict, transcript: str = ""):
    """Save scored result to analysis_results/ folder."""
    try:
        results_dir = BASE_DIR / "analysis_results"
        results_dir.mkdir(exist_ok=True)

        # Count existing files to generate filename
        existing = list(results_dir.glob("scored_*.json"))
        index    = len(existing) + 1
        filename = results_dir / f"scored_live_{index:03d}.json"

        # Add transcript snippet for reference
        save_data = {**result}
        if transcript:
            save_data["transcript_snippet"] = transcript[:500]

        filename.write_text(
            json.dumps(save_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"  💾 Result saved: {filename.name}")

    except Exception as e:
        print(f"  ⚠️  Save failed: {e}")


# ══════════════════════════════════════════════════════
# SHORT RESULT — used when transcript too short
# ══════════════════════════════════════════════════════
def _short_result() -> dict:
    empty = {
        "empathy": 0,
        "professionalism": 0,
        "compliance": 0,
        "resolution_effectiveness": 0,
        "communication_clarity": 0
    }
    return {
        "summary":           "Conversation too short to analyze",
        "sentiment":         "neutral",
        "performance":       "unknown",
        "issue":             "none",
        "resolution":        "none",
        "overall_score":     0,
        "grade":             "N/A",
        "call_outcome":      "Unresolved",
        "was_resolved":      False,
        "issue_detected":    "none",
        "satisfaction":      {},
        "agent_quality":     {},
        "dimension_scores":  empty,
        "scores":            empty,
        "model_metrics":     {},
        "violations":        [],
        "improvements":      [],
        "highlights":        [],
        "compliance_alerts": [],
    }