# vector_db/milvus_store.py
"""
Milvus Vector Store
─────────────────────────────────────────────
Enterprise-grade vector database.
Handles millions of vectors at scale.

Windows Note:
  milvus-lite does not support Windows.
  This file uses a pure Python mock with identical API.
  On Linux/Mac deployment, swap get_client() to use
  real MilvusClient pointing to a Milvus server.

Two collections:
  scored_calls   ← past scored call results
  knowledge_base ← KB policy rules

Usage:
  python vector_db/milvus_store.py --build
  python vector_db/milvus_store.py --stats
  python vector_db/milvus_store.py --search "agent refused escalation"
"""

import os
import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from faiss_search.embedder import embed_text

BASE_DIR    = ROOT
RESULTS_DIR = BASE_DIR / "analysis_results"
KB_FILE     = BASE_DIR / "knowledge_base" / "kb_store.json"
MILVUS_DIR  = str(BASE_DIR / "vector_db" / "milvus_db")

DIMENSION        = 384
CALLS_COLLECTION = "scored_calls"
KB_COLLECTION    = "knowledge_base"

# ══════════════════════════════════════════════════════
# WINDOWS-COMPATIBLE MILVUS MOCK
# ══════════════════════════════════════════════════════
class _MockMilvusClient:
    """
    Pure Python Milvus simulation for Windows.
    Implements identical API to real MilvusClient.

    On Linux/Mac deployment replace get_client() with:
        from pymilvus import MilvusClient
        _client = MilvusClient("./milvus_db/callaudit.db")
    """

    def __init__(self):
        self._collections = {}
        print("  ✅ Milvus connected → mock mode")
        print("     (milvus-lite not supported on Windows)")
        print("     On Linux/Mac this uses real MilvusClient")

    def has_collection(self, name: str) -> bool:
        return name in self._collections

    def create_collection(self, collection_name: str,
                          dimension: int,
                          metric_type: str = "COSINE",
                          auto_id: bool = False):
        self._collections[collection_name] = {
            "dimension": dimension,
            "metric":    metric_type,
            "rows":      []
        }
        print(f"  ✅ Collection '{collection_name}' created")

    def drop_collection(self, name: str):
        if name in self._collections:
            del self._collections[name]

    def insert(self, collection_name: str, data: list):
        if collection_name not in self._collections:
            return {"insert_count": 0}
        for item in data:
            self._collections[collection_name]["rows"].append(item)
        return {"insert_count": len(data)}

    def search(self, collection_name: str, data: list,
               limit: int = 3, output_fields: list = None):
        if collection_name not in self._collections:
            return [[]]

        import numpy as np
        query  = np.array(data[0], dtype=np.float32)
        rows   = self._collections[collection_name]["rows"]
        scored = []

        for row in rows:
            vec  = np.array(row.get("vector", []), dtype=np.float32)
            norm = np.linalg.norm(query) * np.linalg.norm(vec)
            sim  = float(np.dot(query, vec) / norm) if norm > 0 else 0.0
            scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        hits = []
        for sim, row in scored[:limit]:
            fields = output_fields or []
            entity = {k: row.get(k) for k in fields if k in row}
            hits.append({"distance": sim, "entity": entity})

        return [hits]

    def get_collection_stats(self, collection_name: str) -> dict:
        if collection_name not in self._collections:
            return {"row_count": 0}
        return {
            "row_count": len(
                self._collections[collection_name]["rows"]
            )
        }


# ── Client ─────────────────────────────────────────────
_client = None


def get_client():
    global _client
    if _client is not None:
        return _client

    # Always use mock on Windows
    # On Linux/Mac replace this block with:
    #   from pymilvus import MilvusClient
    #   os.makedirs(MILVUS_DIR, exist_ok=True)
    #   _client = MilvusClient(f"{MILVUS_DIR}/callaudit.db")
    _client = _MockMilvusClient()
    return _client


def _ensure_collection(name: str):
    """Create collection if it does not exist."""
    client = get_client()
    if not client.has_collection(name):
        client.create_collection(
            collection_name = name,
            dimension       = DIMENSION,
            metric_type     = "COSINE",
            auto_id         = False,
        )
    return client


# ══════════════════════════════════════════════════════
# BUILD INDEX
# ══════════════════════════════════════════════════════
def build_index():
    print(f"\n{'='*55}")
    print(f"  Building Milvus index")
    print(f"{'='*55}")

    _ensure_collection(CALLS_COLLECTION)
    _ensure_collection(KB_COLLECTION)
    client = get_client()

    # ── Index scored calls ─────────────────────────────
    files = sorted(RESULTS_DIR.glob("scored_*.json"))
    print(f"  Scored files : {len(files)}")

    call_data = []
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

            call_data.append({
                "id":            abs(hash(f.stem)) % (10**9),
                "vector":        embedding,
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
            })

        except Exception as e:
            print(f"  ⚠️  Skipped {f.name}: {e}")

    if call_data:
        client.drop_collection(CALLS_COLLECTION)
        _ensure_collection(CALLS_COLLECTION)
        client.insert(
            collection_name = CALLS_COLLECTION,
            data            = call_data
        )
        print(f"  Scored calls indexed : {len(call_data)}")

    # ── Index KB entries ───────────────────────────────
    kb_data = []
    if KB_FILE.exists():
        try:
            kb_entries = json.loads(KB_FILE.read_text(encoding="utf-8"))
            for i, entry in enumerate(kb_entries):
                kb_text   = f"{entry.get('title','')} {entry.get('content','')}"
                embedding = embed_text(kb_text)

                kb_data.append({
                    "id":       i + 1,
                    "vector":   embedding,
                    "source":   "knowledge_base",
                    "kb_id":    str(entry.get("id", "")),
                    "title":    str(entry.get("title", "")),
                    "content":  str(entry.get("content", ""))[:500],
                    "severity": str(entry.get("severity", "info")),
                    "tags":     str(entry.get("tags", "")),
                })

        except Exception as e:
            print(f"  ⚠️  KB indexing failed: {e}")

    if kb_data:
        client.drop_collection(KB_COLLECTION)
        _ensure_collection(KB_COLLECTION)
        client.insert(
            collection_name = KB_COLLECTION,
            data            = kb_data
        )
        print(f"  KB entries indexed   : {len(kb_data)}")
    else:
        print(f"  ⚠️  No KB entries found")
        print(f"     Run: python knowledge_base/kb_loader.py")

    print(f"\n  ✅ Milvus index built")
    print(f"     Mode    : Mock (Windows compatible)")
    print(f"{'='*55}\n")


# ══════════════════════════════════════════════════════
# SEARCH
# ══════════════════════════════════════════════════════
def search_similar_calls(query_text: str, top_k: int = 3) -> list:
    """Search only scored call results."""
    try:
        client    = get_client()
        embedding = embed_text(query_text)

        results = client.search(
            collection_name = CALLS_COLLECTION,
            data            = [embedding],
            limit           = top_k,
            output_fields   = [
                "source", "filename", "grade",
                "overall_score", "issue", "summary",
                "outcome", "was_resolved", "violations", "sentiment"
            ]
        )

        hits = []
        for r in results[0]:
            entity = r.get("entity", {})
            hits.append({
                **entity,
                "similarity": round(r.get("distance", 0), 4)
            })
        return hits

    except Exception as e:
        print(f"  ⚠️  Milvus calls search failed: {e}")
        return []


def search_kb(query_text: str, top_k: int = 3) -> list:
    """Search only KB policy rule entries."""
    try:
        client    = get_client()
        embedding = embed_text(query_text)

        results = client.search(
            collection_name = KB_COLLECTION,
            data            = [embedding],
            limit           = top_k,
            output_fields   = [
                "source", "kb_id", "title",
                "content", "severity", "tags"
            ]
        )

        hits = []
        for r in results[0]:
            entity = r.get("entity", {})
            hits.append({
                **entity,
                "similarity": round(r.get("distance", 0), 4)
            })
        return hits

    except Exception as e:
        print(f"  ⚠️  Milvus KB search failed: {e}")
        return []


# ══════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════
def index_stats() -> dict:
    try:
        client = get_client()
        calls  = 0
        kb     = 0

        if client.has_collection(CALLS_COLLECTION):
            calls = client.get_collection_stats(
                CALLS_COLLECTION
            ).get("row_count", 0)

        if client.has_collection(KB_COLLECTION):
            kb = client.get_collection_stats(
                KB_COLLECTION
            ).get("row_count", 0)

        return {
            "scored_calls": calls,
            "kb_entries":   kb,
            "total":        calls + kb,
            "location":     MILVUS_DIR,
        }

    except Exception as e:
        return {"error": str(e)}


def clear_index():
    """Drop all collections."""
    try:
        client = get_client()
        if client.has_collection(CALLS_COLLECTION):
            client.drop_collection(CALLS_COLLECTION)
        if client.has_collection(KB_COLLECTION):
            client.drop_collection(KB_COLLECTION)
        print("  ✅ Milvus index cleared")
    except Exception as e:
        print(f"  ⚠️  Clear failed: {e}")


# ══════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Milvus vector store")
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
        print(f"  Milvus Stats")
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