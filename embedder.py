"""
# ============================================================
# NEW FILE — embedder.py
# Offline embedding using TF-IDF (sklearn) or a lightweight
# bag-of-words fallback (numpy only).
# No internet, no external model server required.
#
# Why TF-IDF instead of neural embeddings?
#   • Fully offline — no Ollama embedding model required
#   • Works immediately with zero setup
#   • Good enough for domain-specific college/school documents
#   • Users can swap in Ollama embeddings later (see UPGRADE NOTE)
# ============================================================
"""

import re
import math
import json
import pickle
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np

# Try to import sklearn; fall back to manual TF-IDF if unavailable
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


# ── constants ───────────────────────────────────────────────────────────────────

VECTOR_STORE_PATH = Path("rag_vector_store")   # directory for persistence
INDEX_FILE        = VECTOR_STORE_PATH / "index.pkl"
META_FILE         = VECTOR_STORE_PATH / "metadata.json"


# ── text preprocessing (shared) ─────────────────────────────────────────────────

def _preprocess(text: str) -> str:
    """Lowercase and strip punctuation for consistent tokenisation."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ── sklearn TF-IDF implementation ───────────────────────────────────────────────

class SklearnEmbedder:
    """
    TF-IDF vectoriser backed by scikit-learn.
    Fit on the corpus once, then transform individual queries.
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=10_000,
            sublinear_tf=True,
            strip_accents="unicode",
        )
        self._fitted = False
        self._matrix = None          # np.ndarray shape (N, vocab)
        self._chunks: List[Dict] = []

    def build_index(self, chunks: List[Dict]) -> None:
        """Fit vectoriser and store normalised TF-IDF matrix."""
        self._chunks = chunks
        texts = [_preprocess(c["text"]) for c in chunks]
        raw = self.vectorizer.fit_transform(texts)
        self._matrix = normalize(raw, norm="l2").toarray().astype(np.float32)
        self._fitted = True

    def embed_query(self, query: str) -> np.ndarray:
        texts = [_preprocess(query)]
        raw = self.vectorizer.transform(texts)
        return normalize(raw, norm="l2").toarray().astype(np.float32)[0]

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Dict, float]]:
        if not self._fitted or self._matrix is None or len(self._chunks) == 0:
            return []
        qvec = self.embed_query(query)
        scores = self._matrix @ qvec          # cosine similarity (already L2-normalised)
        top_idx = np.argsort(scores)[::-1][:top_k]
        return [(self._chunks[i], float(scores[i])) for i in top_idx if scores[i] > 0.05]

    def add_chunks(self, new_chunks: List[Dict]) -> None:
        """Add more chunks and re-fit the vectoriser on the full corpus."""
        all_chunks = self._chunks + new_chunks
        self.build_index(all_chunks)

    def save(self) -> None:
        VECTOR_STORE_PATH.mkdir(exist_ok=True)
        with open(INDEX_FILE, "wb") as f:
            pickle.dump({"vectorizer": self.vectorizer, "matrix": self._matrix}, f)
        with open(META_FILE, "w") as f:
            json.dump(self._chunks, f, default=str)

    def load(self) -> bool:
        if not INDEX_FILE.exists() or not META_FILE.exists():
            return False
        with open(INDEX_FILE, "rb") as f:
            data = pickle.load(f)
        self.vectorizer = data["vectorizer"]
        self._matrix = data["matrix"]
        with open(META_FILE) as f:
            self._chunks = json.load(f)
        self._fitted = True
        return True

    def clear(self) -> None:
        self._fitted = False
        self._matrix = None
        self._chunks = []
        if INDEX_FILE.exists():
            INDEX_FILE.unlink()
        if META_FILE.exists():
            META_FILE.unlink()

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def indexed_files(self) -> List[str]:
        return list({c["filename"] for c in self._chunks})


# ── numpy-only fallback ─────────────────────────────────────────────────────────

class NumpyEmbedder:
    """
    Minimal bag-of-words TF-IDF fallback when sklearn is unavailable.
    Slower but zero-dependency.
    """

    def __init__(self):
        self._vocab: Dict[str, int] = {}
        self._idf: np.ndarray = np.array([])
        self._matrix: np.ndarray = np.array([])
        self._chunks: List[Dict] = []
        self._fitted = False

    def _tokenize(self, text: str) -> List[str]:
        return _preprocess(text).split()

    def _tf(self, tokens: List[str]) -> Dict[str, float]:
        freq: Dict[str, float] = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1
        total = max(len(tokens), 1)
        return {k: v / total for k, v in freq.items()}

    def build_index(self, chunks: List[Dict]) -> None:
        self._chunks = chunks
        tokenized = [self._tokenize(c["text"]) for c in chunks]

        # Build vocabulary
        all_words = {w for toks in tokenized for w in toks}
        self._vocab = {w: i for i, w in enumerate(sorted(all_words))}
        V = len(self._vocab)
        N = len(chunks)

        # Document frequency
        df = np.zeros(V, dtype=np.float32)
        for toks in tokenized:
            for w in set(toks):
                if w in self._vocab:
                    df[self._vocab[w]] += 1

        # IDF
        self._idf = np.log((N + 1) / (df + 1)) + 1.0

        # TF-IDF matrix
        mat = np.zeros((N, V), dtype=np.float32)
        for i, toks in enumerate(tokenized):
            tf = self._tf(toks)
            for w, v in tf.items():
                if w in self._vocab:
                    mat[i, self._vocab[w]] = v * self._idf[self._vocab[w]]

        # L2 normalise rows
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1
        self._matrix = (mat / norms).astype(np.float32)
        self._fitted = True

    def _vectorize(self, tokens: List[str]) -> np.ndarray:
        V = len(self._vocab)
        vec = np.zeros(V, dtype=np.float32)
        tf = self._tf(tokens)
        for w, v in tf.items():
            if w in self._vocab:
                vec[self._vocab[w]] = v * self._idf[self._vocab[w]]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Dict, float]]:
        if not self._fitted or len(self._chunks) == 0:
            return []
        tokens = self._tokenize(query)
        qvec = self._vectorize(tokens)
        scores = self._matrix @ qvec
        top_idx = np.argsort(scores)[::-1][:top_k]
        return [(self._chunks[i], float(scores[i])) for i in top_idx if scores[i] > 0.05]

    def add_chunks(self, new_chunks: List[Dict]) -> None:
        self.build_index(self._chunks + new_chunks)

    def save(self) -> None:
        VECTOR_STORE_PATH.mkdir(exist_ok=True)
        np.save(str(VECTOR_STORE_PATH / "matrix.npy"), self._matrix)
        np.save(str(VECTOR_STORE_PATH / "idf.npy"), self._idf)
        with open(META_FILE, "w") as f:
            json.dump({"chunks": self._chunks, "vocab": self._vocab}, f, default=str)

    def load(self) -> bool:
        matrix_file = VECTOR_STORE_PATH / "matrix.npy"
        if not matrix_file.exists() or not META_FILE.exists():
            return False
        self._matrix = np.load(str(matrix_file))
        self._idf = np.load(str(VECTOR_STORE_PATH / "idf.npy"))
        with open(META_FILE) as f:
            data = json.load(f)
        self._chunks = data["chunks"]
        self._vocab = data["vocab"]
        self._fitted = True
        return True

    def clear(self) -> None:
        self._fitted = False
        self._chunks = []
        self._vocab = {}

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def indexed_files(self) -> List[str]:
        return list({c["filename"] for c in self._chunks})


# ── singleton selection ─────────────────────────────────────────────────────────

def _make_embedder():
    if _SKLEARN_AVAILABLE:
        print("[embedder] Using sklearn TF-IDF embedder")
        return SklearnEmbedder()
    else:
        print("[embedder] sklearn not found — using numpy fallback embedder")
        return NumpyEmbedder()


# Module-level singleton — imported by vector_store.py
embedder = _make_embedder()

# ── UPGRADE NOTE ────────────────────────────────────────────────────────────────
# To switch to Ollama neural embeddings (e.g. nomic-embed-text):
#
# 1. Pull the model:  ollama pull nomic-embed-text
#
# 2. Replace embed_query() with:
#
#    import httpx
#    def embed_query(text: str) -> np.ndarray:
#        r = httpx.post("http://localhost:11434/api/embeddings",
#                       json={"model": "nomic-embed-text", "prompt": text})
#        return np.array(r.json()["embedding"], dtype=np.float32)
#
# 3. At index build time, embed each chunk the same way.
# ────────────────────────────────────────────────────────────────────────────────