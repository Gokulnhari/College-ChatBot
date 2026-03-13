"""
# ============================================================
# NEW FILE — chunker.py
# Splits raw text chunks (from file_processor.py) into smaller,
# overlapping windows suitable for embedding and retrieval.
# ============================================================
"""

from typing import List, Dict


# ── configuration ───────────────────────────────────────────────────────────────

CHUNK_SIZE = 700        # target characters per chunk
CHUNK_OVERLAP = 100      # overlap between consecutive chunks


# ── core splitter ───────────────────────────────────────────────────────────────

def _split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split a long string into overlapping windows by word boundary.

    Strategy:
      1. Split into words.
      2. Accumulate words until chunk_size characters reached.
      3. Step back `overlap` characters and start the next chunk.

    Args:
        text: Input text to split
        chunk_size: Maximum characters per chunk
        overlap: Number of characters to repeat at chunk boundaries

    Returns:
        List of text chunks
    """
    words = text.split()
    chunks: List[str] = []
    start = 0

    while start < len(words):
        # Collect words until we exceed chunk_size
        end = start
        current_length = 0
        while end < len(words) and current_length + len(words[end]) + 1 <= chunk_size:
            current_length += len(words[end]) + 1
            end += 1

        # Always advance at least one word to avoid infinite loop
        if end == start:
            end = start + 1

        chunk = " ".join(words[start:end])
        chunks.append(chunk)

        # Calculate overlap in words (approximate)
        overlap_words = 0
        overlap_chars = 0
        for word in reversed(words[start:end]):
            if overlap_chars + len(word) + 1 > overlap:
                break
            overlap_chars += len(word) + 1
            overlap_words += 1

        # Move start forward (but always make progress)
        advance = max(1, (end - start) - overlap_words)
        start += advance

    return chunks


# ── public API ──────────────────────────────────────────────────────────────────

def chunk_extracted(
    raw_chunks: List[Dict],
    filename: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[Dict]:
    """
    Take the output of file_processor.extract() and produce final chunks
    ready for embedding.

    Each output chunk includes metadata so the UI can cite its source.

    Args:
        raw_chunks: List of dicts from file_processor.extract()
        filename: Original filename (stored as metadata)
        chunk_size: Max characters per chunk
        overlap: Overlap between chunks

    Returns:
        List of dicts, each containing:
            - "chunk_id": str  (unique identifier)
            - "text": str      (the text to embed)
            - "filename": str
            - "source_type": str   (pdf / excel / xml / csv)
            - "meta": dict     (page/row/sheet/element info)
    """
    final_chunks: List[Dict] = []
    chunk_counter = 0

    for raw in raw_chunks:
        text = raw.get("text", "").strip()
        if not text:
            continue

        source_type = raw.get("source_type", "unknown")

        # Build metadata dict from whatever keys the extractor provided
        meta_keys = {"page", "row", "sheet", "element", "index"}
        meta = {k: raw[k] for k in meta_keys if k in raw}

        # For short chunks (e.g. a single Excel row) keep as-is
        if len(text) <= chunk_size:
            sub_chunks = [text]
        else:
            sub_chunks = _split_text(text, chunk_size, overlap)

        for i, sub in enumerate(sub_chunks):
            chunk_id = f"{filename}::chunk_{chunk_counter}"
            final_chunks.append({
                "chunk_id": chunk_id,
                "text": sub,
                "filename": filename,
                "source_type": source_type,
                "meta": {**meta, "sub_index": i},
            })
            chunk_counter += 1

    return final_chunks