"""PDF validation, inspection and text extraction (PyMuPDF + Tesseract OCR fallback)."""
from __future__ import annotations

import io
import logging
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz

from app.config import get_settings
from app.schemas import ExtractionResult, PageText
from app.utils.text import normalize_text, word_count

logger = logging.getLogger(__name__)

MIN_WORDS_FOR_TEXT_PAGE = 8
_PAGE_NUM = re.compile(r"^(?:page\s*)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?$", re.I)


class PDFValidationError(ValueError):
    """Raised for invalid, unsupported or out-of-limit PDF files."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class PDFInfo:
    page_count: int
    title: str | None
    author: str | None
    text_pages: int
    empty_pages: int
    word_count: int
    is_scanned: bool


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_pdf_bytes(data: bytes) -> int:
    """Validate raw upload bytes. Returns page count or raises PDFValidationError."""
    settings = get_settings()
    if not data:
        raise PDFValidationError("The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise PDFValidationError(
            f"File is too large. Maximum size is {settings.max_upload_mb} MB.", status_code=413
        )
    if not data.lstrip()[:1024].startswith(b"%PDF-") and b"%PDF-" not in data[:1024]:
        raise PDFValidationError("The file is not a valid PDF document.", status_code=415)
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # fitz raises various errors for corrupt files
        raise PDFValidationError("The PDF file is corrupted or cannot be read.") from exc
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise PDFValidationError("Password-protected PDFs are not supported. Please remove the password and retry.")
        if doc.page_count == 0:
            raise PDFValidationError("The PDF does not contain any pages.")
        if doc.page_count > settings.max_pages:
            raise PDFValidationError(
                f"The PDF has {doc.page_count} pages. The maximum supported is {settings.max_pages} pages.",
                status_code=413,
            )
        return doc.page_count
    finally:
        doc.close()


def _meta(doc: fitz.Document, key: str) -> str | None:
    val = (doc.metadata or {}).get(key) or ""
    val = " ".join(val.split())
    return val[:500] or None


def inspect_pdf(path: Path) -> PDFInfo:
    """Fast inspection used at upload time (no OCR)."""
    with fitz.open(path) as doc:
        text_pages = empty = words = image_only = 0
        for page in doc:
            txt = page.get_text("text")
            wc = word_count(txt)
            words += wc
            if wc >= MIN_WORDS_FOR_TEXT_PAGE:
                text_pages += 1
            else:
                if page.get_images(full=False):
                    image_only += 1
                else:
                    empty += 1
        n = doc.page_count
        is_scanned = n > 0 and image_only / n >= 0.5
        return PDFInfo(
            page_count=n,
            title=_meta(doc, "title"),
            author=_meta(doc, "author"),
            text_pages=text_pages,
            empty_pages=empty,
            word_count=words,
            is_scanned=is_scanned,
        )


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def tesseract_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ImportError:  # pragma: no cover
        return False
    return True


def _ocr_page(page: fitz.Page, lang: str) -> str:
    import pytesseract
    from PIL import Image

    pix = page.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, lang=lang, timeout=60)


# ---------------------------------------------------------------------------
# Structured extraction
# ---------------------------------------------------------------------------
def _page_lines(page: fitz.Page) -> list[tuple[str, float, bool]]:
    """Return (text, font_size, bold) for each visual line on the page."""
    out: list[tuple[str, float, bool]] = []
    data = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in line["spans"]).strip()
            chars = sum(len(s["text"]) for s in spans)
            size = sum(s["size"] * len(s["text"]) for s in spans) / max(chars, 1)
            bold = all((s.get("flags", 0) & 16) or "bold" in s.get("font", "").lower() for s in spans)
            out.append((text, round(size, 1), bold))
        out.append(("", 0.0, False))  # block separator -> paragraph break
    return out


def _body_font_size(all_lines: list[list[tuple[str, float, bool]]]) -> float:
    counter: Counter[float] = Counter()
    for lines in all_lines:
        for text, size, _ in lines:
            if text:
                counter[size] += len(text)
    return counter.most_common(1)[0][0] if counter else 11.0


def _is_heading(text: str, size: float, bold: bool, body: float) -> bool:
    words = text.split()
    if not (1 <= len(words) <= 14) or len(text) > 110:
        return False
    if text.endswith((".", ",", ";")) and not re.match(r"^\d+(\.\d+)*\.?\s", text):
        return False
    if _PAGE_NUM.match(text) or not re.search(r"[A-Za-z]{2,}", text):
        return False
    if size >= body * 1.18:
        return True
    return bold and size >= body * 0.98 and len(words) <= 10 and text[:1].isupper()


def _repeated_lines(all_lines: list[list[tuple[str, float, bool]]]) -> set[str]:
    """Detect running headers/footers repeated on many pages."""
    if len(all_lines) < 4:
        return set()
    counter: Counter[str] = Counter()
    for lines in all_lines:
        texts = [t for t, _, _ in lines if t]
        edge = set(texts[:2] + texts[-2:])
        for t in edge:
            counter[re.sub(r"\d+", "#", t.lower())] += 1
    threshold = max(3, int(len(all_lines) * 0.5))
    return {t for t, c in counter.items() if c >= threshold}


def extract_pdf(path: Path, use_ocr: bool | None = None) -> ExtractionResult:
    """Extract page-wise text with heading markers (``## Heading``)."""
    settings = get_settings()
    use_ocr = settings.ocr_enabled if use_ocr is None else use_ocr
    ocr_ok = use_ocr and tesseract_available()
    warnings: list[str] = []

    with fitz.open(path) as doc:
        all_lines = [_page_lines(p) for p in doc]
        body = _body_font_size(all_lines)
        repeated = _repeated_lines(all_lines)

        pages: list[PageText] = []
        ocr_pages: list[int] = []
        empty_pages: list[int] = []
        image_only_pages = 0
        ocr_budget = settings.ocr_max_pages

        for idx, page in enumerate(doc):
            pno = idx + 1
            headings: list[str] = []
            buf: list[str] = []
            last_heading_size: float | None = None
            for text, size, bold in all_lines[idx]:
                if not text:
                    buf.append("")
                    continue
                if _PAGE_NUM.match(text) or re.sub(r"\d+", "#", text.lower()) in repeated:
                    continue
                if _is_heading(text, size, bold, body):
                    # merge multi-line headings (heading line directly followed by another heading line
                    # of the same size, with no body text in between)
                    last = next((j for j in range(len(buf) - 1, -1, -1) if buf[j]), None)
                    if (last is not None and buf[last].startswith("## ") and last_heading_size == size
                            and len(buf[last]) < 70 and not buf[last].rstrip().endswith(("?", ":"))):
                        buf[last] = buf[last] + " " + text
                        headings[-1] = headings[-1] + " " + text
                    else:
                        headings.append(text)
                        buf.extend(["", f"## {text}", ""])
                    last_heading_size = size
                else:
                    buf.append(text)
                    last_heading_size = None
            page_text = normalize_text("\n".join(buf))
            wc = word_count(page_text.replace("## ", ""))
            method = "text"

            if wc < MIN_WORDS_FOR_TEXT_PAGE:
                has_images = bool(page.get_images(full=False))
                if has_images:
                    image_only_pages += 1
                if has_images and ocr_ok and ocr_budget > 0:
                    try:
                        ocr_text = normalize_text(_ocr_page(page, settings.ocr_language))
                        ocr_budget -= 1
                        if word_count(ocr_text) >= 3:
                            page_text, wc, method = ocr_text, word_count(ocr_text), "ocr"
                            ocr_pages.append(pno)
                    except Exception as exc:  # pragma: no cover - depends on tesseract
                        logger.warning("OCR failed on page %s: %s", pno, exc)
                        warnings.append(f"OCR failed on page {pno}.")
                if method == "text" and wc < 3:
                    method = "empty"
                    empty_pages.append(pno)

            pages.append(PageText(page=pno, text=page_text, headings=headings, method=method, word_count=wc))

        n = doc.page_count
        is_scanned = n > 0 and image_only_pages / n >= 0.5

    _fix_hyphenation(pages)

    if image_only_pages and not ocr_ok:
        warnings.append(
            f"{image_only_pages} page(s) appear to be scanned images, but OCR is unavailable; "
            "their content could not be read."
        )
    elif ocr_pages:
        warnings.append(f"OCR was used to read {len(ocr_pages)} scanned page(s): accuracy may vary.")
    if image_only_pages > len(ocr_pages) and ocr_ok and ocr_budget <= 0:
        warnings.append(f"OCR page limit ({settings.ocr_max_pages}) reached; some scanned pages were skipped.")
    if empty_pages:
        warnings.append(f"{len(empty_pages)} page(s) contain no readable text: {_page_ranges(empty_pages)}.")

    return ExtractionResult(
        page_count=n,
        pages=pages,
        is_scanned=is_scanned,
        ocr_pages=ocr_pages,
        empty_pages=empty_pages,
        warnings=warnings,
    )


_HYPHEN_EOL = re.compile(r"([A-Za-z]{2,})-\n([a-z]{2,})")


def _fix_hyphenation(pages: list[PageText]) -> None:
    """Re-join words hyphenated at line ends.

    "photo-\nsynthesis" becomes "photosynthesis" when that word occurs elsewhere in the
    document; otherwise the hyphen is kept ("light-\ndependent" -> "light-dependent").
    """
    vocab = {w.lower() for p in pages for w in re.findall(r"[A-Za-z]{4,}", p.text)}

    def join(m: re.Match) -> str:
        whole = m.group(1) + m.group(2)
        return whole if whole.lower() in vocab else f"{m.group(1)}-{m.group(2)}"

    for p in pages:
        if "-\n" in p.text:
            p.text = _HYPHEN_EOL.sub(join, p.text)


def _page_ranges(pages: list[int]) -> str:
    if not pages:
        return ""
    ranges, start, prev = [], pages[0], pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        ranges.append(f"{start}" if start == prev else f"{start}–{prev}")
        start = prev = p
    ranges.append(f"{start}" if start == prev else f"{start}–{prev}")
    return ", ".join(ranges[:12]) + ("…" if len(ranges) > 12 else "")
