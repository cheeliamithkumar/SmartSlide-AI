"""Unit tests: chunking, composer budgets, PPTX builder, utilities, cleanup."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pptx import Presentation as PptxPresentation

from app.schemas import (
    Comparison, Definition, DocumentOverview, ExtractionResult, KeyPoint, PageText, Slide, SlideType, Topic,
)
from app.services.chunker import chunk_document
from app.services.content_processor import build_detailed, build_summary, merge_topics
from app.services.pptx_builder import fit_font_size, render_presentation
from app.utils.files import safe_filename, slugify
from app.utils.text import shorten, split_sentences


def _topic(i, imp=3, **kw):
    return Topic(title=f"Topic {i}", summary=f"Summary {i}.", importance=imp, pages=[i],
                 key_points=[KeyPoint(text=f"Point {i}.{k} about the topic", pages=[i]) for k in range(7)],
                 simplified_points=[f"Simple {i}.{k}" for k in range(4)], **kw)


OVERVIEW = DocumentOverview(title="Doc", subtitle="Sub", overview=["a", "b"], key_takeaways=["x", "y"],
                            conclusion=["done"])


def test_chunking_respects_limit_and_pages():
    pages = [PageText(page=i, text=("## Heading %d\n" % i) + "word " * 800, word_count=800) for i in range(1, 11)]
    pages.append(PageText(page=11, text="", method="empty"))
    chunks = chunk_document(ExtractionResult(page_count=11, pages=pages), max_chars=9000)
    assert len(chunks) > 1
    assert all(c.char_count <= 9000 for c in chunks)
    covered = [p for c in chunks for p in c.pages]
    assert covered == list(range(1, 11))  # every non-empty page kept, in order, empty skipped
    assert "[Page 1]" in chunks[0].text


def test_chunking_splits_huge_page():
    pages = [PageText(page=1, text="\n\n".join(["para " * 300] * 10), word_count=3000)]
    chunks = chunk_document(ExtractionResult(page_count=1, pages=pages), max_chars=4000)
    assert len(chunks) >= 3 and all(c.pages == [1] for c in chunks)


def test_merge_topics_across_chunks():
    a, b = _topic(1), _topic(1)
    b.pages = [2]
    merged = merge_topics([a, b, _topic(3)])
    assert len(merged) == 2 and merged[0].pages == [1, 2]


def test_summary_respects_budget():
    topics = [_topic(i, imp=5 if i % 3 == 0 else 3) for i in range(1, 25)]
    slides = build_summary(topics, OVERVIEW, "doc.pdf", target=12)
    assert len(slides) == 12
    assert slides[0].type == SlideType.title and slides[-1].type == SlideType.conclusion
    titles = [s.title for s in slides]
    assert "Topic 3" in titles  # important topics kept


def test_detailed_respects_budget_and_sections():
    topics = [_topic(i, definitions=[{"term": f"T{i}", "definition": "d", "pages": [i]}]) for i in range(1, 15)]
    slides = build_detailed(topics, OVERVIEW, "doc.pdf", target=30)
    assert len(slides) <= 30
    sections = [i for i, s in enumerate(slides) if s.type == SlideType.section]
    assert sections
    for i in sections:  # no empty section dividers
        assert slides[i + 1].type not in (SlideType.section, SlideType.takeaways, SlideType.conclusion)
    assert all(len(s.bullets) <= 5 for s in slides)


def test_pptx_builder_all_slide_types(tmp_path: Path):
    slides = [
        Slide(type=SlideType.title, title="Title", subtitle="Sub"),
        Slide(type=SlideType.section, title="Section", subtitle="desc", source_pages=[1]),
        Slide(type=SlideType.content, title="Content", bullets=["a " * 30, "b", "c", "d"], source_pages=[1, 2, 3]),
        Slide(type=SlideType.content, title="Cards", bullets=["one", "two", "three"]),
        Slide(type=SlideType.definition, title="Defs", definitions=[Definition(term="X", definition="Y is z")]),
        Slide(type=SlideType.comparison, title="Cmp",
              comparison=Comparison(left_title="A", right_title="B", left=["a1", "a2"], right=["b1"])),
        Slide(type=SlideType.process, title="Proc", steps=["s1", "s2", "s3", "s4", "s5"]),
        Slide(type=SlideType.example, title="Ex", bullets=["e1"]),
        Slide(type=SlideType.takeaways, title="Take", bullets=["t1", "t2", "t3"]),
        Slide(type=SlideType.conclusion, title="End", bullets=["bye"], notes="notes here"),
    ]
    for theme in ("modern_education", "minimal_white", "professional_blue", "dark_academic"):
        out = render_presentation(slides, theme, "doc.pdf", "summary", tmp_path / f"{theme}.pptx")
        prs = PptxPresentation(str(out))
        assert len(prs.slides) == len(slides)
        assert prs.slide_width > prs.slide_height  # 16:9
    assert "notes here" in prs.slides[-1].notes_slide.notes_text_frame.text


def test_fit_font_size_shrinks_for_long_text():
    assert fit_font_size(["short"], 10, 5) == 22
    assert fit_font_size(["long text " * 80] * 5, 10, 5) < 16


def test_safe_filename():
    assert safe_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert safe_filename("C:\\Users\\x\\My File (1).pdf") == "My File _1_.pdf"
    assert safe_filename("") == "document.pdf"
    assert safe_filename("ü" * 300 + ".pdf").endswith(".pdf")
    assert slugify("Hello World!.pdf") == "hello-world-pdf"


def test_text_helpers():
    assert split_sentences("Dr. Smith arrived. He sat down, e.g. on a chair. Done!") == [
        "Dr. Smith arrived.", "He sat down, e.g. on a chair.", "Done!"]
    s = shorten("word " * 60, 50)
    assert len(s) <= 51 and s.endswith("…")


def test_cleanup_removes_expired_documents(client, samples):
    from app.database import session_scope
    from app.models import Document
    from app.services.cleanup import cleanup_expired
    from tests.conftest import upload

    doc = upload(client, samples["text"]).json()
    with session_scope() as db:
        path = Path(db.get(Document, doc["id"]).stored_path)
    assert path.exists()
    removed = cleanup_expired(now=datetime.now(timezone.utc) + timedelta(days=30))
    assert removed >= 1
    assert not path.exists()
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404
