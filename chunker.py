"""
chunker.py
Splits raw text chunks (from file_processor.py) into larger,
non-overlapping windows suitable for embedding and retrieval.
"""

from typing import List, Dict

# ── configuration ───────────────────────────────────────────────────────────────

CHUNK_SIZE    = 1500    # target characters per chunk
CHUNK_OVERLAP = 150     # overlap between consecutive chunks

# ── core splitter ───────────────────────────────────────────────────────────────

def _split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    words = text.split()
    chunks: List[str] = []
    start = 0

    while start < len(words):
        end = start
        current_length = 0
        while end < len(words) and current_length + len(words[end]) + 1 <= chunk_size:
            current_length += len(words[end]) + 1
            end += 1

        if end == start:
            end = start + 1

        chunk = " ".join(words[start:end])
        chunks.append(chunk)

        overlap_words = 0
        overlap_chars = 0
        for word in reversed(words[start:end]):
            if overlap_chars + len(word) + 1 > overlap:
                break
            overlap_chars += len(word) + 1
            overlap_words += 1

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

    # ── KEY FIX: group pages by source_type and merge before chunking ──────────
    pdf_pages    = [r for r in raw_chunks if r.get("source_type") == "pdf"]
    other_chunks = [r for r in raw_chunks if r.get("source_type") != "pdf"]

    final_chunks: List[Dict] = []
    chunk_counter = 0

    # ✅ REPLACE the entire "For PDFs" block with this:
    if pdf_pages:
        for raw in pdf_pages:
            text = raw.get("text", "").strip()
            if not text:
                continue

            page_num = raw.get("page", 1)   # ← each page keeps its own number
            meta = {"page": page_num}

            if len(text) <= chunk_size:
                sub_chunks = [text]
            else:
                sub_chunks = _split_text(text, chunk_size, overlap)

            for i, sub in enumerate(sub_chunks):
                chunk_id = f"{filename}::chunk_{chunk_counter}"
                final_chunks.append({
                    "chunk_id":    chunk_id,
                    "text":        sub,
                    "filename":    filename,
                    "source_type": "pdf",
                    "meta":        {**meta, "sub_index": i},
                })
                chunk_counter += 1

    # For non-PDF files: original behavior
    for raw in other_chunks:
        text = raw.get("text", "").strip()
        if not text:
            continue

        source_type = raw.get("source_type", "unknown")
        meta_keys   = {"page", "row", "sheet", "element", "index"}
        meta        = {k: raw[k] for k in meta_keys if k in raw}

        if len(text) <= chunk_size:
            sub_chunks = [text]
        else:
            sub_chunks = _split_text(text, chunk_size, overlap)

        for i, sub in enumerate(sub_chunks):
            chunk_id = f"{filename}::chunk_{chunk_counter}"
            final_chunks.append({
                "chunk_id":    chunk_id,
                "text":        sub,
                "filename":    filename,
                "source_type": source_type,
                "meta":        {**meta, "sub_index": i},
            })
            chunk_counter += 1

    return final_chunks