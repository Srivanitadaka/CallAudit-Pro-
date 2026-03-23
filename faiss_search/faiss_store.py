# faiss_search/faiss_store.py

import json
import faiss
import numpy as np
from pathlib import Path
import sys
import os

# ── Path fix — works from any location ────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from faiss_search.embedder import embed_text

# ── Paths ──────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "analysis_results"
INDEX_FILE  = BASE_DIR / "faiss_search" / "callaudit.index"
META_FILE   = BASE_DIR / "faiss_search" / "callaudit_meta.json"
KB_DIR      = BASE_DIR / "knowledge_base"

VECTOR_DIM  = 384

# ── Internal state ─────────────────────────────────────────
_index    = None
_metadata = None


# ══════════════════════════════════════════════════════════
# BUILD TEXT FROM SCORED JSON
# ══════════════════════════════════════════════════════════
def build_record_text(data: dict) -> str:
    """
    Converts a scored_*.json into a rich searchable
    text string for embedding.
    More fields = better semantic search results.
    """
    parts = []

    parts.append(f"Grade: {data.get('grade', '?')}")
    parts.append(f"Score: {data.get('overall_score', 0)}/100")
    parts.append(f"Outcome: {data.get('call_outcome', 'Unknown')}")
    parts.append(f"Issue: {data.get('issue_detected', '')}")
    parts.append(f"Summary: {data.get('summary', '')}")

    # Dimension scores
    dims = data.get("dimension_scores", data.get("scores", {}))
    if dims:
        dim_parts = [f"{k.replace('_',' ')}: {v}" for k, v in dims.items()]
        parts.append("Dimensions: " + ", ".join(dim_parts))

    # Violations
    violations = data.get("violations", [])
    if violations:
        v_text = " | ".join([
            f"{v.get('type','')} [{v.get('severity','')}]"
            for v in violations
        ])
        parts.append(f"Violations: {v_text}")

    # Improvements
    improvements = data.get("improvements", [])
    if improvements:
        i_text = " | ".join([
            f"{i.get('area','')}: {i.get('suggestion','')[:80]}"
            for i in improvements
        ])
        parts.append(f"Improvements: {i_text}")

    # Highlights
    highlights = data.get("highlights", [])
    if highlights:
        parts.append("Highlights: " + " | ".join(highlights))

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════
# BUILD INDEX
# ══════════════════════════════════════════════════════════
def build_index():
    """
    Reads all analysis_results/scored_*.json files,
    embeds them with BGE model,
    and saves a FAISS index to disk.

    Run this after batch_scorer.py finishes.
    Also indexes Knowledge Base entries if available.
    """
    files = sorted(RESULTS_DIR.glob("scored_*.json"))

    if not files:
        print("❌ No scored files found in analysis_results/")
        print("   Run: python llm/batch_scorer.py first")
        return

    print(f"\n{'='*55}")
    print(f"  Building FAISS index")
    print(f"{'='*55}")
    print(f"  Scored files : {len(files)}")

    texts    = []
    metadata = []

    # ── Index scored results ───────────────────────────────
    for f in files:
        try:
            data      = json.loads(f.read_text(encoding="utf-8"))
            text      = build_record_text(data)
            texts.append(text)
            metadata.append({
                "source":        "scored_result",
                "filename":      f.name,
                "grade":         data.get("grade", "?"),
                "overall_score": data.get("overall_score", 0),
                "issue":         data.get("issue_detected", ""),
                "summary":       data.get("summary", ""),
                "outcome":       data.get("call_outcome", ""),
                "was_resolved":  data.get("was_resolved", False),
                "violations":    len(data.get("violations", [])),
                "sentiment":     data.get("sentiment", "neutral"),
            })
        except Exception as e:
            print(f"  ⚠️  Skipped {f.name}: {e}")

    # ── Index Knowledge Base entries ───────────────────────
    kb_file = KB_DIR / "kb_store.json"
    if kb_file.exists():
        try:
            kb_entries = json.loads(kb_file.read_text(encoding="utf-8"))
            for entry in kb_entries:
                kb_text = f"{entry.get('title','')} {entry.get('content','')}"
                texts.append(kb_text)
                metadata.append({
                    "source":   "knowledge_base",
                    "filename": entry.get("id", ""),
                    "grade":    "KB",
                    "overall_score": 0,
                    "issue":    entry.get("title", ""),
                    "summary":  entry.get("content", "")[:200],
                    "outcome":  entry.get("severity", ""),
                    "was_resolved": False,
                    "violations": 0,
                    "sentiment": "neutral",
                })
            print(f"  KB entries   : {len(kb_entries)}")
        except Exception as e:
            print(f"  ⚠️  KB indexing skipped: {e}")
    else:
        print(f"  KB entries   : 0 (run kb_loader.py first)")

    print(f"  Total records: {len(texts)}")
    print(f"\n  Embedding with BGE model...")

    # ── Embed all texts ────────────────────────────────────
    vectors = np.array(
        [embed_text(t) for t in texts],
        dtype=np.float32
    )

    # ── Build and save FAISS index ─────────────────────────
    index = faiss.IndexFlatIP(VECTOR_DIM)
    index.add(vectors)

    faiss.write_index(index, str(INDEX_FILE))
    META_FILE.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"\n  ✅ Index built: {index.ntotal} vectors")
    print(f"  Saved: {INDEX_FILE.name}")
    print(f"  Meta:  {META_FILE.name}")
    print(f"{'='*55}\n")


# ══════════════════════════════════════════════════════════
# LOAD INDEX
# ══════════════════════════════════════════════════════════
def load_index() -> bool:
    """Load FAISS index and metadata from disk."""
    global _index, _metadata

    if not INDEX_FILE.exists():
        print("❌ Index not found. Run: python faiss_search/faiss_store.py")
        return False

    _index    = faiss.read_index(str(INDEX_FILE))
    _metadata = json.loads(META_FILE.read_text(encoding="utf-8"))
    print(f"  ✅ Index loaded: {_index.ntotal} vectors")
    return True


# ══════════════════════════════════════════════════════════
# SEARCH
# ══════════════════════════════════════════════════════════
def search(
    query_text: str,
    top_k: int = 3,
    source_filter: str = None
) -> list:
    """
    Find top_k most similar past calls to a query text.

    query_text   : the transcript or any search string
    top_k        : number of results to return
    source_filter: 'scored_result' | 'knowledge_base' | None (all)

    Returns list of dicts with similarity score added.
    """
    global _index, _metadata

    # Load index if not already loaded
    if _index is None:
        if not load_index():
            return []

    # Embed the query
    q_vec = np.array(
        [embed_text(query_text)],
        dtype=np.float32
    )

    # Fetch more than top_k so we can filter
    fetch_k  = min(_index.ntotal, top_k * 3)
    scores, indices = _index.search(q_vec, fetch_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue

        meta = _metadata[idx]

        # Apply source filter if given
        if source_filter and meta.get("source") != source_filter:
            continue

        results.append({
            **meta,
            "similarity": round(float(score), 4)
        })

        if len(results) >= top_k:
            break

    return results


# ══════════════════════════════════════════════════════════
# HELPER SEARCH FUNCTIONS
# ══════════════════════════════════════════════════════════
def search_similar_calls(query_text: str, top_k: int = 3) -> list:
    """Search only scored call results — not KB entries."""
    return search(query_text, top_k=top_k, source_filter="scored_result")


def search_kb(query_text: str, top_k: int = 3) -> list:
    """Search only Knowledge Base entries."""
    return search(query_text, top_k=top_k, source_filter="knowledge_base")


def index_stats() -> dict:
    """Return stats about the current index."""
    global _index, _metadata
    if _index is None:
        load_index()
    if _metadata is None:
        return {"total_vectors": 0}

    scored = sum(1 for m in _metadata if m.get("source") == "scored_result")
    kb     = sum(1 for m in _metadata if m.get("source") == "knowledge_base")

    return {
        "total_vectors":  _index.ntotal if _index else 0,
        "scored_results": scored,
        "kb_entries":     kb,
        "index_file":     str(INDEX_FILE),
    }


# ══════════════════════════════════════════════════════════
# RUN DIRECTLY — builds the index
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    build_index()

    # Quick search test after building
    print("Running search test...")
    results = search_similar_calls("agent was rude and refused to escalate", top_k=3)
    print(f"\nTop {len(results)} results:")
    for r in results:
        print(f"  [{r['grade']}] Score:{r['overall_score']} | "
              f"Similarity:{r['similarity']} | "
              f"{r['issue'][:60]}")