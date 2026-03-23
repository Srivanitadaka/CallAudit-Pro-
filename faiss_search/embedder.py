# faiss_search/embedder.py

from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"
_model = None

def get_model():
    global _model
    if _model is None:
        print("Loading BGE model...")
        _model = SentenceTransformer(MODEL_NAME)
    return _model

def embed_text(text: str) -> list:
    """Convert any text → 384 numbers (a vector)"""
    model = get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()