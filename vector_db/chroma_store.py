# vector_db/chroma_store.py
"""
ChromaDB Vector Store
─────────────────────────────────────────────
Local persistent vector database.
Upgrade from FAISS — survives restarts, no rebuild needed.

Two collections:
  scored_calls  ← past scored call results
  knowledge_base ← KB policy rules

Usage:
  python vector_db/chroma_store.py --build
  python vector_db/chroma_store.py --stats
  python vector_db/chroma_store.py --search "agent refused escalation"
"""

import os
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faiss_search.embedder import embed_text

BASE_DIR    = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "analysis_results"
KB_FILE     = BASE_DIR / "knowledge_base" / "kb_store.json"
CHROMA_DIR  = str(BASE_DIR / "vector_db" / "chroma_db")

# ── Client ─────────────────────────────────────────────
_client          = None
_calls_col       = None
_kb_col          = None


def get_client():
    global _client
    if _client is None:
        import chromadb
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        print(f"  ✅ ChromaDB connected → chroma_db/")
    return _client


def get_calls_collection():
    global _calls_col
    if _calls_col is None:
        _calls_col = get_client().get_or_create_collection(
            name="scored_calls",
            metadata={"hnsw:space": "cosine"}
        )
    return _calls_col


def get_kb_collection():
    global _kb_col
    if _kb_col is None:
        _kb_col = get_client().get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )
    return _kb_col


# ══════════════════════════════════════════════════════
# BUILD INDEX
# ══════════════════════════════════════════════════════
def build_index():
    """
    Index all scored_*.json files + KB entries into ChromaDB.
    Safe to run multiple times — upsert will not duplicate.
    """
    print(f"\n{'='*55}")
    print(f"  Building ChromaDB index")
    print(f"{'='*55}")

    calls_col = get_calls_collection()
    kb_col    = get_kb_collection()

    # ── Index scored calls ─────────────────────────────
    files = sorted(RESULTS_DIR.glob("scored_*.json"))
    print(f"  Scored files : {len(files)}")

    call_count = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))

            text = (
                f"Grade: {data.get('grade','?')} "
                f"Score: {data.get('overall_score',0)} "
                f"Outcome: {data.get('call_outcome','')} "
                f"Issue: {data.get('issue_detected','')} "
                f"Summary: {data.get('summary','')}"
            )

            embedding = embed_text(text)

            calls_col.upsert(
                ids        = [f.stem],
                embeddings = [embedding],
                documents  = [text],
                metadatas  = [{
                    "source":        "scored_result",
                    "filename":      f.name,
                    "grade":         str(data.get("grade", "?")),
                    "overall_score": int(data.get("overall_score", 0)),
                    "issue":         str(data.get("issue_detected", ""))[:200],
                    "summary":       str(data.get("summary", ""))[:300],
                    "outcome":       str(data.get("call_outcome", "")),
                    "was_resolved":  str(data.get("was_resolved", False)),
                    "violations":    int(len(data.get("violations", []))),
                    "sentiment":     str(data.get("sentiment", "neutral")),
                }]
            )
            call_count += 1

        except Exception as e:
            print(f"  ⚠️  Skipped {f.name}: {e}")

    print(f"  Scored calls indexed : {call_count}")

    # ── Index KB entries ───────────────────────────────
    kb_count = 0
    if KB_FILE.exists():
        try:
            kb_entries = json.loads(KB_FILE.read_text(encoding="utf-8"))
            for entry in kb_entries:
                kb_text   = f"{entry.get('title','')} {entry.get('content','')}"
                embedding = embed_text(kb_text)

                kb_col.upsert(
                    ids        = [entry.get("id", f"kb_{kb_count}")],
                    embeddings = [embedding],
                    documents  = [kb_text],
                    metadatas  = [{
                        "source":   "knowledge_base",
                        "kb_id":    str(entry.get("id", "")),
                        "title":    str(entry.get("title", "")),
                        "content":  str(entry.get("content", ""))[:500],
                        "severity": str(entry.get("severity", "info")),
                        "tags":     str(entry.get("tags", "")),
                    }]
                )
                kb_count += 1

        except Exception as e:
            print(f"  ⚠️  KB indexing failed: {e}")
    else:
        print(f"  ⚠️  kb_store.json not found")
        print(f"     Run: python knowledge_base/kb_loader.py")

    print(f"  KB entries indexed   : {kb_count}")
    print(f"\n  ✅ ChromaDB index built")
    print(f"     Location: {CHROMA_DIR}")
    print(f"{'='*55}\n")


# ══════════════════════════════════════════════════════
# SEARCH
# ══════════════════════════════════════════════════════
def search_similar_calls(query_text: str, top_k: int = 3) -> list:
    """Search only scored call results."""
    try:
        col       = get_calls_collection()
        embedding = embed_text(query_text)

        results = col.query(
            query_embeddings = [embedding],
            n_results        = min(top_k, col.count() or 1),
            include          = ["metadatas", "distances", "documents"]
        )

        hits = []
        for meta, dist in zip(
            results["metadatas"][0],
            results["distances"][0]
        ):
            hits.append({
                **meta,
                "similarity": round(1 - dist, 4)
            })
        return hits

    except Exception as e:
        print(f"  ⚠️  ChromaDB calls search failed: {e}")
        return []


def search_kb(query_text: str, top_k: int = 3) -> list:
    """Search only KB policy rule entries."""
    try:
        col       = get_kb_collection()
        embedding = embed_text(query_text)

        results = col.query(
            query_embeddings = [embedding],
            n_results        = min(top_k, col.count() or 1),
            include          = ["metadatas", "distances", "documents"]
        )

        hits = []
        for meta, dist in zip(
            results["metadatas"][0],
            results["distances"][0]
        ):
            hits.append({
                **meta,
                "similarity": round(1 - dist, 4)
            })
        return hits

    except Exception as e:
        print(f"  ⚠️  ChromaDB KB search failed: {e}")
        return []


# ══════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════
def index_stats() -> dict:
    try:
        calls = get_calls_collection().count()
        kb    = get_kb_collection().count()
        return {
            "scored_calls": calls,
            "kb_entries":   kb,
            "total":        calls + kb,
            "location":     CHROMA_DIR,
        }
    except Exception as e:
        return {"error": str(e)}


def clear_index():
    """Delete all vectors — use with caution."""
    try:
        client = get_client()
        client.delete_collection("scored_calls")
        client.delete_collection("knowledge_base")
        global _calls_col, _kb_col
        _calls_col = None
        _kb_col    = None
        print("  ✅ ChromaDB index cleared")
    except Exception as e:
        print(f"  ⚠️  Clear failed: {e}")


# ══════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChromaDB vector store")
    parser.add_argument("--build",  action="store_true", help="Build index")
    parser.add_argument("--stats",  action="store_true", help="Show stats")
    parser.add_argument("--clear",  action="store_true", help="Clear index")
    parser.add_argument("--search", type=str,            help="Search query")
    args = parser.parse_args()

    if args.build:
        build_index()

    elif args.stats:
        s = index_stats()
        print(f"\n{'='*45}")
        print(f"  ChromaDB Stats")
        print(f"{'='*45}")
        print(f"  Scored calls : {s.get('scored_calls', 0)}")
        print(f"  KB entries   : {s.get('kb_entries', 0)}")
        print(f"  Total        : {s.get('total', 0)}")
        print(f"  Location     : {s.get('location', '')}")
        print(f"{'='*45}\n")

    elif args.clear:
        clear_index()

    elif args.search:
        print(f"\nSearching calls: '{args.search}'")
        results = search_similar_calls(args.search, top_k=3)
        print(f"Top {len(results)} similar calls:")
        for r in results:
            print(f"  [{r.get('grade','?')}] "
                  f"Score:{r.get('overall_score',0)} | "
                  f"Similarity:{r.get('similarity',0)} | "
                  f"{str(r.get('issue',''))[:60]}")

        print(f"\nSearching KB: '{args.search}'")
        kb_results = search_kb(args.search, top_k=3)
        print(f"Top {len(kb_results)} KB rules:")
        for r in kb_results:
            print(f"  [{r.get('severity','?').upper()}] "
                  f"{r.get('title','')} | "
                  f"Similarity:{r.get('similarity',0)}")
    else:
        parser.print_help()