"""Offline heuristic provider ("demo mode").

Works without any API key and is also the automatic fallback when an LLM provider
fails. It is *extractive*: every point comes from sentences in the source text, so
it never invents facts. It uses PDF heading markers, sentence scoring, regex-based
definition / example / process / comparison detection and light-weight
simplification rules.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from app.schemas import (
    ChunkAnalysis,
    Comparison,
    Definition,
    DiagramNode,
    DocumentOverview,
    KeyPoint,
    Slide,
    SlideType,
    SourcedDefinition,
    SourcedText,
    Topic,
    TopicComparison,
)
from app.services.ai.base import AIProvider
from app.utils.text import (
    STOPWORDS as STOP,
    clean_heading,
    is_bullet_line,
    paragraphs,
    shorten,
    split_sentences,
    strip_bullet,
    title_case,
    tokens,
)

_PAGE_MARK = re.compile(r"^\[Page (\d+)\]$")

_DEF_PATTERNS = [
    re.compile(
        r"^(?:An?\s+|The\s+)?(?P<term>[A-Z]?[\w\-’' ()/]{1,60}?)\s+(?:is|are|can be)\s+defined as\s+(?P<def>.{10,})",
    ),
    re.compile(
        r"^(?:An?|The)?\s*(?P<term>[A-Z]?[\w\-’' ()/]{1,50}?)\s+(?:is|are|refers to|means|describes|denotes)\s+"
        r"(?P<def>(?:an?|the|any|one|those|that|process|method|type|set|measure|study|kind|form|ability|state|technique)\b.{10,})",
    ),
    re.compile(r"^(?P<term>[A-Z][\w\-’' ()/]{1,50}?)\s*[:–—]\s+(?P<def>[A-Za-z].{15,})"),
    re.compile(r"^(?P<def>.{15,}?)\s+(?:is|are)\s+(?:called|known as|termed|referred to as)\s+(?:an?\s+|the\s+)?(?P<term>[\w\-’' ]{2,40}?)(?:[,;.]|$)"),
]
_EXAMPLE = re.compile(r"\b(for example|for instance|e\.g\.|such as|an example of|example:|consider)\b", re.I)
_SEQ_WORD = re.compile(r"^(first(ly)?|second(ly)?|third(ly)?|then|next|after that|afterwards|finally|lastly|step \d+)\b[,:]?\s*", re.I)
_NUMBERED = re.compile(r"^\s*\(?(\d{1,2})[.)]\s+")
_VS = re.compile(
    r"(?:differences?\s+between|comparing|comparison of)\s+(?P<a>[\w\- ]{2,40}?)\s+and\s+(?P<b>[\w\- ]{2,40}?)(?:[.,:;]|$)"
    r"|(?P<c>[\w\- ]{2,40}?)\s+(?:vs\.?|versus)\s+(?P<d>[\w\- ]{2,40}?)(?:[.,:;]|$)",
    re.I,
)
_CUE = re.compile(
    r"\b(important|key|main|essential|significant|fundamental|primary|crucial|must|defined|known as|"
    r"consists of|includes?|results? in|causes?|because|therefore|principle|law|theory|function)\b",
    re.I,
)
_META = re.compile(
    r"^(this (chapter|section|unit|lesson|document|module)|in this (chapter|section|unit|lesson)|we (will )?(examine|"
    r"discuss|look at|explore|study)|by the end of (this|the)|the following|below are|as shown)",
    re.I,
)
_FRAMING_TITLE = re.compile(r"^(introduction|overview|summary|conclusions?|review|recap|abstract|preface)\b", re.I)
_CONNECTOR = re.compile(
    r"^(however|moreover|additionally|in addition|furthermore|therefore|thus|hence|also|consequently|"
    r"as a result|in fact|similarly|likewise|on the other hand|in general|generally|overall),?\s+",
    re.I,
)
_SIMPLIFY = [
    (r"\butili[sz]e[sd]?\b", "use"), (r"\butili[sz]ation\b", "use"), (r"\bapproximately\b", "about"),
    (r"\bin order to\b", "to"), (r"\bnumerous\b", "many"), (r"\bdemonstrates?\b", "shows"),
    (r"\bfacilitates?\b", "helps"), (r"\bcommences?\b", "starts"), (r"\bsubsequently\b", "then"),
    (r"\bsufficient\b", "enough"), (r"\bprior to\b", "before"), (r"\ba large number of\b", "many"),
    (r"\bin the event that\b", "if"), (r"\bdue to the fact that\b", "because"), (r"\bat this point in time\b", "now"),
    (r"\bis able to\b", "can"), (r"\bare able to\b", "can"), (r"\bwith regard to\b", "about"),
    (r"\bin spite of the fact that\b", "although"), (r"\bthe majority of\b", "most"),
]


@dataclass
class _Segment:
    title: str | None
    items: list[tuple[int, str]] = field(default_factory=list)  # (page, paragraph)

    @property
    def pages(self) -> list[int]:
        return sorted({p for p, _ in self.items})

    @property
    def words(self) -> int:
        return sum(len(t.split()) for _, t in self.items)


def simplify(text: str) -> str:
    s = _CONNECTOR.sub("", text.strip())
    s = re.sub(r"\s*\([^()]{0,80}\)", "", s)  # drop short parentheticals
    for pat, rep in _SIMPLIFY:
        s = re.sub(pat, rep, s, flags=re.I)
    s = " ".join(s.split())
    return s[:1].upper() + s[1:] if s else s


def _segments(text: str) -> list[_Segment]:
    """Split chunk text into heading-delimited segments with page tracking.

    Paragraphs that continue across a page break are kept together and attributed
    to the page on which they start.
    """
    segs: list[_Segment] = [_Segment(title=None)]
    page = 1
    block_page = 1
    block: list[str] = []

    def flush_block():
        if block:
            for para in paragraphs("\n".join(block)):
                segs[-1].items.append((block_page, para))
            block.clear()

    for line in text.split("\n"):
        m = _PAGE_MARK.match(line.strip())
        if m:
            page = int(m.group(1))
            last = next((b for b in reversed(block) if b.strip()), "")
            if last and not last.rstrip().endswith((".", "!", "?", ":", ";")) and not is_bullet_line(last):
                while block and not block[-1].strip():
                    block.pop()
                continue  # sentence continues on the next page
            flush_block()
            block_page = page
            continue
        if line.startswith("## "):
            flush_block()
            block_page = page
            segs.append(_Segment(title=clean_heading(line[3:])))
            continue
        if not block:
            block_page = page
        block.append(line)
    flush_block()

    segs = [s for s in segs if s.items or s.title]
    # merge segments with almost no body into the next one (heading directly followed by a sub-heading)
    merged: list[_Segment] = []
    for i, s in enumerate(segs):
        if s.words < 25 and i + 1 < len(segs):
            nxt = segs[i + 1]
            nxt.items = s.items + nxt.items
            if s.title and nxt.title and s.words == 0 and len(s.title) + len(nxt.title) < 60 \
                    and not s.title.lower().startswith(("chapter", "unit", "part")):
                nxt.title = f"{s.title}: {nxt.title}" if len(s.title) < 30 else nxt.title
            elif s.title and not nxt.title:
                nxt.title = s.title
            continue
        merged.append(s)
    if len(merged) > 1 and merged[-1].words < 25:
        last = merged.pop()
        merged[-1].items.extend(last.items)
    return [s for s in merged if s.items]


def _sentences(seg: _Segment) -> list[tuple[int, str, bool]]:
    """(page, sentence, from_bullet) for every sentence in the segment."""
    out = []
    for page, para in seg.items:
        if is_bullet_line(para):
            s = strip_bullet(para)
            if len(s.split()) >= 3:
                out.append((page, s, True))
            continue
        for s in split_sentences(para):
            if len(s.split()) >= 5 and re.search(r"[a-z]", s):
                out.append((page, s, False))
    return out


def _score(sentences: list[tuple[int, str, bool]], title: str | None) -> list[float]:
    freq = Counter(t for _, s, _ in sentences for t in tokens(s))
    if not freq:
        return [0.0] * len(sentences)
    top = freq.most_common(1)[0][1]
    title_toks = set(tokens(title or ""))
    scores = []
    for i, (_, s, bullet) in enumerate(sentences):
        toks = tokens(s)
        if not toks:
            scores.append(0.0)
            continue
        base = sum(freq[t] / top for t in toks) / math.sqrt(len(toks))
        base += 0.35 * len(title_toks & set(toks))
        base += 0.4 if _CUE.search(s) else 0
        base += 0.3 if bullet else 0
        base += 0.25 if i < 2 else 0
        base -= 0.9 if _META.search(s) else 0
        n = len(s.split())
        base *= 0.6 if n > 45 else (0.8 if n < 7 else 1.0)
        scores.append(base)
    return scores


def _find_definitions(sentences, title: str | None) -> list[SourcedDefinition]:
    defs: list[SourcedDefinition] = []
    seen: set[str] = set()
    for page, s, from_bullet in sentences:
        for pat in _DEF_PATTERNS:
            if from_bullet and pat is _DEF_PATTERNS[2]:
                continue  # "Label: text" list items are usually not definitions
            m = pat.match(s)
            if not m:
                continue
            term = m.group("term").strip(" ,:;").strip()
            term = re.sub(r"^(?:An?|The)\s+", "", term)
            definition = m.group("def").strip()
            if not (1 <= len(term.split()) <= 6) or len(term) < 2:
                continue
            if len(term.split()) > 3 and " of " in f" {term.lower()} ":
                continue
            if term.lower() in {"this", "it", "these", "they", "there", "that", "which", "he", "she", "we", "one"}:
                continue
            if term.split()[0].lower() in {"this", "these", "it", "they", "there", "such", "each", "all", "some"}:
                continue
            key = term.lower()
            if key in seen:
                break
            seen.add(key)
            full = s[: m.end("term")] if pat is _DEF_PATTERNS[3] else definition
            full = full.rstrip(".") + "."
            defs.append(SourcedDefinition(term=term[:1].upper() + term[1:], definition=full[:600], pages=[page]))
            break
    return defs[:6]


def _find_examples(sentences) -> list[SourcedText]:
    out = []
    for page, s, _ in sentences:
        if _EXAMPLE.search(s) and len(s.split()) >= 6:
            out.append(SourcedText(text=shorten(s, 260), pages=[page]))
    return out[:5]


def _find_steps(seg: _Segment) -> list[str]:
    numbered = [(int(m.group(1)), _NUMBERED.sub("", p)) for _, p in seg.items if (m := _NUMBERED.match(p))]
    if len(numbered) >= 3:
        nums = [n for n, _ in numbered]
        if nums == sorted(nums):
            return [shorten(simplify(t), 120) for _, t in numbered][:8]
    seq = []
    for _, para in seg.items:
        for s in split_sentences(para):
            if _SEQ_WORD.match(s):
                seq.append(shorten(simplify(_SEQ_WORD.sub("", s)), 120))
    if len(seq) >= 3:
        return seq[:8]
    title = (seg.title or "").lower()
    bullets = [strip_bullet(p) for _, p in seg.items if is_bullet_line(p)]
    if len(bullets) >= 3 and re.search(r"\b(steps?|process|procedure|stages?|cycle|phases?|method|how to)\b", title):
        return [shorten(simplify(b), 120) for b in bullets][:8]
    return []


def _find_comparison(seg: _Segment, sentences, page_fallback: list[int]) -> list[TopicComparison]:
    hay = [(seg.title or "")] + [s for _, s, _ in sentences[:12]]
    for text in hay:
        m = _VS.search(text)
        if not m:
            continue
        a = (m.group("a") or m.group("c") or "").strip()
        b = (m.group("b") or m.group("d") or "").strip()
        a = re.sub(r"^(?:the|a|an)\s+", "", a, flags=re.I)
        b = re.sub(r"^(?:the|a|an)\s+", "", b, flags=re.I)
        if not a or not b or a.lower() == b.lower():
            continue
        wa, wb = a.split(), b.split()
        if len(wa) == 1 and len(wb) > 1:  # "C3 and C4 plants" -> "C3 plants" / "C4 plants"
            a = f"{a} {' '.join(wb[1:])}"
        elif len(wb) == 1 and len(wa) > 1:
            b = f"{b} {' '.join(wa[1:])}"
        la, lb = a.lower().split(), b.lower().split()
        ka = next((w for w in la if w not in lb), la[0]).rstrip("s")
        kb = next((w for w in lb if w not in la), lb[0]).rstrip("s")
        left, right, pages = [], [], set()
        for page, s, _ in sentences:
            low = s.lower()
            has_a, has_b = ka in low, kb in low
            if has_a and not has_b and len(left) < 4:
                left.append(shorten(simplify(s), 110)); pages.add(page)
            elif has_b and not has_a and len(right) < 4:
                right.append(shorten(simplify(s), 110)); pages.add(page)
        if len(left) >= 1 and len(right) >= 1:
            return [TopicComparison(
                title=f"{title_case(a)} vs {title_case(b)}", left_title=title_case(a), right_title=title_case(b),
                left=left, right=right, pages=sorted(pages) or page_fallback,
            )]
    return []


def _keyword_title(sentences) -> str:
    freq = Counter(t for _, s, _ in sentences for t in tokens(s))
    words = [w for w, _ in freq.most_common(3)]
    return title_case(" ".join(words)) if words else "Overview"


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        k = re.sub(r"\W+", "", it.lower())[:80]
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


class MockProvider(AIProvider):
    name = "mock"

    # ------------------------------------------------------------------
    def _topic_from_segment(self, seg: _Segment, chunk_pages: list[int], avg_words: float) -> Topic | None:
        sents = _sentences(seg)
        if not sents:
            return None
        scores = _score(sents, seg.title)
        ranked = sorted(range(len(sents)), key=lambda i: scores[i], reverse=True)
        title = seg.title or _keyword_title(sents)

        key_idx = sorted(ranked[: min(10, max(4, len(sents) // 2))])
        key_points = [KeyPoint(text=shorten(sents[i][1], 260), pages=[sents[i][0]]) for i in key_idx]
        simple_idx = sorted(ranked[:5])
        simplified = _dedupe([shorten(simplify(sents[i][1]), 150) for i in simple_idx if scores[i] > 0 or len(sents) < 4])
        summary = " ".join(shorten(sents[i][1], 220) for i in sorted(ranked[:2]))
        best = next((i for i in ranked if not _META.search(sents[i][1]) and len(sents[i][1].split()) >= 7), ranked[0])
        key_takeaway = shorten(simplify(sents[best][1]), 150)

        definitions = _find_definitions(sents, seg.title)
        examples = _find_examples(sents)
        steps = _find_steps(seg)
        comparisons = _find_comparison(seg, sents, seg.pages or chunk_pages)

        ratio = seg.words / max(avg_words, 1)
        importance = 3 + (1 if ratio > 1.3 else 0) - (1 if ratio < 0.5 else 0) + (1 if definitions else 0)
        importance = max(1, min(5, importance))

        visual = None
        if steps:
            visual = "Flowchart showing each step of the process in order"
        elif comparisons:
            visual = "Side-by-side comparison table"
        elif len(definitions) >= 2:
            visual = "Concept map linking the key terms"

        return Topic(
            title=title[:200], summary=summary[:1500], importance=importance,
            key_points=key_points, simplified_points=simplified, definitions=definitions,
            examples=examples, process_steps=steps, comparisons=comparisons,
            visual_suggestion=visual, pages=seg.pages or chunk_pages, key_takeaway=key_takeaway,
        )

    def analyze_chunk(self, chunk_text: str, pages: list[int], context: dict) -> ChunkAnalysis:
        segs = _segments(chunk_text)
        if not segs:
            return ChunkAnalysis(topics=[])
        avg = sum(s.words for s in segs) / len(segs)
        topics = [t for s in segs if (t := self._topic_from_segment(s, pages, avg))]
        return ChunkAnalysis(topics=topics)

    # ------------------------------------------------------------------
    def document_overview(self, topics: list[Topic], context: dict) -> DocumentOverview:
        doc_title = context.get("doc_title") or context.get("doc_name") or "Presentation"
        if not topics:
            return DocumentOverview(title=doc_title, subtitle=None, overview=[], key_takeaways=[], conclusion=[])
        ranked = sorted(topics, key=lambda t: (t.importance, len(t.key_points)), reverse=True)
        body = [t for t in topics if not _FRAMING_TITLE.match(t.title)
                and t.title.lower() != str(doc_title).lower()] or topics
        overview = [f"{t.title}: {shorten(simplify(t.summary), 90)}" if t.summary else t.title for t in body[:5]]
        takeaways = []
        for t in ranked:
            if _FRAMING_TITLE.match(t.title) or not t.simplified_points:
                continue
            takeaways.append(t.key_takeaway or t.simplified_points[0])
            if len(takeaways) >= 5:
                break
        core = [t for t in ranked if not _FRAMING_TITLE.match(t.title)] or ranked
        names = ", ".join(t.title for t in core[:3])
        conclusion = [f"Core ideas covered: {names}."]
        last = topics[-1]
        if last.simplified_points:
            conclusion.append(last.simplified_points[-1])
        defs = sum(len(t.definitions) for t in topics)
        if defs:
            conclusion.append(f"Review the {defs} key term definition{'s' if defs != 1 else ''} to reinforce understanding.")
        return DocumentOverview(
            title=doc_title[:300],
            subtitle=f"Key concepts from {len(topics)} topic{'s' if len(topics) != 1 else ''}",
            overview=_dedupe(overview), key_takeaways=_dedupe(takeaways), conclusion=conclusion,
        )

    # ------------------------------------------------------------------
    def regenerate_slide(self, slide: Slide, source_text: str, context: dict) -> Slide:
        """Rewrite a slide from its source pages.

        Each call (``variant``) rotates through different source sentences and alternates
        between concise and fuller wording, so repeated regeneration gives visibly
        different, still source-grounded content for every slide type.
        """
        segs = _segments(source_text) or [_Segment(title=slide.title)]
        sents = [x for s in segs for x in _sentences(s)]
        new = slide.model_copy(deep=True)
        if not sents:
            return new
        v = int(context.get("variant", 1))
        detailed = context.get("kind") == "detailed"
        scores = _score(sents, slide.title)
        ranked = sorted(range(len(sents)), key=lambda i: scores[i], reverse=True)
        offset = (v * 2) % max(1, len(ranked))
        order = ranked[offset:] + ranked[:offset]
        concise = v % 2 == 0

        def key(text: str) -> str:
            return re.sub(r"\W+", "", text.lower())[:60]

        def best_source(text: str) -> str:
            """Source sentence that best matches a (shortened) point, for fuller wording."""
            toks = set(tokens(text))
            cand = max(sents, key=lambda x: len(toks & set(tokens(x[1]))))
            return cand[1]

        def reword(text: str, short_len: int, long_len: int) -> str:
            if concise:
                return shorten(simplify(text), short_len)
            return shorten(best_source(text), long_len)

        t = slide.type
        if t == SlideType.definition:
            defs = _find_definitions(sents, slide.title) or [
                SourcedDefinition(term=d.term, definition=d.definition) for d in slide.definitions]
            if defs:
                k = v % len(defs)
                defs = defs[k:] + defs[:k]
                new.definitions = [Definition(term=d.term,
                                              definition=shorten(simplify(d.definition), 160) if concise
                                              else d.definition)
                                   for d in defs[:max(3, len(slide.definitions) or 3)][:4]]
        elif t == SlideType.process:
            steps = [st for sg in segs for st in _find_steps(sg)] or list(slide.steps)
            if steps:
                new.steps = [reword(st, 70, 140) for st in steps[:6]]
        elif t == SlideType.comparison:
            comp = next((c for sg in segs if (c := _find_comparison(sg, _sentences(sg), slide.source_pages))), None)
            base = slide.comparison
            if comp:
                left, right = comp[0].left, comp[0].right
                lt, rt = comp[0].left_title, comp[0].right_title
            elif base:
                left, right, lt, rt = base.left, base.right, base.left_title, base.right_title
            else:
                left = right = []
                lt = rt = ""
            if left or right:
                k = v % max(1, min(len(left), len(right)) or 1)
                new.comparison = Comparison(left_title=lt, right_title=rt,
                                            left=[reword(x, 80, 150) for x in (left[k:] + left[:k])[:4]],
                                            right=[reword(x, 80, 150) for x in (right[k:] + right[:k])[:4]])
        elif t == SlideType.section:
            pick = next((i for i in order if not _META.search(sents[i][1])), order[0])
            new.subtitle = shorten(simplify(sents[pick][1]), 150)
        elif t == SlideType.diagram and slide.diagram is not None:
            d = new.diagram
            if d.kind == "timeline":
                for node in d.nodes:
                    ltoks = set(tokens(node.label))
                    matches = sorted(range(len(sents)), key=lambda i: -len(ltoks & set(tokens(sents[i][1]))))
                    matches = [i for i in matches if ltoks & set(tokens(sents[i][1]))] or matches
                    node.detail = shorten(simplify(sents[matches[v % len(matches)]][1]), 80)
            else:
                current = {key(n.label) for n in d.nodes}
                phrases = [p for p in _ranked_phrases(sents, d.center or slide.title) if key(p) not in current]
                if phrases:
                    k = v % max(1, len(phrases))
                    phrases = phrases[k:] + phrases[:k]
                    d.nodes = [DiagramNode(label=p) for p in phrases[: max(3, len(d.nodes) or 5)][:6]]
        elif t != SlideType.title:
            existing = {key(b) for b in slide.bullets}
            n = len(slide.bullets) or (5 if detailed else 4)
            fresh = [i for i in order if key(simplify(sents[i][1])) not in existing]
            pick = sorted((fresh or order)[:n])
            max_len = 200 if detailed else 130
            new.bullets = _dedupe([reword(sents[i][1], max_len - 40, max_len) for i in pick])
            if t == SlideType.content and new.diagram and new.diagram.kind == "mindmap":
                current = {key(nd.label) for nd in new.diagram.nodes}
                phrases = [p for p in _ranked_phrases(sents, slide.title) if key(p) not in current]
                if len(phrases) >= 3:
                    new.diagram.nodes = [DiagramNode(label=p) for p in phrases[:len(new.diagram.nodes) or 4]]
        new.notes = " ".join(shorten(sents[i][1], 220) for i in sorted(order[:3]))
        return new


def _ranked_phrases(sents, title: str) -> list[str]:
    """Frequent key phrases (bigrams first) in the source sentences, excluding title words."""
    title_toks = set(tokens(title))
    uni: Counter[str] = Counter()
    bi: Counter[str] = Counter()
    for _, text, _ in sents:
        low = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]+", text)]
        for i, w in enumerate(low):
            if w in STOP or len(w) < 4 or w in title_toks:
                continue
            uni[w] += 1
            if i + 1 < len(low) and low[i + 1] not in STOP and len(low[i + 1]) >= 3:
                bi[f"{w} {low[i + 1]}"] += 1
    ranked = [(p, c * 1.6) for p, c in bi.items() if c >= 2] + [(w, float(c)) for w, c in uni.items() if c >= 2]
    ranked.sort(key=lambda x: -x[1])
    out: list[str] = []
    for p, _ in ranked:
        if any(p in o.lower() or o.lower() in p for o in out):
            continue
        out.append(title_case(p))
        if len(out) >= 12:
            break
    return out
