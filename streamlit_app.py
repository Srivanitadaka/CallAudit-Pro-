# streamlit_app.py
"""
CallAudit Pro — Supervisor Dashboard
─────────────────────────────────────────────
Streamlit dashboard for supervisors/managers.
Shows team performance, trends, violations, leaderboard.

Run:
  streamlit run streamlit_app.py
"""

import json
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ── Config ─────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "analysis_results"

st.set_page_config(
    page_title = "CallAudit Pro — Supervisor",
    page_icon  = "🎧",
    layout     = "wide",
    initial_sidebar_state = "expanded"
)

# ── Custom CSS ──────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] {
    background-color: #080c14;
    color: #e2e8f0;
  }
  [data-testid="stSidebar"] {
    background-color: #0d1320;
    border-right: 1px solid #1e293b;
  }
  .metric-card {
    background: #0d1320;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
  }
  .metric-val {
    font-size: 36px;
    font-weight: 800;
    line-height: 1;
  }
  .metric-lbl {
    font-size: 12px;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 6px;
  }
  .viol-card {
    background: rgba(248,113,113,0.08);
    border-left: 4px solid #f87171;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }
  .viol-card-high {
    background: rgba(251,146,60,0.08);
    border-left: 4px solid #fb923c;
  }
  .viol-card-medium {
    background: rgba(245,158,11,0.08);
    border-left: 4px solid #f59e0b;
  }
  .highlight-card {
    background: rgba(34,197,94,0.08);
    border-left: 4px solid #22c55e;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }
  div[data-testid="metric-container"] {
    background: #0d1320;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 16px;
  }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════
@st.cache_data(ttl=30)
def load_all_results() -> list:
    results = []
    for f in sorted(RESULTS_DIR.glob("scored_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_filename"] = f.name
            results.append(data)
        except Exception:
            pass
    return results


def to_dataframe(results: list) -> pd.DataFrame:
    rows = []
    for r in results:
        dims = r.get("dimension_scores", r.get("scores", {}))
        aq   = r.get("agent_quality", {})
        sat  = r.get("satisfaction", {})
        rows.append({
            "filename":       r.get("_filename", ""),
            "grade":          r.get("grade", "?"),
            "score":          r.get("overall_score", 0),
            "sentiment":      r.get("sentiment", "neutral"),
            "outcome":        r.get("call_outcome", "Unknown"),
            "resolved":       r.get("was_resolved", False),
            "violations":     len(r.get("violations", [])),
            "issue":          r.get("issue_detected", ""),
            "summary":        r.get("summary", ""),
            "empathy":        dims.get("empathy", 0),
            "professionalism":dims.get("professionalism", 0),
            "compliance":     dims.get("compliance", 0),
            "resolution":     dims.get("resolution_effectiveness", 0),
            "clarity":        dims.get("communication_clarity", 0),
            "sat_rating":     sat.get("rating", 0),
            "frustration":    sat.get("customer_frustration", "None"),
            "lang_clarity":   aq.get("language_clarity", 0),
            "prof_score":     aq.get("professionalism", 0),
            "time_eff":       aq.get("time_efficiency", 0),
            "resp_eff":       aq.get("response_efficiency", 0),
            "empathy_score":  aq.get("empathy_score", 0),
        })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════
# COLOUR HELPERS
# ══════════════════════════════════════════════════════
GRADE_C = {"A":"#22c55e","B":"#38bdf8","C":"#f59e0b","D":"#fb923c","F":"#f87171"}

def score_color(v, mx=100):
    p = v / mx
    if p >= 0.75: return "#22c55e"
    if p >= 0.55: return "#f59e0b"
    return "#f87171"


# ══════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🎧 CallAudit Pro")
    st.markdown("**Supervisor Dashboard**")
    st.divider()

    results = load_all_results()

    if not results:
        st.warning("No scored calls found.\nRun batch_scorer.py first.")
        st.stop()

    df = to_dataframe(results)

    st.markdown(f"**{len(df)} calls loaded**")
    st.divider()

    # Filters
    st.markdown("### Filters")
    grade_filter = st.multiselect(
        "Grade",
        options = ["A","B","C","D","F"],
        default = ["A","B","C","D","F"]
    )
    outcome_filter = st.multiselect(
        "Outcome",
        options = df["outcome"].unique().tolist(),
        default = df["outcome"].unique().tolist()
    )
    min_score, max_score = st.slider(
        "Score range",
        min_value = 0,
        max_value = 100,
        value     = (0, 100)
    )

    st.divider()
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# Apply filters
df_f = df[
    df["grade"].isin(grade_filter) &
    df["outcome"].isin(outcome_filter) &
    df["score"].between(min_score, max_score)
]

if df_f.empty:
    st.warning("No results match your filters.")
    st.stop()


# ══════════════════════════════════════════════════════
# MAIN HEADER
# ══════════════════════════════════════════════════════
st.markdown(
    "<h1 style='font-size:32px;font-weight:800;margin-bottom:4px'>"
    "CallAudit Pro <span style='color:#38bdf8'>Supervisor</span></h1>",
    unsafe_allow_html=True
)
st.markdown(
    f"<p style='color:#64748b;margin-bottom:24px'>"
    f"Showing {len(df_f)} of {len(df)} scored conversations</p>",
    unsafe_allow_html=True
)


# ══════════════════════════════════════════════════════
# SECTION 1 — KPI CARDS
# ══════════════════════════════════════════════════════
st.markdown("### 📊 Team Overview")
c1, c2, c3, c4, c5, c6 = st.columns(6)

avg_score  = df_f["score"].mean()
pass_rate  = (df_f["score"] >= 60).sum() / len(df_f) * 100
total_viol = df_f["violations"].sum()
resolved   = df_f["resolved"].sum()
avg_sat    = df_f["sat_rating"].mean()
grade_f    = (df_f["grade"] == "F").sum()

c1.metric("Avg Score",      f"{avg_score:.1f}/100")
c2.metric("Pass Rate ≥60",  f"{pass_rate:.0f}%")
c3.metric("Total Violations", int(total_viol))
c4.metric("Resolved",       int(resolved))
c5.metric("Avg Satisfaction", f"{avg_sat:.1f}/5")
c6.metric("Grade F Calls",  int(grade_f))

st.divider()


# ══════════════════════════════════════════════════════
# SECTION 2 — CHARTS ROW 1
# ══════════════════════════════════════════════════════
st.markdown("### 📈 Performance Analysis")
col1, col2 = st.columns(2)

with col1:
    st.markdown("**Score Distribution**")
    fig = px.histogram(
        df_f, x="score", nbins=10,
        color_discrete_sequence=["#38bdf8"],
        labels={"score": "Score", "count": "Calls"}
    )
    fig.update_layout(
        plot_bgcolor  = "#0d1320",
        paper_bgcolor = "#0d1320",
        font_color    = "#e2e8f0",
        bargap        = 0.1,
        margin        = dict(l=0, r=0, t=0, b=0),
        height        = 280,
        showlegend    = False,
    )
    fig.update_xaxes(gridcolor="#1e293b")
    fig.update_yaxes(gridcolor="#1e293b")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown("**Grade Breakdown**")
    grade_counts = df_f["grade"].value_counts().reset_index()
    grade_counts.columns = ["grade", "count"]
    grade_counts["color"] = grade_counts["grade"].map(GRADE_C)
    fig2 = px.bar(
        grade_counts, x="grade", y="count",
        color="grade",
        color_discrete_map=GRADE_C,
        labels={"grade": "Grade", "count": "Calls"}
    )
    fig2.update_layout(
        plot_bgcolor  = "#0d1320",
        paper_bgcolor = "#0d1320",
        font_color    = "#e2e8f0",
        margin        = dict(l=0, r=0, t=0, b=0),
        height        = 280,
        showlegend    = False,
    )
    fig2.update_xaxes(gridcolor="#1e293b")
    fig2.update_yaxes(gridcolor="#1e293b")
    st.plotly_chart(fig2, use_container_width=True)

st.divider()


# ══════════════════════════════════════════════════════
# SECTION 3 — CHARTS ROW 2
# ══════════════════════════════════════════════════════
col3, col4 = st.columns(2)

with col3:
    st.markdown("**Dimension Scores — Team Average**")
    dims = ["empathy","professionalism","compliance","resolution","clarity"]
    avgs = [df_f[d].mean() for d in dims]
    labels = ["Empathy","Professionalism","Compliance","Resolution","Clarity"]
    colors = [score_color(v, 10) for v in avgs]

    fig3 = go.Figure(go.Bar(
        x      = avgs,
        y      = labels,
        orientation = "h",
        marker_color = colors,
        text   = [f"{v:.1f}/10" for v in avgs],
        textposition = "outside",
    ))
    fig3.update_layout(
        plot_bgcolor  = "#0d1320",
        paper_bgcolor = "#0d1320",
        font_color    = "#e2e8f0",
        xaxis_range   = [0, 10],
        margin        = dict(l=0, r=60, t=0, b=0),
        height        = 280,
    )
    fig3.update_xaxes(gridcolor="#1e293b")
    fig3.update_yaxes(gridcolor="#1e293b")
    st.plotly_chart(fig3, use_container_width=True)

with col4:
    st.markdown("**Violations by Severity**")
    sev_counts = {"critical":0, "high":0, "medium":0, "low":0}
    for r in results:
        if r.get("_filename") not in df_f["filename"].values:
            continue
        for v in r.get("violations", []):
            sev = v.get("severity", "medium").lower()
            if sev in sev_counts:
                sev_counts[sev] += 1

    sev_df = pd.DataFrame({
        "severity": list(sev_counts.keys()),
        "count":    list(sev_counts.values())
    })
    sev_colors = {
        "critical": "#f87171",
        "high":     "#fb923c",
        "medium":   "#f59e0b",
        "low":      "#94a3b8"
    }
    fig4 = px.pie(
        sev_df, names="severity", values="count",
        color="severity",
        color_discrete_map=sev_colors,
        hole=0.5
    )
    fig4.update_layout(
        plot_bgcolor  = "#0d1320",
        paper_bgcolor = "#0d1320",
        font_color    = "#e2e8f0",
        margin        = dict(l=0, r=0, t=0, b=0),
        height        = 280,
        legend        = dict(
            orientation = "v",
            font        = dict(color="#e2e8f0")
        )
    )
    st.plotly_chart(fig4, use_container_width=True)

st.divider()


# ══════════════════════════════════════════════════════
# SECTION 4 — SCORE TREND
# ══════════════════════════════════════════════════════
st.markdown("### 📉 Score Trend Across Calls")
fig5 = go.Figure()
fig5.add_trace(go.Scatter(
    x    = list(range(1, len(df_f)+1)),
    y    = df_f["score"].tolist(),
    mode = "lines+markers",
    line = dict(color="#38bdf8", width=2),
    marker = dict(
        color = [score_color(s) for s in df_f["score"]],
        size  = 8
    ),
    text      = df_f["filename"].tolist(),
    hovertemplate = "%{text}<br>Score: %{y}<extra></extra>"
))
fig5.add_hline(
    y=60, line_dash="dash",
    line_color="#f59e0b",
    annotation_text="Pass threshold (60)",
    annotation_font_color="#f59e0b"
)
fig5.update_layout(
    plot_bgcolor  = "#0d1320",
    paper_bgcolor = "#0d1320",
    font_color    = "#e2e8f0",
    margin        = dict(l=0, r=0, t=20, b=0),
    height        = 260,
    xaxis_title   = "Call #",
    yaxis_title   = "Score",
    yaxis_range   = [0, 100],
)
fig5.update_xaxes(gridcolor="#1e293b")
fig5.update_yaxes(gridcolor="#1e293b")
st.plotly_chart(fig5, use_container_width=True)

st.divider()


# ══════════════════════════════════════════════════════
# SECTION 5 — LEADERBOARD
# ══════════════════════════════════════════════════════
st.markdown("### 🏆 Call Leaderboard")

tab1, tab2 = st.tabs(["🔴 Worst Calls", "🟢 Best Calls"])

with tab1:
    worst = df_f.nsmallest(5, "score")
    for _, row in worst.iterrows():
        gc = GRADE_C.get(row["grade"], "#64748b")
        st.markdown(
            f"<div style='background:#0d1320;border:1px solid #1e293b;"
            f"border-left:4px solid {gc};border-radius:8px;"
            f"padding:14px;margin-bottom:8px'>"
            f"<div style='display:flex;justify-content:space-between'>"
            f"<span style='font-weight:600'>{row['filename']}</span>"
            f"<span style='color:{gc};font-weight:800;font-size:18px'>"
            f"Grade {row['grade']} · {row['score']}/100</span></div>"
            f"<div style='color:#64748b;font-size:13px;margin-top:6px'>"
            f"Violations: {int(row['violations'])} · "
            f"Outcome: {row['outcome']} · "
            f"Issue: {row['issue'][:80]}</div></div>",
            unsafe_allow_html=True
        )

with tab2:
    best = df_f.nlargest(5, "score")
    for _, row in best.iterrows():
        gc = GRADE_C.get(row["grade"], "#64748b")
        st.markdown(
            f"<div style='background:#0d1320;border:1px solid #1e293b;"
            f"border-left:4px solid {gc};border-radius:8px;"
            f"padding:14px;margin-bottom:8px'>"
            f"<div style='display:flex;justify-content:space-between'>"
            f"<span style='font-weight:600'>{row['filename']}</span>"
            f"<span style='color:{gc};font-weight:800;font-size:18px'>"
            f"Grade {row['grade']} · {row['score']}/100</span></div>"
            f"<div style='color:#64748b;font-size:13px;margin-top:6px'>"
            f"Violations: {int(row['violations'])} · "
            f"Outcome: {row['outcome']} · "
            f"Issue: {row['issue'][:80]}</div></div>",
            unsafe_allow_html=True
        )

st.divider()


# ══════════════════════════════════════════════════════
# SECTION 6 — VIOLATIONS TABLE
# ══════════════════════════════════════════════════════
st.markdown("### ⚠️ All Violations Detected")

all_viols = []
for r in results:
    if r.get("_filename") not in df_f["filename"].values:
        continue
    for v in r.get("violations", []):
        all_viols.append({
            "File":        r.get("_filename", ""),
            "Grade":       r.get("grade", "?"),
            "Score":       r.get("overall_score", 0),
            "Type":        v.get("type", "").replace("_"," ").title(),
            "Severity":    v.get("severity", "").upper(),
            "Quote":       v.get("quote", "")[:80],
            "Explanation": v.get("explanation", "")[:100],
        })

if all_viols:
    viol_df = pd.DataFrame(all_viols)
    st.dataframe(
        viol_df,
        use_container_width = True,
        hide_index          = True,
        column_config       = {
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100
            ),
            "Severity": st.column_config.TextColumn("Severity"),
        }
    )
else:
    st.success("No violations found in filtered results ✓")

st.divider()


# ══════════════════════════════════════════════════════
# SECTION 7 — FULL RESULTS TABLE
# ══════════════════════════════════════════════════════
st.markdown("### 📋 All Scored Calls")

display_df = df_f[[
    "filename","grade","score","sentiment",
    "outcome","violations","sat_rating",
    "empathy","professionalism","compliance",
    "resolution","clarity"
]].copy()

display_df.columns = [
    "File","Grade","Score","Sentiment",
    "Outcome","Violations","Sat Rating",
    "Empathy","Prof","Compliance",
    "Resolution","Clarity"
]

st.dataframe(
    display_df,
    use_container_width = True,
    hide_index          = True,
    column_config       = {
        "Score": st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100
        ),
        "Sat Rating": st.column_config.ProgressColumn(
            "Sat Rating", min_value=0, max_value=5
        ),
    }
)

st.divider()

# ── Footer ──────────────────────────────────────────────
st.markdown(
    "<p style='text-align:center;color:#1e293b;font-size:12px'>"
    "CallAudit Pro · Supervisor Dashboard · "
    "llama-3.3-70b · Groq · LangChain · RAG</p>",
    unsafe_allow_html=True
)