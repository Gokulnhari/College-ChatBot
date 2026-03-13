"""
# ============================================================
# file_processor.py
# Extracts raw text content from PDF, Excel, XML, and CSV files.
# Called by the /upload endpoint in routes.py.
#
# CHANGES FROM ORIGINAL:
#   - extract_pdf() now tries pdfplumber first (better text extraction),
#     falls back to pypdf, then raises a clear error for scanned PDFs.
#   - Added debug print statements to diagnose empty extractions.
# ============================================================
"""

import csv
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict

import openpyxl

# Try pdfplumber first (better), fall back to pypdf
try:
    import pdfplumber
    _PDFPLUMBER_AVAILABLE = True
    print("[file_processor] Using pdfplumber for PDF extraction")
except ImportError:
    _PDFPLUMBER_AVAILABLE = False
    print("[file_processor] pdfplumber not found, using pypdf")

try:
    from pypdf import PdfReader
    _PYPDF_AVAILABLE = True
except ImportError:
    try:
        from PyPDF2 import PdfReader
        _PYPDF_AVAILABLE = True
        print("[file_processor] Using PyPDF2 for PDF extraction")
    except ImportError:
        _PYPDF_AVAILABLE = False
        print("[file_processor] WARNING: No PDF library available!")


# ── helpers ────────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Strip extra whitespace and blank lines."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


# ── per-format extractors ───────────────────────────────────────────────────────

def extract_pdf(file_bytes: bytes) -> List[Dict]:
    """
    Extract text page-by-page from a PDF.
    Tries pdfplumber first (handles more PDF types), then pypdf.

    Returns:
        List of dicts: [{"page": 1, "text": "...", "source_type": "pdf"}, ...]
    """
    pages = []

    # ── Method 1: pdfplumber ────────────────────────────────────────────────
    if _PDFPLUMBER_AVAILABLE:
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                print(f"[file_processor] pdfplumber: {len(pdf.pages)} pages found")
                for i, page in enumerate(pdf.pages, start=1):
                    raw = page.extract_text() or ""
                    text = _clean(raw)
                    print(f"[file_processor]   Page {i}: {len(text)} chars extracted")
                    if text:
                        pages.append({
                            "page": i,
                            "text": text,
                            "source_type": "pdf"
                        })
            if pages:
                print(f"[file_processor] pdfplumber extracted {len(pages)} pages with text")
                return pages
            else:
                print("[file_processor] pdfplumber found no text — PDF may be scanned/image-based")
        except Exception as e:
            print(f"[file_processor] pdfplumber failed: {e}, trying pypdf...")

    # ── Method 2: pypdf fallback ────────────────────────────────────────────
    if _PYPDF_AVAILABLE:
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            print(f"[file_processor] pypdf: {len(reader.pages)} pages found")
            for i, page in enumerate(reader.pages, start=1):
                raw = page.extract_text() or ""
                text = _clean(raw)
                print(f"[file_processor]   Page {i}: {len(text)} chars extracted")
                if text:
                    pages.append({
                        "page": i,
                        "text": text,
                        "source_type": "pdf"
                    })
            if pages:
                print(f"[file_processor] pypdf extracted {len(pages)} pages with text")
                return pages
            else:
                print("[file_processor] pypdf found no text — PDF may be scanned/image-based")
        except Exception as e:
            print(f"[file_processor] pypdf failed: {e}")

    # ── Both methods failed or returned no text ─────────────────────────────
    if not pages:
        print("[file_processor] WARNING: No text extracted from PDF.")
        print("[file_processor] This is likely a scanned/image-based PDF.")
        print("[file_processor] To fix: install OCR support with 'pip install pytesseract'")
        # Return a placeholder so the UI shows a helpful message
        pages.append({
            "page": 1,
            "text": (
                "This PDF appears to be scanned or image-based. "
                "Text extraction was not possible. "
                "Please upload a text-based PDF or a Word document."
            ),
            "source_type": "pdf",
            "warning": "scanned_pdf"
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

    if element.attrib:
        attr_str = ", ".join(f"{k}={v}" for k, v in element.attrib.items())
        lines.append("  " * depth + f"{tag} [{attr_str}]")
    else:
        lines.append("  " * depth + f"{tag}")

    if element.text and element.text.strip():
        lines.append("  " * (depth + 1) + element.text.strip())

    for child in element:
        lines.append(_xml_to_text(child, depth + 1))

    return "\n".join(lines)


def extract_xml(file_bytes: bytes) -> List[Dict]:
    """Parse XML and chunk by top-level child elements."""
    try:
        root = ET.fromstring(file_bytes)
    except ET.ParseError as e:
        return [{"element": "root", "index": 0,
                 "text": f"XML parse error: {e}", "source_type": "xml"}]

    children = list(root)

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
    """Extract CSV rows as text chunks."""
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
    """
    ext = Path(filename).suffix.lower()
    print(f"[file_processor] extract() called: filename={filename}, ext={ext}, size={len(file_bytes)} bytes")

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