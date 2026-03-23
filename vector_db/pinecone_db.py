# vector_db/pinecone_store.py
"""
Pinecone Vector Store
─────────────────────────────────────────────
Cloud vector database. Survives deployment.
Use this when deploying to cloud (Render, Railway).

Two namespaces:
  scored_calls   ← past scored call results
  knowledge_base ← KB policy rules

Usage:
  python vector_db/pinecone_store.py --build
  python vector_db/pinecone_store.py --stats
  python vector_db/pinecone_store.py --search "agent refused escalation"
"""

import os
import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "config" / ".env")

from faiss_search.embedder import embed_text

BASE_DIR    = ROOT
RESULTS_DIR = BASE_DIR / "analysis_results"
KB_FILE     = BASE_DIR / "knowledge_base" / "kb_store.json"

API_KEY     = os.getenv("PINECONE_API_KEY", "")
INDEX_NAME  = os.getenv("PINECONE_INDEX", "callaudit")
DIMENSION   = 384        # BGE-small-en-v1.5 output size
METRIC      = "cosine"

# ── Client ─────────────────────────────────────────────
_index = None


def get_index():
    global _index
    if _index is not None:
        return _index

    if not API_KEY:
        raise ValueError(
            "PINECONE_API_KEY not found.\n"
            "Add it to config/.env:\n"
            "  PINECONE_API_KEY=your_key_here"
        )

    from pinecone import Pinecone, ServerlessSpec

    pc = Pinecone(api_key=API_KEY)

    # Create index if it does not exist
    existing = [i.name for i in pc.list_indexes()]
    if INDEX_NAME not in existing:
        print(f"  Creating Pinecone index '{INDEX_NAME}'...")
        pc.create_index(
            name      = INDEX_NAME,
            dimension = DIMENSION,
            metric    = METRIC,
            spec      = ServerlessSpec(
                cloud  = "aws",
                region = "us-east-1"
            )
        )
        print(f"  ✅ Index '{INDEX_NAME}' created")
    else:
        print(f"  ✅ Index '{INDEX_NAME}' already exists")

    _index = pc.Index(INDEX_NAME)
    return _index


# ══════════════════════════════════════════════════════
# BUILD INDEX
# ══════════════════════════════════════════════════════
def build_index():
    print(f"\n{'='*55}")
    print(f"  Building Pinecone index")
    print(f"{'='*55}")

    idx = get_index()

    # ── Index scored calls ─────────────────────────────
    files = sorted(RESULTS_DIR.glob("scored_*.json"))
    print(f"  Scored files : {len(files)}")

    call_vectors = []
    for f in files:
        try:
            data      = json.loads(f.read_text(encoding="utf-8"))
            text      = (
                f"Grade: {data.get('grade','?')} "
                f"Score: {data.get('overall_score',0)} "
                f"Outcome: {data.get('call_outcome','')} "
                f"Issue: {data.get('issue_detected','')} "
                f"Summary: {data.get('summary','')}"
            )
            embedding = embed_text(text)

            call_vectors.append({
                "id":     f.stem,
                "values": embedding,
                "metadata": {
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
                }
            })

        except Exception as e:
            print(f"  ⚠️  Skipped {f.name}: {e}")

    # Upsert in batches of 100
    if call_vectors:
        for i in range(0, len(call_vectors), 100):
            batch = call_vectors[i:i+100]
            idx.upsert(vectors=batch, namespace="scored_calls")
        print(f"  Scored calls indexed : {len(call_vectors)}")

    # ── Index KB entries ───────────────────────────────
    kb_vectors = []
    if KB_FILE.exists():
        try:
            kb_entries = json.loads(KB_FILE.read_text(encoding="utf-8"))
            for entry in kb_entries:
                kb_text   = f"{entry.get('title','')} {entry.get('content','')}"
                embedding = embed_text(kb_text)

                kb_vectors.append({
                    "id":     str(entry.get("id", f"kb_{len(kb_vectors)}")),
                    "values": embedding,
                    "metadata": {
                        "source":   "knowledge_base",
                        "kb_id":    str(entry.get("id", "")),
                        "title":    str(entry.get("title", "")),
                        "content":  str(entry.get("content", ""))[:500],
                        "severity": str(entry.get("severity", "info")),
                        "tags":     str(entry.get("tags", "")),
                    }
                })

        except Exception as e:
            print(f"  ⚠️  KB indexing failed: {e}")

    if kb_vectors:
        for i in range(0, len(kb_vectors), 100):
            batch = kb_vectors[i:i+100]
            idx.upsert(vectors=batch, namespace="knowledge_base")
        print(f"  KB entries indexed   : {len(kb_vectors)}")
    else:
        print(f"  ⚠️  No KB entries found")

    print(f"\n  ✅ Pinecone index built")
    print(f"     Index : {INDEX_NAME}")
    print(f"{'='*55}\n")


# ══════════════════════════════════════════════════════
# SEARCH
# ══════════════════════════════════════════════════════
def search_similar_calls(query_text: str, top_k: int = 3) -> list:
    """Search only scored call results namespace."""
    try:
        idx       = get_index()
        embedding = embed_text(query_text)

        results = idx.query(
            vector    = embedding,
            top_k     = top_k,
            namespace = "scored_calls",
            include_metadata = True
        )

        hits = []
        for match in results.matches:
            hits.append({
                **match.metadata,
                "similarity": round(match.score, 4)
            })
        return hits

    except Exception as e:
        print(f"  ⚠️  Pinecone calls search failed: {e}")
        return []


def search_kb(query_text: str, top_k: int = 3) -> list:
    """Search only knowledge base namespace."""
    try:
        idx       = get_index()
        embedding = embed_text(query_text)

        results = idx.query(
            vector    = embedding,
            top_k     = top_k,
            namespace = "knowledge_base",
            include_metadata = True
        )

        hits = []
        for match in results.matches:
            hits.append({
                **match.metadata,
                "similarity": round(match.score, 4)
            })
        return hits

    except Exception as e:
        print(f"  ⚠️  Pinecone KB search failed: {e}")
        return []


# ══════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════
def index_stats() -> dict:
    try:
        idx   = get_index()
        stats = idx.describe_index_stats()

        namespaces = stats.namespaces or {}
        calls = namespaces.get("scored_calls",    {}).get("vector_count", 0)
        kb    = namespaces.get("knowledge_base",  {}).get("vector_count", 0)

        return {
            "scored_calls": calls,
            "kb_entries":   kb,
            "total":        calls + kb,
            "index_name":   INDEX_NAME,
            "dimension":    DIMENSION,
        }
    except Exception as e:
        return {"error": str(e)}


def clear_index():
    """Delete all vectors from both namespaces."""
    try:
        idx = get_index()
        idx.delete(delete_all=True, namespace="scored_calls")
        idx.delete(delete_all=True, namespace="knowledge_base")
        print("  ✅ Pinecone index cleared")
    except Exception as e:
        print(f"  ⚠️  Clear failed: {e}")


# ══════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pinecone vector store")
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
        print(f"  Pinecone Stats")
        print(f"{'='*45}")
        print(f"  Scored calls : {s.get('scored_calls', 0)}")
        print(f"  KB entries   : {s.get('kb_entries', 0)}")
        print(f"  Total        : {s.get('total', 0)}")
        print(f"  Index name   : {s.get('index_name', '')}")
        print(f"  Dimension    : {s.get('dimension', 0)}")
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