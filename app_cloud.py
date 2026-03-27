# app_cloud.py
"""
CallAudit Pro — Unified Cloud App
─────────────────────────────────────────────
All features in one Streamlit app:
  Page 1 → 🏠 Dashboard   (upload + analyze)
  Page 2 → 🎤 Live        (mic + real-time)
  Page 3 → 📊 Supervisor  (team analytics)
  Page 4 → 📋 Reports     (PDF + Excel)

Run locally:
  streamlit run app_cloud.py

Deploy on Streamlit Cloud:
  Main file: app_cloud.py
"""

import os
import sys
import json
import time
import tempfile
import threading
from pathlib import Path
from datetime import datetime

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Load .env (local dev) ────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "config" / ".env")
except Exception:
    pass

# ── Override with Streamlit Cloud secrets ───────────────
for _key in [
    "GROQ_API_KEY", "DEEPGRAM_API_KEY",
    "PINECONE_API_KEY", "VECTOR_BACKEND",
    "ALERT_EMAIL_FROM", "ALERT_EMAIL_PASSWORD",
    "ALERT_EMAIL_TO"
]:
    try:
        _val = st.secrets.get(_key)
        if _val:
            os.environ[_key] = _val
    except Exception:
        pass

RESULTS_DIR = ROOT / "analysis_results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Page config ──────────────────────────────────────────
st.set_page_config(
    page_title="CallAudit Pro",
    page_icon="🎧",
    layout="wide",
)

# ── Global CSS ───────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background:#080c14; color:#e2e8f0; }
  [data-testid="stSidebar"]          { background:#0d1320; border-right:1px solid #1e293b; }
  [data-testid="stSidebar"] *        { color:#e2e8f0 !important; }
  h1, h2, h3                         { color:#38bdf8 !important; }
  .stButton button {
    background:#38bdf8; color:#080c14;
    font-weight:800; border:none; border-radius:8px;
    padding:10px 24px; width:100%;
  }
  .stButton button:hover { opacity:.9; }
  div[data-testid="metric-container"] {
    background:#0d1320; border:1px solid #1e293b;
    border-radius:12px; padding:16px;
  }
  .viol-card  { padding:14px; border-radius:8px; margin-bottom:8px; border-left:4px solid; }
  .critical   { border-left-color:#f87171; background:rgba(248,113,113,.1); }
  .high       { border-left-color:#fb923c; background:rgba(251,146,60,.1); }
  .medium     { border-left-color:#f59e0b; background:rgba(245,158,11,.1); }
  .imp-card   {
    padding:14px; border-radius:8px; margin-bottom:8px;
    border-left:4px solid #38bdf8; background:rgba(56,189,248,.08);
  }
  .h-item {
    padding:10px 14px; background:rgba(34,197,94,.08);
    border:1px solid rgba(34,197,94,.2); border-radius:8px;
    font-size:13px; color:#86efac; margin-bottom:6px;
  }
  .live-badge {
    display:inline-flex; align-items:center; gap:8px;
    padding:8px 20px; border-radius:20px;
    background:rgba(248,113,113,0.15);
    border:1px solid rgba(248,113,113,0.3);
    color:#f87171; font-size:14px; font-weight:700;
  }
</style>
""", unsafe_allow_html=True)

# ── Colour helpers ───────────────────────────────────────
GRADE_C = {
    "A": "#22c55e", "B": "#38bdf8",
    "C": "#f59e0b", "D": "#fb923c", "F": "#f87171"
}


def score_color(v, mx=100):
    p = v / mx
    return "#22c55e" if p >= .75 else "#f59e0b" if p >= .55 else "#f87171"


# ── Session state defaults ───────────────────────────────
_defaults = {
    "page":             "🏠 Dashboard",
    "result":           None,
    "transcript":       "",
    "alerts":           [],
    "live_running":     False,
    "live_transcript":  "",
    "live_result":      None,
    "live_chunks":      0,
    "pipeline":         None,
    "live_monitor_obj": None,
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ══════════════════════════════════════════════════════════
# SIDEBAR NAVIGATION
# ══════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        "<h2 style='color:#38bdf8;margin-bottom:4px'>🎧 CallAudit Pro</h2>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='color:#64748b;font-size:12px;margin-bottom:0'>AI Quality Auditor</p>",
        unsafe_allow_html=True
    )
    st.divider()

    _pages = ["🏠 Dashboard", "🎤 Live Analysis", "📊 Supervisor", "📋 Reports"]
    page = st.radio(
        "Navigation",
        _pages,
        index=_pages.index(st.session_state.page)
    )
    st.session_state.page = page

    st.divider()
    st.markdown(
        "<p style='color:#1e293b;font-size:11px'>"
        "llama-3.3-70b · Groq<br>"
        "LangChain · RAG · Pinecone<br>"
        "Deepgram · ChromaDB</p>",
        unsafe_allow_html=True
    )


# ══════════════════════════════════════════════════════════
# SHARED: GET RAG PIPELINE
# ══════════════════════════════════════════════════════════
def get_pipeline():
    if st.session_state.pipeline is not None:
        return st.session_state.pipeline
    try:
        from rag_pipeline.rag_pipeline import RAGPipeline
        backend  = os.getenv("VECTOR_BACKEND", "chromadb")
        pipeline = RAGPipeline(backend=backend)
        pipeline.setup()
        st.session_state.pipeline = pipeline
        return pipeline
    except Exception as e:
        st.error(f"Pipeline setup failed: {e}")
        return None


# ══════════════════════════════════════════════════════════
# SHARED: ANALYZE TRANSCRIPT
# ══════════════════════════════════════════════════════════
def run_analysis(text: str) -> dict:
    try:
        # ── Patch: newer httpx dropped 'proxies' kwarg; some LangChain/Groq
        #    versions still pass it. Monkey-patch before importing. ──────────
        try:
            import httpx
            _orig_init = httpx.Client.__init__
            def _patched_init(self, *args, **kwargs):
                kwargs.pop("proxies", None)
                _orig_init(self, *args, **kwargs)
            httpx.Client.__init__ = _patched_init

            _orig_async_init = httpx.AsyncClient.__init__
            def _patched_async_init(self, *args, **kwargs):
                kwargs.pop("proxies", None)
                _orig_async_init(self, *args, **kwargs)
            httpx.AsyncClient.__init__ = _patched_async_init
        except Exception:
            pass

        from llm.langchain_scorer  import score_with_langchain
        from realtime.alert_engine import AlertEngine

        pipeline = get_pipeline()
        if not pipeline:
            return None

        with st.spinner("🔍 Searching similar calls..."):
            enriched = pipeline.enrich(text)

        with st.spinner("🤖 AI scoring with Groq..."):
            result = score_with_langchain(enriched)

        if result:
            alert_engine = AlertEngine(socketio=None)
            alerts = alert_engine.check_and_alert(result, text)
            result["compliance_alerts"] = alerts or []
            _save_result(result)

        return result

    except Exception as e:
        st.error(f"Analysis error: {e}")
        return None


# ══════════════════════════════════════════════════════════
# SHARED: TRANSCRIBE AUDIO
# ══════════════════════════════════════════════════════════
def transcribe_file(file_path: str) -> str:
    try:
        from transcription.deepgram_processor import process_call_transcript
        return process_call_transcript(file_path)
    except Exception as e:
        st.error(f"Transcription error: {e}")
        return ""


# ══════════════════════════════════════════════════════════
# SHARED: SAVE RESULT
# ══════════════════════════════════════════════════════════
def _save_result(result: dict):
    try:
        existing = list(RESULTS_DIR.glob("scored_live_*.json"))
        idx      = len(existing) + 1
        fname    = RESULTS_DIR / f"scored_live_{idx:03d}.json"
        fname.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
# SHARED: LOAD ALL RESULTS
# ══════════════════════════════════════════════════════════
def load_results() -> list:
    results = []
    for f in sorted(RESULTS_DIR.glob("scored_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_filename"] = f.name
            results.append(data)
        except Exception:
            pass
    return results


# ══════════════════════════════════════════════════════════
# SHARED: RENDER FULL RESULT DASHBOARD
# ══════════════════════════════════════════════════════════
def render_result_dashboard(r: dict):
    if not r:
        return

    grade = r.get("grade", "?")
    score = r.get("overall_score", 0)
    gc    = GRADE_C.get(grade, "#64748b")
    sat   = r.get("satisfaction", {})
    aq    = r.get("agent_quality", {})
    dims  = r.get("dimension_scores", r.get("scores", {}))
    mm    = r.get("model_metrics", {})

    # ── KPI row ────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall Score",  f"{score}/100",  delta=f"Grade {grade}")
    c2.metric("Satisfaction",   f"{sat.get('rating', 0):.1f}/5")
    c3.metric("Call Outcome",   r.get("call_outcome", "Unknown"))
    c4.metric("Violations",     len(r.get("violations", [])))

    # ── Compliance alerts ──────────────────────────────────
    alerts = r.get("compliance_alerts", [])
    if alerts:
        st.markdown(f"### 🚨 Compliance Alerts ({len(alerts)})")
        for a in alerts:
            lvl   = (a.get("level") or "warning").lower()
            cls   = "critical" if lvl == "critical" else "high" if lvl == "high" else "medium"
            color = "#f87171" if lvl == "critical" else "#fb923c" if lvl == "high" else "#f59e0b"
            msg   = a.get("message", "")
            level_label = (a.get("level") or "").upper()
            st.markdown(
                f"<div class='viol-card {cls}'>"
                f"<strong style='color:{color}'>[{level_label}]</strong> {msg}"
                f"</div>",
                unsafe_allow_html=True
            )

    st.divider()

    # ── Two column layout ──────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        # Dimension scores bar chart
        st.markdown("#### 🎯 Dimension Scores")
        DIM_LABELS = {
            "empathy":                  "Empathy",
            "professionalism":          "Professionalism",
            "compliance":               "Compliance",
            "resolution_effectiveness": "Resolution",
            "communication_clarity":    "Clarity",
        }
        dim_names = list(DIM_LABELS.values())
        dim_vals  = [dims.get(k, 0) for k in DIM_LABELS]

        fig = go.Figure(go.Bar(
            x            = dim_names,
            y            = dim_vals,
            marker_color = [score_color(v, 10) for v in dim_vals],
            text         = [f"{v}/10" for v in dim_vals],
            textposition = "outside",
        ))
        fig.update_layout(
            plot_bgcolor  = "#0d1320",
            paper_bgcolor = "#0d1320",
            font_color    = "#e2e8f0",
            yaxis_range   = [0, 10],
            height        = 250,
            margin        = dict(l=0, r=0, t=0, b=0),
            showlegend    = False,
        )
        fig.update_xaxes(gridcolor="#1e293b")
        fig.update_yaxes(gridcolor="#1e293b")
        st.plotly_chart(fig, use_container_width=True)

        # Customer satisfaction details
        st.markdown("#### 👤 Customer Satisfaction")
        sat_items = [
            ("Sentiment",   sat.get("sentiment", "—")),
            ("Frustration", sat.get("customer_frustration", "—")),
            ("Stability",   sat.get("emotional_stability", "—")),
            ("Why",         sat.get("frustration_reason", "None")),
        ]
        for label, val in sat_items:
            ca, cb = st.columns([2, 1])
            ca.markdown(
                f"<span style='color:#64748b;font-size:13px'>{label}</span>",
                unsafe_allow_html=True
            )
            cb.markdown(
                f"<span style='font-size:13px'>{val}</span>",
                unsafe_allow_html=True
            )

    with col_r:
        # Agent quality bars
        st.markdown("#### 👔 Agent Quality")
        aq_metrics = [
            ("Language Clarity",    aq.get("language_clarity",    0), 20),
            ("Professionalism",     aq.get("professionalism",     0), 20),
            ("Time Efficiency",     aq.get("time_efficiency",     0), 20),
            ("Response Efficiency", aq.get("response_efficiency", 0), 20),
            ("Empathy Score",       aq.get("empathy_score",       0), 10),
        ]
        for label, val, mx in aq_metrics:
            ca, cb = st.columns([3, 1])
            ca.markdown(
                f"<span style='font-size:12px;color:#94a3b8'>{label}</span>",
                unsafe_allow_html=True
            )
            cb.markdown(
                f"<span style='font-size:12px;color:{score_color(val, mx)}'>{val}/{mx}</span>",
                unsafe_allow_html=True
            )
            st.progress(int(val / mx * 100))

        # Bias / calmed pills
        bias   = aq.get("bias_detected", False)
        calmed = aq.get("calmed_customer", False)
        p1c    = "#f87171" if bias   else "#22c55e"
        p2c    = "#22c55e" if calmed else "#f87171"
        p1txt  = "⚠ Bias Detected"   if bias   else "✔ No Bias"
        p2txt  = "✔ Customer Calmed" if calmed else "✘ Not Calmed"
        st.markdown(
            f"<span style='color:{p1c};font-size:13px'>{p1txt}</span>"
            f"&nbsp;&nbsp;&nbsp;"
            f"<span style='color:{p2c};font-size:13px'>{p2txt}</span>",
            unsafe_allow_html=True
        )

    st.divider()

    # ── Violations ─────────────────────────────────────────
    col_v, col_i = st.columns(2)

    with col_v:
        viols = r.get("violations", [])
        st.markdown(f"#### ⚠ Violations ({len(viols)})")
        if viols:
            for v in viols:
                sev   = (v.get("severity") or "medium").lower()
                cls   = "critical" if sev == "critical" else "high" if sev == "high" else "medium"
                vtype = (v.get("type") or "").replace("_", " ").title()
                expl  = v.get("explanation", "")[:120]
                quote = v.get("quote", "")[:80]

                if quote:
                    quote_html = (
                        '<br><em style="color:#f87171;font-size:11px">'
                        + quote
                        + '</em>'
                    )
                else:
                    quote_html = ""

                st.markdown(
                    f"<div class='viol-card {cls}'>"
                    f"<strong>{vtype}</strong> "
                    f"<span style='font-size:10px;color:#94a3b8'>[{sev.upper()}]</span><br>"
                    f"<span style='font-size:12px;color:#94a3b8'>{expl}</span>"
                    f"{quote_html}"
                    f"</div>",
                    unsafe_allow_html=True
                )
        else:
            st.success("✅ No violations detected")

    # ── Improvements ───────────────────────────────────────
    with col_i:
        imps = r.get("improvements", [])
        st.markdown(f"#### 💡 Improvements ({len(imps)})")
        if imps:
            for i in imps:
                area    = (i.get("area") or "").replace("_", " ").upper()
                sug     = i.get("suggestion", "")[:150]
                example = i.get("example", "")[:100]

                if example:
                    ex_html = (
                        '<br><em style="color:#64748b;font-size:11px">💬 '
                        + example
                        + '</em>'
                    )
                else:
                    ex_html = ""

                st.markdown(
                    f"<div class='imp-card'>"
                    f"<strong style='color:#38bdf8;font-size:11px'>{area}</strong><br>"
                    f"<span style='font-size:13px'>{sug}</span>"
                    f"{ex_html}"
                    f"</div>",
                    unsafe_allow_html=True
                )
        else:
            st.success("✅ No improvements needed")

    st.divider()

    # ── Highlights + Summary ───────────────────────────────
    col_h, col_s = st.columns(2)

    with col_h:
        highs = r.get("highlights", [])
        if highs:
            st.markdown("#### ✅ What Went Well")
            for h in highs:
                st.markdown(
                    f"<div class='h-item'>✅ {h}</div>",
                    unsafe_allow_html=True
                )

    with col_s:
        st.markdown("#### 📝 AI Summary")
        st.info(r.get("summary", "No summary available"))

    # ── Model metrics ──────────────────────────────────────
    st.divider()
    st.markdown("#### 📐 Classification Metrics")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Precision",  f"{mm.get('precision',  0):.2f}")
    mc2.metric("Recall",     f"{mm.get('recall',     0):.2f}")
    mc3.metric("F1 Score",   f"{mm.get('f1_score',   0):.2f}")
    mc4.metric("Confidence", f"{mm.get('confidence', 0) * 100:.0f}%")


# ══════════════════════════════════════════════════════════
# TRANSCRIPT VIEWER HELPER
# ══════════════════════════════════════════════════════════
def render_transcript(text: str):
    lines = text.split("\n")
    html_parts = []
    for line in lines:
        if not line.strip():
            continue
        line_lower = line.lower()
        if line_lower.startswith("agent:"):
            content = line[6:]
            html_parts.append(
                "<div style='background:#0d1f30;border-left:3px solid #38bdf8;"
                "padding:8px;margin:4px 0;border-radius:4px;font-size:13px'>"
                "<strong style='color:#38bdf8'>Agent</strong>"
                + content
                + "</div>"
            )
        elif line_lower.startswith("customer:"):
            content = line[9:]
            html_parts.append(
                "<div style='background:#1a1020;border-left:3px solid #a78bfa;"
                "padding:8px;margin:4px 0;border-radius:4px;font-size:13px'>"
                "<strong style='color:#a78bfa'>Customer</strong>"
                + content
                + "</div>"
            )
        else:
            html_parts.append(
                "<div style='font-size:13px;color:#64748b;padding:4px 0'>"
                + line
                + "</div>"
            )

    st.markdown(
        "<div style='background:#111827;border:1px solid #1e293b;"
        "border-radius:8px;padding:16px;max-height:320px;overflow-y:auto'>"
        + "".join(html_parts)
        + "</div>",
        unsafe_allow_html=True
    )


# ══════════════════════════════════════════════════════════
# PAGE 1 — MAIN DASHBOARD
# ══════════════════════════════════════════════════════════
if page == "🏠 Dashboard":
    st.markdown(
        "<h1>🎧 CallAudit <span style='color:#38bdf8'>Pro</span></h1>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='color:#64748b'>AI Customer Support Quality Auditor</p>",
        unsafe_allow_html=True
    )

    # Upload section
    st.markdown("### 📤 Upload Call")
    col_u1, col_u2 = st.columns(2)

    with col_u1:
        st.markdown("**Audio File** (mp3, wav, m4a)")
        audio_file = st.file_uploader(
            "audio",
            type=["mp3", "wav", "m4a", "flac"],
            label_visibility="collapsed"
        )

    with col_u2:
        st.markdown("**Transcript** (txt, json)")
        text_file = st.file_uploader(
            "transcript",
            type=["txt", "json"],
            label_visibility="collapsed"
        )

    if st.button("🔍 Analyze & Score", type="primary"):
        transcript = ""

        if audio_file:
            with st.spinner("🎙 Transcribing audio..."):
                suffix = Path(audio_file.name).suffix
                tmp    = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                tmp.write(audio_file.read())
                tmp.close()
                transcript = transcribe_file(tmp.name)
                os.unlink(tmp.name)

            if transcript:
                st.success(f"✅ Transcribed — {len(transcript)} chars")
                # Save transcript immediately so it shows even if scoring fails
                st.session_state.transcript = transcript
            else:
                st.error("❌ Transcription failed. Check DEEPGRAM_API_KEY.")

        elif text_file:
            raw = text_file.read()
            try:
                transcript = raw.decode("utf-8")
            except Exception:
                transcript = raw.decode("latin-1")
            st.success(f"✅ Loaded — {len(transcript)} chars")
            st.session_state.transcript = transcript

        else:
            st.warning("Please upload an audio file or transcript first.")

        if transcript:
            with st.spinner("🤖 Analyzing transcript..."):
                result = run_analysis(transcript)
            if result:
                st.session_state.result     = result
                st.session_state.transcript = transcript
                grade = result.get("grade", "?")
                score = result.get("overall_score", 0)
                st.success(f"✅ Analysis complete — Grade {grade} | Score {score}/100")
            else:
                st.error(
                    "❌ Scoring failed (check GROQ_API_KEY / LangChain version). "
                    "Transcript is shown below."
                )

    # Always show transcript if we have one (even if scoring failed)
    if st.session_state.transcript and not st.session_state.result:
        st.divider()
        st.markdown("### 📄 Transcript (Scoring pending / failed)")
        render_transcript(st.session_state.transcript)

    # Show full results dashboard
    if st.session_state.result:
        st.divider()
        st.markdown("## 📊 Analysis Results")

        # ── Quick summary card at the top ──────────────────
        r = st.session_state.result
        grade = r.get("grade", "?")
        score = r.get("overall_score", 0)
        gc    = GRADE_C.get(grade, "#64748b")
        summary_text = r.get("summary", "No summary available.")

        st.markdown(
            f"""
            <div style='background:#0d1320;border:1px solid #1e293b;border-radius:12px;
                        padding:20px;margin-bottom:16px'>
              <div style='display:flex;align-items:center;gap:16px;margin-bottom:12px'>
                <span style='font-size:48px;font-weight:900;color:{gc}'>{grade}</span>
                <div>
                  <div style='font-size:22px;font-weight:700;color:#e2e8f0'>{score}/100</div>
                  <div style='font-size:13px;color:#64748b'>Overall Score</div>
                </div>
              </div>
              <div style='font-size:14px;color:#cbd5e1;line-height:1.6'>
                <strong style='color:#38bdf8'>📝 AI Summary:</strong><br>{summary_text}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        render_result_dashboard(st.session_state.result)

        # Transcript viewer
        if st.session_state.transcript:
            with st.expander("📄 View Full Transcript"):
                render_transcript(st.session_state.transcript)

        # PDF download
        st.divider()
        try:
            from reports.pdf_report import generate_pdf
            pdf_bytes = generate_pdf(
                st.session_state.result,
                filename="dashboard_analysis.json"
            )
            st.download_button(
                label     = "⬇ Download PDF Report",
                data      = pdf_bytes,
                file_name = f"callaudit_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime      = "application/pdf",
            )
        except Exception as e:
            st.caption(f"PDF not available: {e}")


# ══════════════════════════════════════════════════════════
# PAGE 2 — LIVE ANALYSIS
# ══════════════════════════════════════════════════════════
elif page == "🎤 Live Analysis":
    st.markdown(
        "<h1>🎤 Live <span style='color:#38bdf8'>Analysis</span></h1>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='color:#64748b'>Real-time call monitoring with AI scoring</p>",
        unsafe_allow_html=True
    )

    # Live status badge
    if st.session_state.live_running:
        st.markdown(
            "<div class='live-badge'>"
            "<span style='width:10px;height:10px;border-radius:50%;"
            "background:#f87171;display:inline-block'></span>"
            " LIVE MONITORING"
            "</div>",
            unsafe_allow_html=True
        )
        st.markdown("")

    st.divider()

    # Controls row
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("▶ Start Monitor"):
            st.session_state.live_running    = True
            st.session_state.live_transcript = ""
            st.session_state.live_result     = None
            st.session_state.live_chunks     = 0
            try:
                from realtime.live_monitor import LiveMonitor
                if st.session_state.live_monitor_obj is None:
                    st.session_state.live_monitor_obj = LiveMonitor(socketio=None)
                st.session_state.live_monitor_obj.start()
                st.success("🎤 Microphone started! Speak now, then click Stop & Score.")
            except BaseException as e:
                st.session_state.live_running = False
                st.warning(f"Microphone unavailable: {e} — Use Manual Transcript Input below.")

    with col2:
        if st.button("⏹ Stop & Score"):
            # ── Step 1: mark stopped immediately ──────────
            st.session_state.live_running = False
            transcript = ""

            # ── Step 2: grab transcript from monitor ──────
            # Everything is wrapped in BaseException so PyAudio's
            # SystemExit on Windows can NEVER reach Streamlit.
            monitor = st.session_state.get("live_monitor_obj")
            if monitor is not None:
                try:
                    # Get status BEFORE stop (transcript lives here)
                    status     = monitor.get_status()
                    transcript = (status.get("transcript") or "").strip()
                except BaseException:
                    transcript = ""

                try:
                    # stop() runs PyAudio teardown in a background
                    # thread internally — never raises here
                    result_dict = monitor.stop()
                    if not transcript:
                        transcript = (result_dict.get("transcript") or "").strip()
                except BaseException:
                    pass

                # Always clear the monitor reference
                st.session_state.live_monitor_obj = None

            # ── Step 3: fall back to any partial transcript ─
            if not transcript:
                transcript = (st.session_state.get("live_transcript") or "").strip()

            # ── Step 4: score if we have content ──────────
            if len(transcript) > 20:
                st.session_state.live_transcript = transcript
                with st.spinner("🤖 AI scoring..."):
                    scored = run_analysis(transcript)
                if scored:
                    st.session_state.live_result = scored
                    st.success(
                        f"✅ Grade {scored.get('grade')} | "
                        f"Score {scored.get('overall_score')}/100"
                    )
                else:
                    st.error(
                        "❌ Scoring failed — check GROQ_API_KEY. "
                        "Your transcript was captured. Copy it and paste "
                        "it into Manual Transcript Input below to retry."
                    )
            else:
                st.warning(
                    "⚠ No transcript captured yet. The microphone records "
                    "in 5-second chunks — make sure you spoke for at least "
                    "10 seconds before stopping. OR paste a transcript "
                    "manually below and click Analyze Transcript."
                )

    with col3:
        if st.button("🔄 Refresh Transcript"):
            try:
                monitor = st.session_state.get("live_monitor_obj")
                if monitor is not None:
                    status = monitor.get_status()
                    st.session_state.live_transcript = status.get("transcript", "")
                    st.session_state.live_chunks    += 1
                    st.rerun()
            except BaseException:
                pass

    st.divider()

    # Manual transcript paste (works everywhere including cloud)
    st.markdown("### 📝 Manual Transcript Input")
    st.caption(
        "Paste a call transcript below and click Analyze. "
        "Use this when microphone is not available."
    )

    manual_text = st.text_area(
        "Transcript",
        height=200,
        placeholder="Agent: Thank you for calling support...\nCustomer: I have an issue with my order...",
        label_visibility="collapsed"
    )

    if st.button("⚡ Analyze Transcript", type="primary"):
        if manual_text.strip():
            st.session_state.live_transcript = manual_text
            with st.spinner("Analyzing..."):
                result = run_analysis(manual_text)
            if result:
                st.session_state.live_result = result
                grade = result.get("grade", "?")
                score = result.get("overall_score", 0)
                st.success(f"✅ Grade {grade} | Score {score}/100")
        else:
            st.warning("Please paste a transcript first.")

    # Show live transcript
    if st.session_state.live_transcript:
        st.divider()
        st.markdown("### 📄 Transcript")
        render_transcript(st.session_state.live_transcript)

    # Show live results
    if st.session_state.live_result:
        st.divider()
        st.markdown("## 📊 Live Scoring Result")

        # ── Quick summary card ─────────────────────────────
        r     = st.session_state.live_result
        grade = r.get("grade", "?")
        score = r.get("overall_score", 0)
        gc    = GRADE_C.get(grade, "#64748b")
        summary_text = r.get("summary", "No summary available.")

        st.markdown(
            f"""
            <div style='background:#0d1320;border:1px solid #1e293b;border-radius:12px;
                        padding:20px;margin-bottom:16px'>
              <div style='display:flex;align-items:center;gap:16px;margin-bottom:12px'>
                <span style='font-size:48px;font-weight:900;color:{gc}'>{grade}</span>
                <div>
                  <div style='font-size:22px;font-weight:700;color:#e2e8f0'>{score}/100</div>
                  <div style='font-size:13px;color:#64748b'>Overall Score</div>
                </div>
              </div>
              <div style='font-size:14px;color:#cbd5e1;line-height:1.6'>
                <strong style='color:#38bdf8'>📝 AI Summary:</strong><br>{summary_text}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        render_result_dashboard(st.session_state.live_result)

        # PDF download
        try:
            from reports.pdf_report import generate_pdf
            pdf_bytes = generate_pdf(
                st.session_state.live_result,
                filename="live_analysis.json"
            )
            st.download_button(
                label     = "⬇ Download PDF Report",
                data      = pdf_bytes,
                file_name = f"live_callaudit_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime      = "application/pdf",
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════
# PAGE 3 — SUPERVISOR DASHBOARD
# ══════════════════════════════════════════════════════════
elif page == "📊 Supervisor":
    st.markdown(
        "<h1>📊 Supervisor <span style='color:#38bdf8'>Dashboard</span></h1>",
        unsafe_allow_html=True
    )

    results = load_results()

    if not results:
        st.warning("No scored calls found. Go to Dashboard or Live Analysis and analyze some calls first.")
        st.stop()

    # Build dataframe
    rows = []
    for r in results:
        dims = r.get("dimension_scores", r.get("scores", {}))
        sat  = r.get("satisfaction", {})
        rows.append({
            "filename":        r.get("_filename", ""),
            "grade":           r.get("grade", "?"),
            "score":           r.get("overall_score", 0),
            "sentiment":       r.get("sentiment", "neutral"),
            "outcome":         r.get("call_outcome", "Unknown"),
            "resolved":        bool(r.get("was_resolved", False)),
            "violations":      len(r.get("violations", [])),
            "issue":           str(r.get("issue_detected", "")),
            "summary":         str(r.get("summary", "")),
            "empathy":         dims.get("empathy", 0),
            "professionalism": dims.get("professionalism", 0),
            "compliance":      dims.get("compliance", 0),
            "resolution":      dims.get("resolution_effectiveness", 0),
            "clarity":         dims.get("communication_clarity", 0),
            "sat_rating":      float(sat.get("rating", 0)),
        })
    df = pd.DataFrame(rows)

    # Filters
    with st.expander("🔧 Filters"):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            grade_f = st.multiselect(
                "Grade", ["A", "B", "C", "D", "F"],
                default=["A", "B", "C", "D", "F"]
            )
        with fc2:
            outcomes  = df["outcome"].unique().tolist()
            outcome_f = st.multiselect("Outcome", outcomes, default=outcomes)
        with fc3:
            min_s, max_s = st.slider("Score range", 0, 100, (0, 100))

    df_f = df[
        df["grade"].isin(grade_f) &
        df["outcome"].isin(outcome_f) &
        df["score"].between(min_s, max_s)
    ]

    if df_f.empty:
        st.warning("No results match your filters.")
        st.stop()

    st.caption(f"Showing {len(df_f)} of {len(df)} calls")

    # KPIs
    st.markdown("### 📊 Team Overview")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Calls",      len(df_f))
    k2.metric("Avg Score",        f"{df_f['score'].mean():.1f}/100")
    k3.metric("Pass Rate ≥60",    f"{(df_f['score'] >= 60).sum() / len(df_f) * 100:.0f}%")
    k4.metric("Total Violations", int(df_f["violations"].sum()))
    k5.metric("Resolved",         int(df_f["resolved"].sum()))
    k6.metric("Grade F",          int((df_f["grade"] == "F").sum()))

    st.divider()

    # Charts row 1
    ch1, ch2 = st.columns(2)

    with ch1:
        st.markdown("**Score Distribution**")
        fig = px.histogram(
            df_f, x="score", nbins=10,
            color_discrete_sequence=["#38bdf8"],
            labels={"score": "Score", "count": "Calls"}
        )
        fig.update_layout(
            plot_bgcolor="#0d1320", paper_bgcolor="#0d1320",
            font_color="#e2e8f0", bargap=0.1,
            height=250, margin=dict(l=0, r=0, t=0, b=0), showlegend=False
        )
        fig.update_xaxes(gridcolor="#1e293b")
        fig.update_yaxes(gridcolor="#1e293b")
        st.plotly_chart(fig, use_container_width=True)

    with ch2:
        st.markdown("**Grade Breakdown**")
        gc_df = df_f["grade"].value_counts().reset_index()
        gc_df.columns = ["grade", "count"]
        fig2 = px.bar(
            gc_df, x="grade", y="count",
            color="grade", color_discrete_map=GRADE_C,
            labels={"grade": "Grade", "count": "Calls"}
        )
        fig2.update_layout(
            plot_bgcolor="#0d1320", paper_bgcolor="#0d1320",
            font_color="#e2e8f0", height=250,
            margin=dict(l=0, r=0, t=0, b=0), showlegend=False
        )
        fig2.update_xaxes(gridcolor="#1e293b")
        fig2.update_yaxes(gridcolor="#1e293b")
        st.plotly_chart(fig2, use_container_width=True)

    # Charts row 2
    ch3, ch4 = st.columns(2)

    with ch3:
        st.markdown("**Dimension Team Averages**")
        dim_keys   = ["empathy", "professionalism", "compliance", "resolution", "clarity"]
        dim_labels = ["Empathy", "Professionalism", "Compliance", "Resolution", "Clarity"]
        dim_avgs   = [df_f[k].mean() for k in dim_keys]

        fig3 = go.Figure(go.Bar(
            x            = dim_avgs,
            y            = dim_labels,
            orientation  = "h",
            marker_color = [score_color(v, 10) for v in dim_avgs],
            text         = [f"{v:.1f}/10" for v in dim_avgs],
            textposition = "outside",
        ))
        fig3.update_layout(
            plot_bgcolor="#0d1320", paper_bgcolor="#0d1320",
            font_color="#e2e8f0", xaxis_range=[0, 10],
            height=250, margin=dict(l=0, r=60, t=0, b=0)
        )
        fig3.update_xaxes(gridcolor="#1e293b")
        fig3.update_yaxes(gridcolor="#1e293b")
        st.plotly_chart(fig3, use_container_width=True)

    with ch4:
        st.markdown("**Score Trend**")
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(
            x    = list(range(1, len(df_f) + 1)),
            y    = df_f["score"].tolist(),
            mode = "lines+markers",
            line = dict(color="#38bdf8", width=2),
            marker = dict(
                color=[score_color(s) for s in df_f["score"]],
                size=8
            ),
            text          = df_f["filename"].tolist(),
            hovertemplate = "%{text}<br>Score: %{y}<extra></extra>"
        ))
        fig4.add_hline(
            y=60, line_dash="dash", line_color="#f59e0b",
            annotation_text="Pass (60)",
            annotation_font_color="#f59e0b"
        )
        fig4.update_layout(
            plot_bgcolor="#0d1320", paper_bgcolor="#0d1320",
            font_color="#e2e8f0", yaxis_range=[0, 100],
            height=250, margin=dict(l=0, r=0, t=0, b=0)
        )
        fig4.update_xaxes(gridcolor="#1e293b")
        fig4.update_yaxes(gridcolor="#1e293b")
        st.plotly_chart(fig4, use_container_width=True)

    # Violations severity pie
    st.divider()
    col_pie, col_lb = st.columns(2)

    with col_pie:
        st.markdown("**Violations by Severity**")
        sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for r in results:
            if r.get("_filename") not in df_f["filename"].values:
                continue
            for v in r.get("violations", []):
                sev = (v.get("severity") or "medium").lower()
                if sev in sev_counts:
                    sev_counts[sev] += 1

        sev_df = pd.DataFrame({
            "severity": list(sev_counts.keys()),
            "count":    list(sev_counts.values())
        })
        sev_colors = {
            "critical": "#f87171", "high":   "#fb923c",
            "medium":   "#f59e0b", "low":    "#94a3b8"
        }
        fig5 = px.pie(
            sev_df, names="severity", values="count",
            color="severity", color_discrete_map=sev_colors, hole=0.5
        )
        fig5.update_layout(
            plot_bgcolor="#0d1320", paper_bgcolor="#0d1320",
            font_color="#e2e8f0", height=250,
            margin=dict(l=0, r=0, t=0, b=0),
            legend=dict(orientation="v", font=dict(color="#e2e8f0"))
        )
        st.plotly_chart(fig5, use_container_width=True)

    with col_lb:
        st.markdown("**Outcome Breakdown**")
        oc_df = df_f["outcome"].value_counts().reset_index()
        oc_df.columns = ["outcome", "count"]
        fig6 = px.pie(
            oc_df, names="outcome", values="count",
            hole=0.5,
            color_discrete_sequence=["#22c55e", "#f87171", "#38bdf8", "#f59e0b"]
        )
        fig6.update_layout(
            plot_bgcolor="#0d1320", paper_bgcolor="#0d1320",
            font_color="#e2e8f0", height=250,
            margin=dict(l=0, r=0, t=0, b=0),
            legend=dict(orientation="v", font=dict(color="#e2e8f0"))
        )
        st.plotly_chart(fig6, use_container_width=True)

    st.divider()

    # Leaderboard
    st.markdown("### 🏆 Leaderboard")
    tab1, tab2 = st.tabs(["🔴 Worst 5 Calls", "🟢 Best 5 Calls"])

    with tab1:
        for _, row in df_f.nsmallest(5, "score").iterrows():
            gc = GRADE_C.get(row["grade"], "#64748b")
            st.markdown(
                f"<div style='background:#0d1320;border:1px solid #1e293b;"
                f"border-left:4px solid {gc};border-radius:8px;"
                f"padding:14px;margin-bottom:8px'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<span style='font-weight:600'>{row['filename']}</span>"
                f"<span style='color:{gc};font-weight:800'>"
                f"Grade {row['grade']} · {row['score']}/100</span></div>"
                f"<div style='color:#64748b;font-size:13px;margin-top:6px'>"
                f"Violations: {int(row['violations'])} · "
                f"Outcome: {row['outcome']} · "
                f"{str(row['issue'])[:80]}</div></div>",
                unsafe_allow_html=True
            )

    with tab2:
        for _, row in df_f.nlargest(5, "score").iterrows():
            gc = GRADE_C.get(row["grade"], "#64748b")
            st.markdown(
                f"<div style='background:#0d1320;border:1px solid #1e293b;"
                f"border-left:4px solid {gc};border-radius:8px;"
                f"padding:14px;margin-bottom:8px'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<span style='font-weight:600'>{row['filename']}</span>"
                f"<span style='color:{gc};font-weight:800'>"
                f"Grade {row['grade']} · {row['score']}/100</span></div>"
                f"<div style='color:#64748b;font-size:13px;margin-top:6px'>"
                f"Violations: {int(row['violations'])} · "
                f"Outcome: {row['outcome']}</div></div>",
                unsafe_allow_html=True
            )

    st.divider()

    # Full calls table
    st.markdown("### 📋 All Scored Calls")
    display_df = df_f[[
        "filename", "grade", "score", "sentiment", "outcome",
        "violations", "sat_rating", "empathy", "professionalism",
        "compliance", "resolution", "clarity"
    ]].copy()
    display_df.columns = [
        "File", "Grade", "Score", "Sentiment", "Outcome",
        "Violations", "Sat", "Empathy", "Prof",
        "Compliance", "Resolution", "Clarity"
    ]
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
            "Sat":   st.column_config.ProgressColumn("Sat",   min_value=0, max_value=5),
        }
    )

    # Violations detail table
    st.divider()
    st.markdown("### ⚠ All Violations")
    all_viols = []
    for r in results:
        if r.get("_filename") not in df_f["filename"].values:
            continue
        for v in r.get("violations", []):
            all_viols.append({
                "File":        r.get("_filename", ""),
                "Grade":       r.get("grade", "?"),
                "Score":       r.get("overall_score", 0),
                "Type":        (v.get("type") or "").replace("_", " ").title(),
                "Severity":    (v.get("severity") or "").upper(),
                "Explanation": str(v.get("explanation", ""))[:120],
            })
    if all_viols:
        st.dataframe(
            pd.DataFrame(all_viols),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
            }
        )
    else:
        st.success("No violations found ✓")


# ══════════════════════════════════════════════════════════
# PAGE 4 — REPORTS
# ══════════════════════════════════════════════════════════
elif page == "📋 Reports":
    st.markdown(
        "<h1>📋 <span style='color:#38bdf8'>Reports</span></h1>",
        unsafe_allow_html=True
    )

    results = load_results()

    if not results:
        st.warning("No results yet. Analyze some calls first.")
        st.stop()

    st.markdown(f"**{len(results)} scored calls available for export**")
    st.divider()

    # ── Excel export ───────────────────────────────────────
    st.markdown("### 📊 Excel Export — All Calls")
    st.caption("Exports all scored calls to Excel with 5 sheets: Summary, All Calls, Violations, Improvements, Agent Quality")

    if st.button("⬇ Generate Excel Report"):
        try:
            from reports.excel_report import generate_excel
            with st.spinner("Generating Excel..."):
                excel_bytes = generate_excel(str(RESULTS_DIR))
            fname = f"callaudit_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            st.download_button(
                label     = "⬇ Download Excel",
                data      = excel_bytes,
                file_name = fname,
                mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.success("✅ Excel ready — click Download Excel above")
        except Exception as e:
            st.error(f"Excel error: {e}")

    st.divider()

    # ── PDF per call ───────────────────────────────────────
    st.markdown("### 📄 PDF Report — Per Call")
    st.caption("Generate a detailed PDF report for any individual scored call")

    filenames = [r.get("_filename", "") for r in results if r.get("_filename")]
    if filenames:
        selected = st.selectbox("Select call", filenames)

        if st.button("⬇ Generate PDF"):
            try:
                from reports.pdf_report import generate_pdf
                target = next(
                    (x for x in results if x.get("_filename") == selected),
                    None
                )
                if target:
                    with st.spinner("Generating PDF..."):
                        pdf_bytes = generate_pdf(target, filename=selected)
                    pdf_name = selected.replace(".json", "_report.pdf")
                    st.download_button(
                        label     = f"⬇ Download {selected} PDF",
                        data      = pdf_bytes,
                        file_name = pdf_name,
                        mime      = "application/pdf",
                    )
                    st.success("✅ PDF ready — click download above")
            except Exception as e:
                st.error(f"PDF error: {e}")

    st.divider()

    # ── JSON export ────────────────────────────────────────
    st.markdown("### 📦 Raw JSON Export")
    st.caption("Download all scored results as a single JSON file")

    all_json = json.dumps(results, indent=2, ensure_ascii=False)
    st.download_button(
        label     = "⬇ Download All Results JSON",
        data      = all_json,
        file_name = f"callaudit_all_{datetime.now().strftime('%Y%m%d')}.json",
        mime      = "application/json",
    )

    st.divider()
    st.markdown(
        "<p style='text-align:center;color:#1e293b;font-size:12px'>"
        "CallAudit Pro · llama-3.3-70b · Groq · LangChain · RAG · Pinecone · Deepgram</p>",
        unsafe_allow_html=True
    )