"""
# ============================================================
# NEW FILE — vector_store.py
# Manages the RAG index lifecycle:
#   - add_file()     → process + chunk + index a new file
#   - search()       → retrieve top-K relevant chunks for a query
#   - remove_file()  → delete chunks belonging to a specific file
#   - clear()        → wipe everything
#   - status()       → index stats for the UI
# ============================================================
"""

from typing import List, Dict, Any, Tuple
from pathlib import Path

from embedder import embedder
from file_processor import extract
from chunker import chunk_extracted


class VectorStore:
    """
    High-level RAG index manager.
    Wraps the embedder and exposes a clean API to routes.py and the LLM service.
    """

    def __init__(self):
        # Attempt to restore a saved index from disk
        restored = embedder.load()
        if restored:
            print(f"[vector_store] Restored index: {embedder.chunk_count} chunks "
                  f"from {embedder.indexed_files}")
        else:
            print("[vector_store] Starting with empty index.")

    # ── indexing ────────────────────────────────────────────────────────────────

    def add_file(self, filename: str, file_bytes: bytes) -> Dict[str, Any]:
        """
        Full pipeline: extract → chunk → embed → add to index.

        Args:
            filename: Original filename (determines parser)
            file_bytes: Raw bytes of the uploaded file

        Returns:
            Summary dict {"filename", "source_type", "chunks_added", "total_chunks"}
        """
        # 1. Extract text
        raw_chunks = extract(filename, file_bytes)

        if not raw_chunks:
            return {
                "filename": filename,
                "source_type": "unknown",
                "chunks_added": 0,
                "total_chunks": embedder.chunk_count,
                "warning": "No text could be extracted from this file."
            }

        source_type = raw_chunks[0].get("source_type", "unknown")

        # 2. Split into embedding-sized chunks
        final_chunks = chunk_extracted(raw_chunks, filename)

        # 3. Add to index (re-fits the vectoriser on the full corpus)
        embedder.add_chunks(final_chunks)

        # 4. Persist to disk
        embedder.save()

        return {
            "filename": filename,
            "source_type": source_type,
            "chunks_added": len(final_chunks),
            "total_chunks": embedder.chunk_count,
        }

    # ── retrieval ───────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Return the top-K most relevant chunks for a query.

        Args:
            query: User question
            top_k: Number of chunks to retrieve

        Returns:
            List of dicts, each containing:
                - "text": str          (the chunk content)
                - "filename": str
                - "source_type": str
                - "score": float       (cosine similarity 0-1)
                - "meta": dict         (page / row / sheet / element)
        """
        results = embedder.search(query, top_k=top_k)
        return [
            {
                "text": chunk["text"],
                "filename": chunk["filename"],
                "source_type": chunk["source_type"],
                "score": round(score, 4),
                "meta": chunk.get("meta", {}),
            }
            for chunk, score in results
        ]

    # ── management ──────────────────────────────────────────────────────────────

    def remove_file(self, filename: str) -> Dict[str, Any]:
        """
        Remove all chunks belonging to a specific file and rebuild the index.

        Args:
            filename: Filename to remove

        Returns:
            Summary dict
        """
        # Access the internal chunk list and filter
        all_chunks = embedder._chunks
        remaining = [c for c in all_chunks if c["filename"] != filename]
        removed = len(all_chunks) - len(remaining)

        if removed == 0:
            return {"filename": filename, "removed": 0,
                    "message": "File not found in index."}

        # Rebuild index with remaining chunks
        embedder.clear()
        if remaining:
            embedder.build_index(remaining)
            embedder.save()

        return {
            "filename": filename,
            "removed": removed,
            "total_chunks": embedder.chunk_count,
        }

    def clear(self) -> Dict[str, Any]:
        """Wipe the entire index."""
        count = embedder.chunk_count
        embedder.clear()
        return {"message": "Index cleared.", "chunks_removed": count}

    # ── status ──────────────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Return index stats for the Streamlit sidebar."""
        return {
            "total_chunks": embedder.chunk_count,
            "indexed_files": embedder.indexed_files,
            "has_data": embedder.chunk_count > 0,
        }


# Singleton — imported by routes.py and llm_service.py
vector_store = VectorStore()