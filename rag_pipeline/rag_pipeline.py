# rag_pipeline/rag_pipeline.py

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SIMILAR_CALLS_TOP_K = 3
KB_RULES_TOP_K      = 3
KB_QUERY_CHARS      = 300


class RAGPipeline:

    def __init__(self, backend: str = "chromadb"):
        """
        backend options:
          'chromadb' — local persistent (default)
          'faiss'    — local in-memory
          'pinecone' — cloud vector DB
          'milvus'   — enterprise vector DB
        """
        self.backend = backend
        self._ready  = False

    # ══════════════════════════════════════════════════
    # SETUP
    # ══════════════════════════════════════════════════
    def setup(self) -> bool:
        try:
            if self.backend == "chromadb":
                from vector_db.chroma_store import index_stats
                stats = index_stats()
                calls = stats.get("scored_calls", 0)
                kb    = stats.get("kb_entries", 0)

                if calls == 0:
                    print("  ⚠️  ChromaDB empty.")
                    print("     Run: python vector_db\\chroma_store.py --build")
                    self._ready = False
                    return False

                print(f"  ✅ RAG Pipeline ready")
                print(f"     Backend      : ChromaDB")
                print(f"     Scored calls : {calls}")
                print(f"     KB entries   : {kb}")

            elif self.backend == "faiss":
                from faiss_search.faiss_store import load_index, index_stats
                loaded = load_index()
                if not loaded:
                    print("  ⚠️  FAISS index not found.")
                    print("     Run: python faiss_search\\faiss_store.py")
                    self._ready = False
                    return False

                stats = index_stats()
                print(f"  ✅ RAG Pipeline ready")
                print(f"     Backend        : FAISS")
                print(f"     Scored calls   : {stats.get('scored_results', 0)}")
                print(f"     KB entries     : {stats.get('kb_entries', 0)}")
                print(f"     Total vectors  : {stats.get('total_vectors', 0)}")

            elif self.backend == "pinecone":
                from vector_db.pinecone_db import index_stats
                stats = index_stats()

                if "error" in stats:
                    print(f"  ⚠️  Pinecone error: {stats['error']}")
                    print(f"     Check PINECONE_API_KEY in config/.env")
                    self._ready = False
                    return False

                calls = stats.get("scored_calls", 0)
                kb    = stats.get("kb_entries", 0)

                if calls == 0:
                    print("  ⚠️  Pinecone index empty.")
                    print("     Run: python vector_db\\pinecone_db.py --build")
                    self._ready = False
                    return False

                print(f"  ✅ RAG Pipeline ready")
                print(f"     Backend      : Pinecone ☁️")
                print(f"     Index        : {stats.get('index_name', '')}")
                print(f"     Scored calls : {calls}")
                print(f"     KB entries   : {kb}")

            elif self.backend == "milvus":
                from vector_db.milvus_store import index_stats
                stats = index_stats()

                if "error" in stats:
                    print(f"  ⚠️  Milvus error: {stats['error']}")
                    print(f"     Run: python vector_db\\milvus_store.py --build")
                    self._ready = False
                    return False

                calls = stats.get("scored_calls", 0)
                kb    = stats.get("kb_entries", 0)

                if calls == 0:
                    print("  ⚠️  Milvus index empty.")
                    print("     Run: python vector_db\\milvus_store.py --build")
                    self._ready = False
                    return False

                print(f"  ✅ RAG Pipeline ready")
                print(f"     Backend      : Milvus 🏢")
                print(f"     Scored calls : {calls}")
                print(f"     KB entries   : {kb}")

            else:
                print(f"  ⚠️  Unknown backend: '{self.backend}'")
                print(f"     Options: chromadb, faiss, pinecone, milvus")
                self._ready = False
                return False

            self._ready = True
            return True

        except Exception as e:
            print(f"  ⚠️  RAG Pipeline setup failed: {e}")
            self._ready = False
            return False

    # ══════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ══════════════════════════════════════════════════
    def enrich(self, transcript: str) -> str:
        if not self._ready:
            self.setup()

        enriched = transcript

        similar = self._get_similar_calls(transcript)
        if similar:
            enriched += self._format_similar_calls(similar)
            print(f"  🔍 RAG: {len(similar)} similar calls injected")
        else:
            print(f"  ⚠️  RAG: no similar calls found")

        kb_rules = self._get_kb_rules(transcript)
        if kb_rules:
            enriched += self._format_kb_rules(kb_rules)
            print(f"  📚 RAG: {len(kb_rules)} KB rules injected")
        else:
            print(f"  ⚠️  RAG: no KB rules found")

        return enriched

    # ══════════════════════════════════════════════════
    # RETRIEVAL
    # ══════════════════════════════════════════════════
    def _get_similar_calls(self, text: str) -> list:
        try:
            if self.backend == "chromadb":
                from vector_db.chroma_store import search_similar_calls
                return search_similar_calls(text, top_k=SIMILAR_CALLS_TOP_K)

            elif self.backend == "faiss":
                from faiss_search.faiss_store import search_similar_calls
                return search_similar_calls(text, top_k=SIMILAR_CALLS_TOP_K)

            elif self.backend == "pinecone":
                from vector_db.pinecone_db import search_similar_calls
                return search_similar_calls(text, top_k=SIMILAR_CALLS_TOP_K)

            elif self.backend == "milvus":
                from vector_db.milvus_store import search_similar_calls
                return search_similar_calls(text, top_k=SIMILAR_CALLS_TOP_K)

        except Exception as e:
            print(f"  ⚠️  Similar calls failed: {e}")
            return []

    def _get_kb_rules(self, text: str) -> list:
        try:
            if self.backend == "chromadb":
                from vector_db.chroma_store import search_kb
                return search_kb(
                    text[:KB_QUERY_CHARS],
                    top_k=KB_RULES_TOP_K
                )

            elif self.backend == "faiss":
                from faiss_search.faiss_store import search_kb
                return search_kb(
                    text[:KB_QUERY_CHARS],
                    top_k=KB_RULES_TOP_K
                )

            elif self.backend == "pinecone":
                from vector_db.pinecone_db import search_kb
                return search_kb(
                    text[:KB_QUERY_CHARS],
                    top_k=KB_RULES_TOP_K
                )

            elif self.backend == "milvus":
                from vector_db.milvus_store import search_kb
                return search_kb(
                    text[:KB_QUERY_CHARS],
                    top_k=KB_RULES_TOP_K
                )

        except Exception as e:
            print(f"  ⚠️  KB rules failed: {e}")
            return []

    # ══════════════════════════════════════════════════
    # FORMATTERS
    # ══════════════════════════════════════════════════
    def _format_similar_calls(self, similar: list) -> str:
        lines = ["\n\n[SIMILAR PAST CALLS — use as grade reference:]\n"]
        for s in similar:
            lines.append(
                f"  - Grade {s.get('grade','?')} | "
                f"Score {s.get('overall_score',0)}/100 | "
                f"Similarity {s.get('similarity',0)} | "
                f"Resolved: {s.get('was_resolved','False')}\n"
                f"    Issue  : {str(s.get('issue',''))[:100]}\n"
                f"    Outcome: {s.get('outcome', s.get('call_outcome',''))}\n"
            )
        lines.append(
            "→ Score the current call consistently "
            "with these reference cases.\n"
        )
        return "\n".join(lines)

    def _format_kb_rules(self, kb_rules: list) -> str:
        lines = ["\n\n[POLICY RULES — apply strictly when scoring:]\n"]
        for k in kb_rules:
            severity   = k.get("severity", "info").upper()
            title      = k.get("title", "")
            content    = k.get("content", "")
            similarity = k.get("similarity", 0)
            lines.append(
                f"  [{severity}] {title}\n"
                f"  {content}\n"
                f"  (Relevance: {similarity})\n"
            )
        return "\n".join(lines)

    # ══════════════════════════════════════════════════
    # STATS
    # ══════════════════════════════════════════════════
    def print_stats(self):
        try:
            if self.backend == "chromadb":
                from vector_db.chroma_store import index_stats
                s = index_stats()
                print(f"\n{'='*45}")
                print(f"  RAG Pipeline Stats — ChromaDB")
                print(f"{'='*45}")
                print(f"  Scored calls  : {s.get('scored_calls', 0)}")
                print(f"  KB entries    : {s.get('kb_entries', 0)}")
                print(f"  Total         : {s.get('total', 0)}")
                print(f"{'='*45}\n")

            elif self.backend == "faiss":
                from faiss_search.faiss_store import index_stats
                s = index_stats()
                print(f"\n{'='*45}")
                print(f"  RAG Pipeline Stats — FAISS")
                print(f"{'='*45}")
                print(f"  Scored calls  : {s.get('scored_results', 0)}")
                print(f"  KB entries    : {s.get('kb_entries', 0)}")
                print(f"  Total vectors : {s.get('total_vectors', 0)}")
                print(f"{'='*45}\n")

            elif self.backend == "pinecone":
                from vector_db.pinecone_db import index_stats
                s = index_stats()
                print(f"\n{'='*45}")
                print(f"  RAG Pipeline Stats — Pinecone ☁️")
                print(f"{'='*45}")
                print(f"  Scored calls  : {s.get('scored_calls', 0)}")
                print(f"  KB entries    : {s.get('kb_entries', 0)}")
                print(f"  Total         : {s.get('total', 0)}")
                print(f"  Index name    : {s.get('index_name', '')}")
                print(f"  Dimension     : {s.get('dimension', 0)}")
                print(f"{'='*45}\n")

            elif self.backend == "milvus":
                from vector_db.milvus_store import index_stats
                s = index_stats()
                print(f"\n{'='*45}")
                print(f"  RAG Pipeline Stats — Milvus 🏢")
                print(f"{'='*45}")
                print(f"  Scored calls  : {s.get('scored_calls', 0)}")
                print(f"  KB entries    : {s.get('kb_entries', 0)}")
                print(f"  Total         : {s.get('total', 0)}")
                print(f"  Location      : {s.get('location', '')}")
                print(f"{'='*45}\n")

        except Exception as e:
            print(f"  ⚠️  Stats failed: {e}")


# ══════════════════════════════════════════════════════
# RUN DIRECTLY — test all backends
# ══════════════════════════════════════════════════════
if __name__ == "__main__":

    test_transcript = """
    Agent: Thank you for calling support.
    Customer: I want to speak to a manager right now.
    Agent: Managers are too busy, I cannot transfer you.
    Customer: This is unacceptable, I have been waiting 3 days.
    Agent: There is nothing I can do about that.
    """

    # ── Change this to test different backends ─────────
    BACKEND = "chromadb"   # "faiss" | "chromadb" | "pinecone" | "milvus"
    # ──────────────────────────────────────────────────

    print(f"\nTesting RAG Pipeline — {BACKEND} backend\n")

    pipeline = RAGPipeline(backend=BACKEND)
    pipeline.setup()
    pipeline.print_stats()

    print("\nEnriching test transcript...")
    enriched = pipeline.enrich(test_transcript)

    print("\n" + "="*45)
    print("ENRICHED OUTPUT — what LangChain will receive:")
    print("="*45)
    print(enriched[:600])