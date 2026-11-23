"""Split extracted documents into topic-aware chunks for AI processing."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import ExtractionResult


@dataclass
class Chunk:
    index: int
    pages: list[int] = field(default_factory=list)
    parts: list[tuple[int, str]] = field(default_factory=list)  # (page, text)

    @property
    def text(self) -> str:
        """Text with explicit page markers so the model can cite pages."""
        return "\n\n".join(f"[Page {p}]\n{t}" for p, t in self.parts)

    @property
    def char_count(self) -> int:
        return sum(len(t) for _, t in self.parts)

    @property
    def page_range(self) -> str:
        if not self.pages:
            return ""
        a, b = min(self.pages), max(self.pages)
        return f"{a}" if a == b else f"{a}–{b}"


def _split_long(text: str, limit: int) -> list[str]:
    """Split a single very long page on paragraph boundaries."""
    paras = text.split("\n\n")
    out, buf, size = [], [], 0
    for p in paras:
        while len(p) > limit:  # pathological single paragraph
            if buf:
                out.append("\n\n".join(buf))
                buf, size = [], 0
            out.append(p[:limit])
            p = p[limit:]
        if size + len(p) > limit and buf:
            out.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(p)
        size += len(p) + 2
    if buf:
        out.append("\n\n".join(buf))
    return out


def chunk_document(extraction: ExtractionResult, max_chars: int = 12000) -> list[Chunk]:
    """Group pages into chunks of at most ``max_chars``.

    A new chunk prefers to start at a page that opens with a heading once the current
    chunk is reasonably full (>= 60%), so topics are less likely to be split.
    Empty pages are skipped (they are reported as warnings separately).
    """
    chunks: list[Chunk] = []
    current = Chunk(index=0)

    def flush():
        nonlocal current
        if current.parts:
            chunks.append(current)
            current = Chunk(index=len(chunks))

    for page in extraction.pages:
        text = page.text.strip()
        if not text or page.method == "empty":
            continue
        pieces = _split_long(text, max_chars) if len(text) > max_chars else [text]
        for piece in pieces:
            starts_topic = piece.lstrip().startswith("## ")
            full = current.char_count + len(piece) > max_chars
            soft = starts_topic and current.char_count >= max_chars * 0.6
            if current.parts and (full or soft):
                flush()
            current.parts.append((page.page, piece))
            if page.page not in current.pages:
                current.pages.append(page.page)
    flush()
    return chunks
