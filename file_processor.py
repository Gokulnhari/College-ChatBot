"""
# ============================================================
# NEW FILE — file_processor.py
# Extracts raw text content from PDF, Excel, XML, and CSV files.
# Called by the /upload endpoint in routes.py.
# ============================================================
"""

import csv
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict

import openpyxl
from pypdf import PdfReader


# ── helpers ────────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Strip extra whitespace and blank lines."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


# ── per-format extractors ───────────────────────────────────────────────────────

def extract_pdf(file_bytes: bytes) -> List[Dict]:
    """
    Extract text page-by-page from a PDF.

    Returns:
        List of dicts: [{"page": 1, "text": "...", "source_type": "pdf"}, ...]
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        text = _clean(raw)
        if text:
            pages.append({
                "page": i,
                "text": text,
                "source_type": "pdf"
            })
    return pages


def extract_excel(file_bytes: bytes) -> List[Dict]:
    """
    Extract content from every sheet of an Excel file.
    Each row becomes a small text chunk with column headers as keys.

    Returns:
        List of dicts: [{"sheet": "Sheet1", "row": 2, "text": "...", "source_type": "excel"}, ...]
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    chunks = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        # First row → headers
        headers = [str(h).strip() if h is not None else f"col_{i}"
                   for i, h in enumerate(rows[0])]

        for row_idx, row in enumerate(rows[1:], start=2):
            parts = []
            for header, cell in zip(headers, row):
                if cell is not None and str(cell).strip():
                    parts.append(f"{header}: {cell}")
            if parts:
                chunks.append({
                    "sheet": sheet_name,
                    "row": row_idx,
                    "text": " | ".join(parts),
                    "source_type": "excel"
                })

    return chunks


def _xml_to_text(element: ET.Element, depth: int = 0) -> str:
    """
    Recursively flatten an XML element tree into readable key: value lines.
    """
    lines = []
    tag = element.tag.split("}")[-1]  # strip namespace

    # Attributes
    if element.attrib:
        attr_str = ", ".join(f"{k}={v}" for k, v in element.attrib.items())
        lines.append("  " * depth + f"{tag} [{attr_str}]")
    else:
        lines.append("  " * depth + f"{tag}")

    # Text content
    if element.text and element.text.strip():
        lines.append("  " * (depth + 1) + element.text.strip())

    # Children
    for child in element:
        lines.append(_xml_to_text(child, depth + 1))

    return "\n".join(lines)


def extract_xml(file_bytes: bytes) -> List[Dict]:
    """
    Parse XML and chunk by top-level child elements.
    Each direct child of root → one chunk.

    Returns:
        List of dicts: [{"element": "Student", "index": 0, "text": "...", "source_type": "xml"}, ...]
    """
    try:
        root = ET.fromstring(file_bytes)
    except ET.ParseError as e:
        return [{"element": "root", "index": 0,
                 "text": f"XML parse error: {e}", "source_type": "xml"}]

    children = list(root)

    # If root has no children, treat the whole file as one chunk
    if not children:
        return [{
            "element": root.tag.split("}")[-1],
            "index": 0,
            "text": _xml_to_text(root),
            "source_type": "xml"
        }]

    chunks = []
    for i, child in enumerate(children):
        tag = child.tag.split("}")[-1]
        text = _clean(_xml_to_text(child))
        if text:
            chunks.append({
                "element": tag,
                "index": i,
                "text": text,
                "source_type": "xml"
            })
    return chunks


def extract_csv(file_bytes: bytes) -> List[Dict]:
    """
    Extract CSV rows as text chunks (each row → one chunk).

    Returns:
        List of dicts: [{"row": 2, "text": "col1: val1 | col2: val2", "source_type": "csv"}, ...]
    """
    content = file_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    chunks = []
    for row_idx, row in enumerate(reader, start=2):
        parts = [f"{k}: {v}" for k, v in row.items() if v and str(v).strip()]
        if parts:
            chunks.append({
                "row": row_idx,
                "text": " | ".join(parts),
                "source_type": "csv"
            })
    return chunks


# ── public dispatcher ───────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".xml", ".csv"}


def extract(filename: str, file_bytes: bytes) -> List[Dict]:
    """
    Dispatch to the correct extractor based on file extension.

    Args:
        filename: Original filename (used to detect type)
        file_bytes: Raw bytes of the uploaded file

    Returns:
        List of chunk dicts, each with at least {"text": str, "source_type": str}

    Raises:
        ValueError: If the file type is not supported
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return extract_pdf(file_bytes)
    elif ext in {".xlsx", ".xls"}:
        return extract_excel(file_bytes)
    elif ext == ".xml":
        return extract_xml(file_bytes)
    elif ext == ".csv":
        return extract_csv(file_bytes)
    else:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )