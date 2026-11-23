"""Content pipeline: chunk analyses -> merged topics -> Summary / Detailed slide decks.

The AI (or offline engine) does the *understanding*; this module does the
*instructional layout*: it decides which slide types to use, keeps slides
uncrowded, respects slide budgets and attaches source page references.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from collections import Counter

from app.schemas import (
    Comparison,
    Definition,
    Diagram,
    DiagramNode,
    DocumentOverview,
    Slide,
    SlideType,
    Topic,
)
from app.utils.text import STOPWORDS, shorten, title_case, tokens

MAX_BULLETS = 5
MAX_DEFS_PER_SLIDE = 3
MAX_STEPS = 6


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def merge_topics(topics: list[Topic]) -> list[Topic]:
    """Merge adjacent topics with the same title (split across chunk boundaries)."""
    merged: list[Topic] = []
    for t in topics:
        if merged and _norm(merged[-1].title) == _norm(t.title):
            m = merged[-1]
            m.key_points += t.key_points
            m.simplified_points += t.simplified_points
            m.definitions += t.definitions
            m.examples += t.examples
            m.process_steps += t.process_steps
            m.comparisons += t.comparisons
            m.pages = sorted(set(m.pages) | set(t.pages))
            m.importance = max(m.importance, t.importance)
            if t.summary and len(m.summary) < 600:
                m.summary = (m.summary + " " + t.summary).strip()
            m.visual_suggestion = m.visual_suggestion or t.visual_suggestion
        else:
            merged.append(t.model_copy(deep=True))
    return merged


def _chunks(items: list, n: int) -> list[list]:
    return [items[i : i + n] for i in range(0, len(items), n)]


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        k = _norm(it)[:80]
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _pages(*groups: list[int]) -> list[int]:
    out: set[int] = set()
    for g in groups:
        out |= set(g)
    return sorted(out)


_FRAMING = re.compile(r"^(introduction|overview|summary|conclusions?|review|recap|key takeaways|abstract|preface)\b",
                      re.I)


def _is_framing(title: str) -> bool:
    return bool(_FRAMING.match(title.strip()))


_CYCLE = re.compile(r"\b(cycle|cyclic|loop|recycl\w*|regenerat\w*|repeat\w*|continu\w* again)\b", re.I)


def short_label(text: str, max_words: int = 5, max_chars: int = 38) -> str:
    """Compact label for a diagram node."""
    s = re.sub(r"\s*[:–—(].*$", "", text).strip() or text
    words = s.split()
    if len(words) > max_words:
        s = " ".join(words[:max_words]) + "…"
    return s if len(s) <= max_chars else s[: max_chars - 1].rstrip() + "…"


def key_terms(t: Topic, n: int = 5) -> list[str]:
    """Key terms of a topic for concept maps: defined terms first, then frequent phrases."""
    terms: list[str] = []
    title_norm = _norm(t.title)
    for d in t.definitions:
        k = _norm(d.term)
        if len(d.term.split()) <= 4 and k not in {_norm(x) for x in terms} and k not in title_norm:
            terms.append(d.term)
    title_toks = set(tokens(t.title))
    # count over distinct source sentences only (simplified points repeat the key points)
    texts = [k.text for k in t.key_points] or t.simplified_points
    uni: Counter[str] = Counter()
    bi: Counter[str] = Counter()
    for text in texts:
        words = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", text)
        low = [w.lower() for w in words]
        for i, w in enumerate(low):
            if w in STOPWORDS or len(w) < 4 or w in title_toks:
                continue
            uni[w] += 1
            if i + 1 < len(low) and low[i + 1] not in STOPWORDS and len(low[i + 1]) >= 3:
                bi[f"{w} {low[i + 1]}"] += 1
    ranked = [(p, c * 1.6) for p, c in bi.items() if c >= 2] + [(w, float(c)) for w, c in uni.items() if c >= 2]
    ranked.sort(key=lambda x: -x[1])
    for phrase, _ in ranked:
        if len(terms) >= n:
            break
        if any(phrase in _norm(x) or _norm(x) in phrase for x in terms):
            continue
        terms.append(title_case(phrase) if phrase.islower() else phrase)
    return terms[:n]


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _mindmap(center: str, labels: list[str]) -> Diagram:
    return Diagram(kind="mindmap", center=short_label(center, 6, 48),
                   nodes=[DiagramNode(label=_cap(short_label(x))) for x in labels[:6]])


def _roadmap(title: str, topics: list[Topic], priority: float, max_nodes: int = 6) -> _Candidate | None:
    core = [t for t in topics if not _is_framing(t.title)] or topics
    if len(core) < 3:
        return None
    if len(core) > max_nodes:  # keep the most important, in document order
        keep = sorted(sorted(range(len(core)), key=lambda i: -core[i].importance)[:max_nodes])
        core = [core[i] for i in keep]
    nodes = [DiagramNode(label=short_label(t.title),
                         detail=shorten(t.key_takeaway or (t.simplified_points or [t.summary or ""])[0], 80) or None)
             for t in core]
    return _Candidate(Slide(
        type=SlideType.diagram, title=title, diagram=Diagram(kind="timeline", nodes=nodes),
        source_pages=_pages(*[t.pages for t in core]),
        notes="Roadmap of the main topics, in the order they are covered: " + " → ".join(t.title for t in core),
        visual_suggestion="Timeline of topics",
    ), priority)


def _big_picture(overview: DocumentOverview, topics: list[Topic], priority: float) -> _Candidate | None:
    core = [t for t in topics if not _is_framing(t.title)] or topics
    if len(core) < 3:
        return None
    core = sorted(core, key=lambda t: -t.importance)[:6]
    core = [t for t in topics if t in core]
    return _Candidate(Slide(
        type=SlideType.diagram, title="The Big Picture",
        diagram=_mindmap(overview.title, [t.title for t in core]),
        source_pages=_pages(*[t.pages for t in core]),
        notes="How the main topics connect to the central theme: " + ", ".join(t.title for t in core),
        visual_suggestion="Concept map of the main topics",
    ), priority)


@dataclass
class _Candidate:
    slide: Slide
    priority: float
    group: int | None = None  # section group (detailed deck) – used to drop empty sections


def _select(cands: list[_Candidate], budget: int) -> list[Slide]:
    """Keep the highest-priority slides within ``budget``; preserve original order."""
    if len(cands) > budget:
        keep = sorted(range(len(cands)), key=lambda i: cands[i].priority, reverse=True)[:budget]
        cands = [cands[i] for i in sorted(keep)]
    # drop section dividers that ended up with no content slides
    result: list[_Candidate] = []
    for i, c in enumerate(cands):
        if c.slide.type == SlideType.section:
            has_child = any(o.group == c.group and o.slide.type != SlideType.section for o in cands[i + 1 :])
            if not has_child:
                continue
        result.append(c)
    return [c.slide for c in result]


def _title_slide(overview: DocumentOverview, kind: str, doc_name: str) -> Slide:
    label = "Summary Presentation" if kind == "summary" else "Detailed Presentation"
    return Slide(
        type=SlideType.title,
        title=overview.title,
        subtitle=f"{label} • {overview.subtitle}" if overview.subtitle else label,
        notes=None,
    )


def _definition_slides(defs: list, title: str, priority: float, group=None, max_slides: int = 2,
                       summary: bool = False) -> list[_Candidate]:
    out = []
    seen = set()
    uniq = []
    for d in defs:
        k = _norm(d.term)
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    for i, part in enumerate(_chunks(uniq, MAX_DEFS_PER_SLIDE)[:max_slides]):
        out.append(_Candidate(Slide(
            type=SlideType.definition,
            title=title if i == 0 else f"{title} (cont.)",
            definitions=[Definition(term=d.term, definition=shorten(d.definition, 200 if summary else 320))
                         for d in part],
            source_pages=_pages(*[d.pages for d in part]),
            notes="Key terms: " + "; ".join(f"{d.term} — {d.definition}" for d in part),
            visual_suggestion="Concept map linking these terms" if len(part) > 1 else None,
        ), priority - i * 5, group))
    return out


def _process_slide(t: Topic, priority: float, group=None) -> _Candidate | None:
    steps = _dedupe(t.process_steps)[:MAX_STEPS]
    if len(steps) < 3:
        return None
    is_cycle = bool(_CYCLE.search(t.title) or _CYCLE.search(" ".join(steps[-2:])))
    return _Candidate(Slide(
        type=SlideType.process, title=f"{t.title}: Process" if "process" not in t.title.lower() else t.title,
        steps=[shorten(s, 110) for s in steps], source_pages=t.pages,
        diagram=Diagram(kind="cycle" if is_cycle else "flow"),
        notes="Walk through each step in order. " + " → ".join(steps),
        visual_suggestion=t.visual_suggestion or "Flowchart of the steps",
    ), priority, group)


def _comparison_slide(t: Topic, priority: float, group=None) -> _Candidate | None:
    if not t.comparisons:
        return None
    c = t.comparisons[0]
    if not c.left or not c.right:
        return None
    return _Candidate(Slide(
        type=SlideType.comparison, title=c.title or t.title,
        comparison=Comparison(left_title=c.left_title, right_title=c.right_title,
                              left=[shorten(x, 120) for x in c.left[:4]], right=[shorten(x, 120) for x in c.right[:4]]),
        source_pages=c.pages or t.pages,
        notes=f"Compare {c.left_title} and {c.right_title} point by point.",
        visual_suggestion="Side-by-side comparison table",
    ), priority, group)


# ---------------------------------------------------------------------------
# Summary deck
# ---------------------------------------------------------------------------
def build_summary(topics: list[Topic], overview: DocumentOverview, doc_name: str,
                  target: int = 12, include_notes: bool = True) -> list[Slide]:
    cands: list[_Candidate] = [_Candidate(_title_slide(overview, "summary", doc_name), 1000)]
    roadmap = _roadmap("Topic Roadmap", topics, 900)
    if roadmap:
        cands.append(roadmap)
    elif overview.overview:
        cands.append(_Candidate(Slide(
            type=SlideType.content, title="What This Presentation Covers",
            bullets=[shorten(b, 120) for b in overview.overview[:MAX_BULLETS]],
            notes="Overview of the main topics in the document.",
        ), 900))

    for idx, t in enumerate(topics):
        bullets = _dedupe(t.simplified_points) or [shorten(k.text, 150) for k in t.key_points]
        bullets = [shorten(b, 150) for b in bullets][:MAX_BULLETS]
        if not bullets:
            continue
        imp = t.importance - (2 if _is_framing(t.title) else 0)
        base = 100 + imp * 20 - idx * 0.1
        notes = t.summary if include_notes else None
        # Use the most visual slide type available for the topic (one slide per topic).
        special = _process_slide(t, base) or _comparison_slide(t, base)
        if special:
            special.slide.title = t.title
            special.slide.notes = "\n".join(filter(None, [notes, "Key points: " + " ".join(bullets)]))
            cands.append(special)
        else:
            terms = key_terms(t)
            diagram = _mindmap(t.title, terms) if len(terms) >= 3 else None
            cands.append(_Candidate(Slide(
                type=SlideType.content, title=t.title, bullets=bullets[:4] if diagram else bullets,
                source_pages=t.pages, notes=notes, visual_suggestion=t.visual_suggestion, diagram=diagram,
            ), base))
        # optional second view of important topics (only used when budget allows)
        shown = {_norm(b)[:60] for b in bullets}
        extra = [shorten(k.text, 150) for k in t.key_points if _norm(k.text)[:60] not in shown]
        if special and len(bullets) >= 3:
            extra = bullets
        if imp >= 4 and len(extra) >= 3:
            cands.append(_Candidate(Slide(
                type=SlideType.content, title=f"{t.title}: Key Details", bullets=extra[:4],
                source_pages=_pages(*[k.pages for k in t.key_points]) or t.pages, notes=notes,
            ), 40 + imp * 5 - idx * 0.1))

    all_defs = sorted((d for t in topics for d in t.definitions),
                      key=lambda d: -next((t.importance for t in topics if d in t.definitions), 3))
    if all_defs:
        # place glossary after topics
        defs = sorted(all_defs[:6], key=lambda d: d.pages[0] if d.pages else 0)
        cands += _definition_slides(defs, "Important Definitions", 170, max_slides=2, summary=True)

    if (bp := _big_picture(overview, topics, 175)):
        cands.append(bp)

    if overview.key_takeaways:
        cands.append(_Candidate(Slide(
            type=SlideType.takeaways, title="Key Takeaways",
            bullets=[shorten(b, 120) for b in overview.key_takeaways[:MAX_BULLETS]],
            source_pages=_pages(*[t.pages for t in topics]),
            notes="The most important points to remember.",
        ), 950))
    cands.append(_Candidate(Slide(
        type=SlideType.conclusion, title="Conclusion",
        bullets=[shorten(b, 140) for b in (overview.conclusion or ["Thank you!"])[:4]],
        source_pages=_pages(*[t.pages for t in topics]),
        notes="Wrap up and invite questions.",
    ), 990))
    slides = _select(cands, target)
    _fix_source_pages(slides)
    return slides


# ---------------------------------------------------------------------------
# Detailed deck
# ---------------------------------------------------------------------------
def _section_title(group: list[Topic]) -> str:
    for t in group:
        if not _is_framing(t.title):
            return t.title
    return group[0].title


def _group_topics(topics: list[Topic]) -> list[list[Topic]]:
    if len(topics) <= 6:
        return [[t] for t in topics]
    n_groups = min(7, max(3, round(len(topics) / 3)))
    size = -(-len(topics) // n_groups)
    return _chunks(topics, size)


def build_detailed(topics: list[Topic], overview: DocumentOverview, doc_name: str,
                   target: int = 24, include_notes: bool = True) -> list[Slide]:
    groups = _group_topics(topics)
    cands: list[_Candidate] = [_Candidate(_title_slide(overview, "detailed", doc_name), 1000)]
    agenda = [_section_title(g) for g in groups]
    if len(groups) > 1:
        nodes = [DiagramNode(label=short_label(a),
                             detail=shorten(" • ".join(t.title for t in g if t.title != a), 80) or None)
                 for a, g in zip(agenda[:7], groups)]
        cands.append(_Candidate(Slide(
            type=SlideType.diagram, title="Agenda", diagram=Diagram(kind="timeline", nodes=nodes),
            bullets=[shorten(a, 90) for a in agenda[:7]],
            source_pages=_pages(*[t.pages for t in topics]),
            notes="Roadmap of the sections in this presentation: " + " → ".join(agenda),
        ), 900))
    if overview.overview and not (topics and _is_framing(topics[0].title)):
        cands.append(_Candidate(Slide(
            type=SlideType.content, title="Introduction",
            bullets=[shorten(b, 160) for b in overview.overview[:MAX_BULLETS]],
            notes="What this document is about.",
        ), 300))

    order = 0
    for gi, group in enumerate(groups):
        order += 1
        sec_title = _section_title(group)
        sub = " • ".join(t.title for t in group if t.title != sec_title) or (shorten(group[0].summary, 140) if group[0].summary else None)
        cands.append(_Candidate(Slide(
            type=SlideType.section, title=sec_title, subtitle=sub,
            source_pages=_pages(*[t.pages for t in group]),
            notes=f"Section {gi + 1}: {', '.join(t.title for t in group)}",
        ), 400, gi))
        for t in group:
            imp = t.importance
            points = _dedupe([k.text for k in t.key_points])
            point_pages = {k.text: k.pages for k in t.key_points}
            if not points:
                points = _dedupe(t.simplified_points)
            terms = key_terms(t)
            first = [shorten(b, 200) for b in points[:4]]
            diagram = _mindmap(t.title, terms) if len(terms) >= 3 and sum(map(len, first)) <= 720 else None
            # with a concept map the first slide carries 4 points, the rest continue on later slides
            parts = ([points[:4]] + _chunks(points[4:], MAX_BULLETS)) if diagram else _chunks(points, MAX_BULLETS)
            for pi, part in enumerate(parts[:3]):
                title = t.title if pi == 0 else f"{t.title} (cont.)"
                with_map = diagram is not None and pi == 0
                cands.append(_Candidate(Slide(
                    type=SlideType.content, title=title,
                    bullets=[shorten(b, 200 if with_map else 240) for b in part],
                    source_pages=_pages(*[point_pages.get(b, t.pages) for b in part]) or t.pages,
                    notes=(t.summary if include_notes else None),
                    visual_suggestion=t.visual_suggestion if pi == 0 else None,
                    diagram=diagram if with_map else None,
                ), (200 + imp * 15 if pi == 0 else 80 + imp * 8 - pi * 10) - order * 0.01, gi))
            if (p := _process_slide(t, 205 + imp * 5, gi)):
                cands.append(p)
            if (c := _comparison_slide(t, 205 + imp * 5, gi)):
                cands.append(c)
            if t.examples:
                ex = _dedupe([e.text for e in t.examples])[:4]
                cands.append(_Candidate(Slide(
                    type=SlideType.example, title=f"Examples: {t.title}",
                    bullets=[shorten(e, 220) for e in ex],
                    source_pages=_pages(*[e.pages for e in t.examples]),
                    notes="Examples taken directly from the source document.",
                ), 90 + imp * 8, gi))
        group_defs = [d for t in group for d in t.definitions]
        if group_defs:
            for k, cand in enumerate(_definition_slides(group_defs, f"Key Terms: {sec_title}", 190, gi, max_slides=3)):
                cand.priority = 190 + 4 * len(cand.slide.definitions) - k * 25
                cands.append(cand)

    if (bp := _big_picture(overview, topics, 330)):
        cands.append(bp)
    if overview.key_takeaways:
        cands.append(_Candidate(Slide(
            type=SlideType.takeaways, title="Key Takeaways",
            bullets=[shorten(b, 150) for b in overview.key_takeaways[:6]],
            source_pages=_pages(*[t.pages for t in topics]),
            notes="Summarise the essential learning points.",
        ), 950))
    cands.append(_Candidate(Slide(
        type=SlideType.conclusion, title="Conclusion",
        bullets=[shorten(b, 160) for b in (overview.conclusion or ["Thank you!"])[:4]],
        source_pages=_pages(*[t.pages for t in topics]),
        notes="Conclude and invite questions.",
    ), 990))
    slides = _select(cands, target)
    _fix_source_pages(slides)
    return slides


def _fix_source_pages(slides: list[Slide]) -> None:
    for s in slides:
        s.source_pages = sorted({p for p in s.source_pages if p > 0})


def build_decks(topics: list[Topic], overview: DocumentOverview, doc_name: str, kinds: list[str],
                summary_target: int, detailed_target: int, include_notes: bool = True) -> dict[str, list[Slide]]:
    topics = merge_topics(topics)
    for t in topics:
        if _norm(t.title) == _norm(overview.title) or _norm(t.title) == _norm(doc_name.rsplit(".", 1)[0]):
            t.title = "Introduction"
    out: dict[str, list[Slide]] = {}
    if "summary" in kinds:
        out["summary"] = build_summary(topics, overview, doc_name, summary_target, include_notes)
    if "detailed" in kinds:
        out["detailed"] = build_detailed(topics, overview, doc_name, detailed_target, include_notes)
    return out
