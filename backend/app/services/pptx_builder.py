"""Render slide data into an editable .pptx using python-pptx.

Everything is drawn with native, editable PowerPoint objects (text boxes, shapes,
tables, connectors), never as images.
"""
from __future__ import annotations

import math
from pathlib import Path

from lxml import etree
from pptx import Presentation as PptxPresentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from app.schemas import Slide, SlideType
from app.services.templates import Theme, get_theme

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.65)
CONTENT_TOP = Inches(1.65)
FOOTER_Y = Inches(6.95)


def _rgb(hex_: str) -> RGBColor:
    return RGBColor.from_string(hex_.upper())


def _page_label(pages: list[int]) -> str:
    if not pages:
        return ""
    pages = sorted(set(pages))
    ranges, start, prev = [], pages[0], pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        ranges.append(str(start) if start == prev else f"{start}–{prev}")
        start = prev = p
    ranges.append(str(start) if start == prev else f"{start}–{prev}")
    label = ", ".join(ranges[:4]) + ("…" if len(ranges) > 4 else "")
    return ("p. " if len(pages) == 1 else "pp. ") + label


def fit_font_size(texts: list[str], width_in: float, height_in: float, max_pt: int = 22, min_pt: int = 12,
                  spacing: float = 1.25, para_gap_pt: float = 8) -> int:
    """Largest font size such that the paragraphs fit into the box (heuristic)."""
    for size in range(max_pt, min_pt - 1, -1):
        chars_per_line = max(10, (width_in * 72) / (size * 0.52))
        lines = sum(max(1, math.ceil(len(t) / chars_per_line)) for t in texts) or 1
        height = (lines * size * spacing + len(texts) * para_gap_pt) / 72
        if height <= height_in:
            return size
    return min_pt


class DeckBuilder:
    def __init__(self, theme_id: str, doc_name: str, kind: str):
        self.theme: Theme = get_theme(theme_id)
        self.doc_name = doc_name
        self.kind = kind
        self.prs = PptxPresentation()
        self.prs.slide_width = SLIDE_W
        self.prs.slide_height = SLIDE_H
        self._blank = self.prs.slide_layouts[6]
        self.total = 0

    # ------------------------------------------------------------------ primitives
    def _bg(self, slide, color: str):
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = _rgb(color)

    def _rect(self, slide, x, y, w, h, color: str, shape=MSO_SHAPE.RECTANGLE, line: str | None = None,
              radius: float | None = None):
        shp = slide.shapes.add_shape(shape, x, y, w, h)
        shp.fill.solid()
        shp.fill.fore_color.rgb = _rgb(color)
        if line:
            shp.line.color.rgb = _rgb(line)
            shp.line.width = Pt(1)
        else:
            shp.line.fill.background()
        shp.shadow.inherit = False
        if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            shp.adjustments[0] = radius
        if shp.has_text_frame:
            shp.text_frame.text = ""
        return shp

    def _text(self, slide, x, y, w, h, text: str, size: int, color: str, bold=False, font: str | None = None,
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False, wrap=True, name: str | None = None):
        tb = slide.shapes.add_textbox(x, y, w, h)
        if name:
            tb.name = name
        tf = tb.text_frame
        tf.word_wrap = wrap
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Inches(0.05)
        tf.margin_top = tf.margin_bottom = Inches(0.03)
        p = tf.paragraphs[0]
        p.alignment = align
        self._run(p, text, size, color, bold, font or self.theme.body_font, italic)
        return tb

    def _run(self, paragraph, text, size, color, bold=False, font=None, italic=False):
        r = paragraph.add_run()
        r.text = text
        f = r.font
        f.size = Pt(size)
        f.bold = bold
        f.italic = italic
        f.name = font or self.theme.body_font
        f.color.rgb = _rgb(color)
        return r

    def _shape_text(self, shp, text, size, color, bold=False, font=None, align=PP_ALIGN.CENTER,
                    anchor=MSO_ANCHOR.MIDDLE):
        tf = shp.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Inches(0.12)
        p = tf.paragraphs[0]
        p.alignment = align
        self._run(p, text, size, color, bold, font)

    @staticmethod
    def _bulletize(paragraph, color: str, char: str = "•", indent_emu: int = 342900):
        pPr = paragraph._p.get_or_add_pPr()
        pPr.set("marL", str(indent_emu))
        pPr.set("indent", str(-int(indent_emu * 0.75)))
        for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buClr", "a:buFont"):
            for el in pPr.findall(qn(tag)):
                pPr.remove(el)
        bu_clr = etree.SubElement(pPr, qn("a:buClr"))
        clr = etree.SubElement(bu_clr, qn("a:srgbClr"))
        clr.set("val", color)
        bu_font = etree.SubElement(pPr, qn("a:buFont"))
        bu_font.set("typeface", "Arial")
        bu_char = etree.SubElement(pPr, qn("a:buChar"))
        bu_char.set("char", char)

    def _bullets(self, slide, x, y, w, h, items: list[str], max_pt=22, min_pt=13, color: str | None = None,
                 bullet_color: str | None = None):
        t = self.theme
        size = fit_font_size(items, Emu(w).inches - 0.5, Emu(h).inches, max_pt, min_pt)
        tb = slide.shapes.add_textbox(x, y, w, h)
        tb.name = "Bullets"
        tf = tb.text_frame
        tf.word_wrap = True
        for i, item in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(max(6, size * 0.6))
            p.line_spacing = 1.1
            self._run(p, item, size, color or t.text)
            self._bulletize(p, bullet_color or t.primary)
        return tb

    # ------------------------------------------------------------------ chrome
    def _header(self, slide, title: str, eyebrow: str | None = None):
        t = self.theme
        size = 32 if len(title) <= 48 else (27 if len(title) <= 62 else (23 if len(title) <= 80 else 20))
        if eyebrow:
            self._text(slide, MARGIN, Inches(0.32), Inches(9), Inches(0.3), eyebrow.upper(), 11, t.primary,
                       bold=True, font=t.body_font)
        self._text(slide, MARGIN, Inches(0.58), SLIDE_W - 2 * MARGIN, Inches(0.82), title, size, t.text,
                   bold=True, font=t.heading_font, anchor=MSO_ANCHOR.BOTTOM, name="Title")
        self._rect(slide, MARGIN, Inches(1.45), Inches(0.9), Inches(0.07), t.accent)

    def _footer(self, slide, idx: int, pages: list[int], dark: bool = False, x=None):
        t = self.theme
        color = t.muted if not dark else ("F9FAFB" if t.id == "dark_academic" else t.on_primary)
        name = self.doc_name if len(self.doc_name) <= 60 else self.doc_name[:57] + "…"
        src = _page_label(pages)
        left = f"{name}  •  Source: {src}" if src else name
        x = MARGIN if x is None else x
        self._text(slide, x, FOOTER_Y, Inches(9.5) - (x - MARGIN), Inches(0.35), left, 10, color, name="Footer")
        self._text(slide, SLIDE_W - MARGIN - Inches(1.5), FOOTER_Y, Inches(1.5), Inches(0.35),
                   f"{idx} / {self.total}", 10, color, align=PP_ALIGN.RIGHT, name="Slide Number")

    def _notes(self, slide, data: Slide):
        parts = []
        if data.notes:
            parts.append(data.notes)
        if data.visual_suggestion:
            parts.append(f"Visual suggestion: {data.visual_suggestion}")
        if data.source_pages:
            parts.append(f"Source: {_page_label(data.source_pages)} of {self.doc_name}")
        if parts:
            slide.notes_slide.notes_text_frame.text = "\n\n".join(parts)

    # ------------------------------------------------------------------ slide types
    def _title_slide(self, s, d: Slide, idx):
        t = self.theme
        self._bg(s, t.primary_dark if t.id != "minimal_white" else t.background)
        dark = t.id != "minimal_white"
        if dark:
            # decorative geometry
            self._rect(s, SLIDE_W - Inches(4.6), Inches(-1.2), Inches(6), Inches(6), t.primary, MSO_SHAPE.OVAL)
            self._rect(s, SLIDE_W - Inches(2.4), Inches(4.6), Inches(3.4), Inches(3.4), t.accent, MSO_SHAPE.OVAL)
        else:
            self._rect(s, 0, 0, Inches(0.35), SLIDE_H, t.primary)
        fg = t.on_primary if dark and t.id != "dark_academic" else (t.text if not dark else "F9FAFB")
        self._text(s, Inches(0.9), Inches(1.5), Inches(3.5), Inches(0.4), "SMARTSLIDE AI", 12,
                   t.accent if dark else t.primary, bold=True)
        tsize = 44 if len(d.title) < 45 else (36 if len(d.title) < 80 else 30)
        self._text(s, Inches(0.9), Inches(2.0), Inches(8.4), Inches(2.6), d.title, tsize, fg, bold=True,
                   font=t.heading_font, anchor=MSO_ANCHOR.BOTTOM, name="Title")
        self._rect(s, Inches(0.95), Inches(4.8), Inches(1.2), Inches(0.08), t.accent)
        if d.subtitle:
            self._text(s, Inches(0.9), Inches(5.05), Inches(8.4), Inches(1.0), d.subtitle, 18,
                       fg if dark else t.muted, name="Subtitle")
        self._text(s, Inches(0.9), FOOTER_Y - Inches(0.1), Inches(9), Inches(0.35), f"Source: {self.doc_name}", 10,
                   fg if dark else t.muted, name="Footer")

    def _section_slide(self, s, d: Slide, idx, number: int):
        t = self.theme
        self._bg(s, t.surface if t.id != "dark_academic" else t.primary_dark)
        self._rect(s, 0, 0, Inches(4.3), SLIDE_H, t.primary)
        self._text(s, Inches(0.7), Inches(2.4), Inches(3), Inches(2), f"{number:02d}", 96, t.on_primary, bold=True,
                   font=t.heading_font, anchor=MSO_ANCHOR.MIDDLE)
        self._text(s, Inches(5.0), Inches(2.1), Inches(7.6), Inches(0.4), "SECTION", 13, t.primary, bold=True)
        size = 40 if len(d.title) < 40 else 32
        self._text(s, Inches(5.0), Inches(2.5), Inches(7.6), Inches(1.9), d.title, size, t.text, bold=True,
                   font=t.heading_font, anchor=MSO_ANCHOR.MIDDLE, name="Title")
        if d.subtitle:
            self._text(s, Inches(5.0), Inches(4.5), Inches(7.6), Inches(1.4), d.subtitle, 16, t.muted, name="Subtitle")
        self._footer(s, idx, d.source_pages, x=Inches(5.0))

    def _content_slide(self, s, d: Slide, idx):
        t = self.theme
        self._bg(s, t.background)
        self._header(s, d.title)
        items = d.bullets or ([d.subtitle] if d.subtitle else [])
        short = len(items) in (2, 3) and all(len(b) <= 130 for b in items)
        if short:
            self._cards(s, items, numbered=True)
        elif items:
            self._bullets(s, MARGIN, CONTENT_TOP + Inches(0.1), SLIDE_W - 2 * MARGIN, Inches(5.0), items)
        self._footer(s, idx, d.source_pages)

    def _cards(self, s, items: list[str], numbered=True, label: str | None = None, top=None, height=None):
        t = self.theme
        n = len(items)
        top = top if top is not None else CONTENT_TOP + Inches(0.35)
        if height is None:
            longest = max(len(x) for x in items)
            height = Inches(2.4) if longest <= 60 else (Inches(3.3) if longest <= 110 else Inches(4.2))
        gap = Inches(0.35)
        width = int((SLIDE_W - 2 * MARGIN - gap * (n - 1)) / n)
        size = fit_font_size([max(items, key=len)], Emu(width).inches - 0.6, Emu(height).inches - 1.4, 22, 13,
                             para_gap_pt=0)
        for i, item in enumerate(items):
            x = MARGIN + i * (width + gap)
            self._rect(s, x, top, width, height, t.surface, MSO_SHAPE.ROUNDED_RECTANGLE, line=t.border, radius=0.08)
            badge = self._rect(s, x + Inches(0.3), top + Inches(0.3), Inches(0.6), Inches(0.6), t.primary,
                               MSO_SHAPE.OVAL)
            self._shape_text(badge, str(i + 1) if numbered else "•", 16, t.on_primary, bold=True)
            if label:
                self._text(s, x + Inches(1.05), top + Inches(0.38), width - Inches(1.3), Inches(0.45),
                           f"{label} {i + 1}", 13, t.primary, bold=True)
            self._text(s, x + Inches(0.3), top + Inches(1.15), width - Inches(0.6), height - Inches(1.35), item,
                       size, t.text)

    def _definition_slide(self, s, d: Slide, idx):
        t = self.theme
        self._bg(s, t.background)
        self._header(s, d.title, eyebrow="Key terms")
        defs = d.definitions[:4] or []
        if not defs and d.bullets:
            self._bullets(s, MARGIN, CONTENT_TOP + Inches(0.1), SLIDE_W - 2 * MARGIN, Inches(5.0), d.bullets)
            self._footer(s, idx, d.source_pages)
            return
        n = max(1, len(defs))
        gap = Inches(0.22)
        avail = Inches(5.05)
        h = min(int((avail - gap * (n - 1)) / n), Inches(1.7))
        texts = [x.definition for x in defs]
        size = fit_font_size([max(texts, key=len)], Emu(SLIDE_W - 2 * MARGIN).inches - 3.8, Emu(h).inches - 0.2,
                             20, 12, para_gap_pt=0) if texts else 16
        for i, df in enumerate(defs):
            y = CONTENT_TOP + Inches(0.1) + i * (h + gap)
            self._rect(s, MARGIN, y, SLIDE_W - 2 * MARGIN, h, t.surface, MSO_SHAPE.ROUNDED_RECTANGLE,
                       line=t.border, radius=0.12)
            self._rect(s, MARGIN, y, Inches(0.12), h, t.primary)
            self._text(s, MARGIN + Inches(0.35), y, Inches(2.9), h, df.term, 19, t.primary, bold=True,
                       font=t.heading_font, anchor=MSO_ANCHOR.MIDDLE)
            self._text(s, MARGIN + Inches(3.35), y, SLIDE_W - 2 * MARGIN - Inches(3.6), h, df.definition, size,
                       t.text, anchor=MSO_ANCHOR.MIDDLE)
        self._footer(s, idx, d.source_pages)

    def _comparison_slide(self, s, d: Slide, idx):
        t = self.theme
        self._bg(s, t.background)
        self._header(s, d.title, eyebrow="Comparison")
        c = d.comparison
        if not c:
            if d.bullets:
                self._bullets(s, MARGIN, CONTENT_TOP + Inches(0.1), SLIDE_W - 2 * MARGIN, Inches(5.0), d.bullets)
            self._footer(s, idx, d.source_pages)
            return
        rows = max(len(c.left), len(c.right), 1)
        tbl_h = Inches(0.6) + Inches(0.9) * rows
        gt = s.shapes.add_table(rows + 1, 2, MARGIN, CONTENT_TOP + Inches(0.2), SLIDE_W - 2 * MARGIN,
                                min(tbl_h, Inches(5.0)))
        tbl = gt.table
        tbl.first_row = True
        longest = max(c.left + c.right, key=len, default="")
        size = fit_font_size([longest], 5.6, max(0.45, 4.4 / rows - 0.15), 17, 11, para_gap_pt=0)
        for col, head in enumerate((c.left_title, c.right_title)):
            cell = tbl.cell(0, col)
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(t.primary if col == 0 else t.primary_dark if t.id != "dark_academic" else "374151")
            cell.text_frame.text = ""
            self._run(cell.text_frame.paragraphs[0], head, 18, t.on_primary if col == 0 or t.id != "dark_academic" else t.text, bold=True,
                      font=t.heading_font)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        for r in range(rows):
            for col, items in enumerate((c.left, c.right)):
                cell = tbl.cell(r + 1, col)
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(t.surface if r % 2 == 0 else t.background)
                cell.text_frame.text = ""
                cell.text_frame.word_wrap = True
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                self._run(cell.text_frame.paragraphs[0], items[r] if r < len(items) else "", size, t.text)
        self._footer(s, idx, d.source_pages)

    def _process_slide(self, s, d: Slide, idx):
        t = self.theme
        self._bg(s, t.background)
        self._header(s, d.title, eyebrow="Process")
        steps = d.steps[:6] or d.bullets[:6]
        n = len(steps)
        if n == 0:
            self._footer(s, idx, d.source_pages)
            return
        per_row = n if n <= 4 else math.ceil(n / 2)
        rows = math.ceil(n / per_row)
        arrow_w = Inches(0.45)
        gap = Inches(0.12)
        box_w = int((SLIDE_W - 2 * MARGIN - (per_row - 1) * (arrow_w + 2 * gap)) / per_row)
        box_h = Inches(2.3) if rows == 2 else Inches(3.4)
        size = fit_font_size([max(steps, key=len)], Emu(box_w).inches - 0.45, Emu(box_h).inches - 1.1, 18, 11,
                             para_gap_pt=0)
        for i, step in enumerate(steps):
            r, cpos = divmod(i, per_row)
            y = CONTENT_TOP + Inches(0.35) + r * (box_h + Inches(0.4))
            x = MARGIN + cpos * (box_w + arrow_w + 2 * gap)
            self._rect(s, x, y, box_w, box_h, t.surface, MSO_SHAPE.ROUNDED_RECTANGLE, line=t.border, radius=0.1)
            badge = self._rect(s, x + Inches(0.25), y + Inches(0.25), Inches(0.55), Inches(0.55), t.primary,
                               MSO_SHAPE.OVAL)
            self._shape_text(badge, str(i + 1), 15, t.on_primary, bold=True)
            self._text(s, x + Inches(0.2), y + Inches(0.95), box_w - Inches(0.4), box_h - Inches(1.05), step, size,
                       t.text)
            if cpos < per_row - 1 and i < n - 1:
                arr = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + box_w + gap, y + box_h / 2 - Inches(0.22),
                                         arrow_w, Inches(0.44))
                arr.fill.solid()
                arr.fill.fore_color.rgb = _rgb(t.accent)
                arr.line.fill.background()
        self._footer(s, idx, d.source_pages)

    def _example_slide(self, s, d: Slide, idx):
        t = self.theme
        self._bg(s, t.background)
        self._header(s, d.title, eyebrow="Examples")
        items = d.bullets[:4]
        if 1 <= len(items) <= 3 and all(len(x) <= 220 for x in items):
            self._cards(s, items, numbered=True, label="Example")
        elif items:
            self._bullets(s, MARGIN, CONTENT_TOP + Inches(0.1), SLIDE_W - 2 * MARGIN, Inches(5.0), items)
        self._footer(s, idx, d.source_pages)

    def _takeaways_slide(self, s, d: Slide, idx):
        t = self.theme
        self._bg(s, t.background)
        self._header(s, d.title, eyebrow="Remember")
        items = d.bullets[:6]
        n = len(items)
        if n == 0:
            self._footer(s, idx, d.source_pages)
            return
        cols = 1 if n <= 2 else 2
        rows = math.ceil(n / cols)
        gap = Inches(0.25)
        w = int((SLIDE_W - 2 * MARGIN - gap * (cols - 1)) / cols)
        h = int((Inches(5.05) - gap * (rows - 1)) / rows)
        h = min(h, Inches(1.9))
        size = fit_font_size([max(items, key=len)], Emu(w).inches - 1.5, Emu(h).inches - 0.25, 20, 12,
                             para_gap_pt=0)
        for i, item in enumerate(items):
            r, c = divmod(i, cols)
            x = MARGIN + c * (w + gap)
            y = CONTENT_TOP + Inches(0.1) + r * (h + gap)
            self._rect(s, x, y, w, h, t.surface, MSO_SHAPE.ROUNDED_RECTANGLE, line=t.border, radius=0.12)
            self._text(s, x + Inches(0.2), y, Inches(0.9), h, f"{i + 1:02d}", 26, t.accent, bold=True,
                       font=t.heading_font, anchor=MSO_ANCHOR.MIDDLE)
            self._text(s, x + Inches(1.15), y, w - Inches(1.35), h, item, size, t.text, anchor=MSO_ANCHOR.MIDDLE)
        self._footer(s, idx, d.source_pages)

    def _conclusion_slide(self, s, d: Slide, idx):
        t = self.theme
        dark = t.id != "minimal_white"
        self._bg(s, t.primary_dark if dark else t.background)
        fg = "F9FAFB" if dark else t.text
        if dark:
            self._rect(s, SLIDE_W - Inches(3.2), Inches(4.3), Inches(4.6), Inches(4.6), t.primary, MSO_SHAPE.OVAL)
        else:
            self._rect(s, 0, 0, Inches(0.35), SLIDE_H, t.primary)
        self._text(s, Inches(0.9), Inches(0.6), Inches(6), Inches(0.4), "CONCLUSION", 12, t.accent, bold=True)
        self._text(s, Inches(0.9), Inches(0.95), Inches(11.5), Inches(0.9), d.title, 36, fg, bold=True,
                   font=t.heading_font, name="Title")
        if d.bullets:
            self._bullets(s, Inches(0.9), Inches(2.1), Inches(11.4), Inches(3.6), d.bullets, max_pt=22, color=fg,
                          bullet_color=t.accent)
        self._text(s, Inches(0.9), Inches(5.9), Inches(11.5), Inches(0.6), "Thank you • Questions?", 20, t.accent,
                   bold=True, font=t.heading_font)
        self._footer(s, idx, d.source_pages, dark=dark)

    # ------------------------------------------------------------------ public
    def build(self, slides: list[Slide], output: Path) -> Path:
        self.total = len(slides)
        section_no = 0
        for i, d in enumerate(slides, start=1):
            s = self.prs.slides.add_slide(self._blank)
            if d.type == SlideType.title:
                self._title_slide(s, d, i)
            elif d.type == SlideType.section:
                section_no += 1
                self._section_slide(s, d, i, section_no)
            elif d.type == SlideType.definition:
                self._definition_slide(s, d, i)
            elif d.type == SlideType.comparison:
                self._comparison_slide(s, d, i)
            elif d.type == SlideType.process:
                self._process_slide(s, d, i)
            elif d.type == SlideType.example:
                self._example_slide(s, d, i)
            elif d.type == SlideType.takeaways:
                self._takeaways_slide(s, d, i)
            elif d.type == SlideType.conclusion:
                self._conclusion_slide(s, d, i)
            else:
                self._content_slide(s, d, i)
            self._notes(s, d)
        self.prs.core_properties.title = slides[0].title if slides else "Presentation"
        self.prs.core_properties.author = "SmartSlide AI"
        self.prs.core_properties.subject = f"{self.kind.title()} presentation of {self.doc_name}"
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(".tmp.pptx")
        self.prs.save(str(tmp))
        tmp.replace(output)
        return output


def render_presentation(slides: list[Slide], theme_id: str, doc_name: str, kind: str, output: Path) -> Path:
    return DeckBuilder(theme_id, doc_name, kind).build(slides, output)
