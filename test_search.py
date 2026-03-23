# test_search.py
from faiss_search.faiss_store import search

query   = "agent was rude and refused to escalate the complaint"
results = search(query, top_k=3)

print(f"\nQuery: '{query}'\n")
print("Top 3 similar past calls:")
for r in results:
    print(f"  Grade {r['grade']} | Score {r['overall_score']} | {r['issue'][:60]}")
    print(f"  Similarity: {r['similarity']}")
    print()