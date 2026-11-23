"""Text processing helpers used by extraction, chunking and the offline engine."""
from __future__ import annotations

import re

_WS = re.compile(r"[ \t ]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_ABBREV = re.compile(r"\b(e\.g|i\.e|etc|vs|Fig|fig|Dr|Mr|Mrs|Ms|Prof|No|approx|cf|al)\.", re.I)
_BULLET_PREFIX = re.compile(r"^\s*(?:[-•▪◦●○■□➢►*·]|\(?\d{1,2}[.)]|\(?[a-zA-Z][.)])\s+")

STOPWORDS = frozenset(
    """a about above after again against all also am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for from
    further had has have having he her here hers herself him himself his how i if in into is it its
    itself just let me more most my myself no nor not now of off on once only or other our ours
    ourselves out over own same she should so some such than that the their theirs them themselves
    then there these they this those through to too under until up very was we were what when where
    which while who whom why will with would you your yours yourself yourselves may might must shall
    one two use used using also however therefore thus hence within without upon via per each many
    much often well like new example examples called known figure table page chapter section""".split()
)


def normalize_text(text: str) -> str:
    """Clean raw PDF text while preserving paragraph breaks."""
    text = text.replace("\r", "\n").replace("­", "")
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if not ln:
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(ln)
    return "\n".join(out).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def paragraphs(text: str) -> list[str]:
    """Join wrapped lines into paragraphs. Bullet-like lines stay separate."""
    paras: list[str] = []
    buf: list[str] = []
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            if buf:
                paras.append(" ".join(buf))
                buf = []
            continue
        if _BULLET_PREFIX.match(s):
            if buf:
                paras.append(" ".join(buf))
            buf = [s]
            continue
        buf.append(s)
    if buf:
        paras.append(" ".join(buf))
    return [p for p in paras if p.strip()]


def split_sentences(text: str) -> list[str]:
    protected = _ABBREV.sub(lambda m: m.group(0).replace(".", "<DOT>"), text)
    parts = _SENT_SPLIT.split(protected)
    sentences = []
    for p in parts:
        s = " ".join(p.replace("<DOT>", ".").split())
        if len(s) > 2:
            sentences.append(s)
    return sentences


def strip_bullet(text: str) -> str:
    return _BULLET_PREFIX.sub("", text).strip()


def is_bullet_line(text: str) -> bool:
    return bool(_BULLET_PREFIX.match(text))


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower()) if t not in STOPWORDS]


def shorten(text: str, max_chars: int = 160) -> str:
    """Shorten a sentence to a bullet: trim filler openers and cut on a word boundary."""
    s = " ".join(text.split())
    s = re.sub(
        r"^(?:In (?:this|the) (?:chapter|section|unit|lesson|document),?\s*(?:we\s+(?:will\s+)?)?)",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"^(?:It is important to note that|Note that|Basically,|In other words,)\s*", "", s, flags=re.I)
    s = s[:1].upper() + s[1:] if s else s
    if len(s) <= max_chars:
        return s.rstrip()
    cut = s[:max_chars]
    # prefer cutting at a clause boundary
    for sep in ("; ", ", which", ", where", " — ", ": ", ", "):
        idx = cut.rfind(sep)
        if idx > max_chars * 0.55:
            return cut[:idx].rstrip(" ,;:") + "…"
    idx = cut.rfind(" ")
    return (cut[:idx] if idx > 0 else cut).rstrip(" ,;:") + "…"


def title_case(text: str) -> str:
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "via"}
    words = text.split()
    out = []
    for i, w in enumerate(words):
        if w.isupper() and len(w) > 1:
            out.append(w if len(w) <= 5 else w.capitalize())
        elif i > 0 and w.lower() in small:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def clean_heading(text: str) -> str:
    s = " ".join(text.split()).strip(" .:-–—")
    s = re.sub(r"^(?:chapter|section|unit|part|lesson)\s+[\dIVXivx]+[.:]?\s*", "", s, flags=re.I)
    s = re.sub(r"^\d+(?:\.\d+)*[.)]?\s+", "", s)
    return title_case(s) if s.isupper() else s
