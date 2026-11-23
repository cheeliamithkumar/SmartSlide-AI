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
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from app.schemas import Diagram, Slide, SlideType
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
        src = _page_label(pages)
        left = f"Source: {src}" if src else ""
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
            parts.append(f"Source: {_page_label(data.source_pages)} of the original document")
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
        tsize = 44 if len(d.title) < 45 else (36 if len(d.title) < 80 else 30)
        self._text(s, Inches(0.9), Inches(2.0), Inches(8.4), Inches(2.6), d.title, tsize, fg, bold=True,
                   font=t.heading_font, anchor=MSO_ANCHOR.BOTTOM, name="Title")
        self._rect(s, Inches(0.95), Inches(4.8), Inches(1.2), Inches(0.08), t.accent)
        if d.subtitle:
            self._text(s, Inches(0.9), Inches(5.05), Inches(8.4), Inches(1.0), d.subtitle, 18,
                       fg if dark else t.muted, name="Subtitle")

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
        if d.diagram and d.diagram.kind == "mindmap" and d.diagram.nodes:
            # bullets on the left, editable concept map on the right
            if items:
                self._bullets(s, MARGIN, CONTENT_TOP + Inches(0.1), Inches(6.6), Inches(5.0), items, max_pt=20)
            self._draw_mindmap(s, d.diagram, Inches(7.55), CONTENT_TOP, Inches(5.15), Inches(5.1), compact=True)
            self._footer(s, idx, d.source_pages)
            return
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
        steps = d.steps[:6] or d.bullets[:6]
        is_cycle = bool(d.diagram and d.diagram.kind == "cycle")
        self._header(s, d.title, eyebrow="Cycle" if is_cycle else "Process")
        n = len(steps)
        if n == 0:
            self._footer(s, idx, d.source_pages)
            return
        if is_cycle and n >= 3:
            self._draw_cycle(s, steps, MARGIN, CONTENT_TOP, SLIDE_W - 2 * MARGIN, Inches(5.15))
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

    # ------------------------------------------------------------------ diagrams
    def _line(self, s, x1, y1, x2, y2, color: str, width_pt: float = 1.75, arrow: bool = False):
        ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, int(x1), int(y1), int(x2), int(y2))
        ln.line.color.rgb = _rgb(color)
        ln.line.width = Pt(width_pt)
        if arrow:
            ln_el = ln.line._get_or_add_ln()
            tail = etree.SubElement(ln_el, qn("a:tailEnd"))
            tail.set("type", "triangle")
            tail.set("w", "med")
            tail.set("h", "med")
        return ln

    def _node(self, s, x, y, w, h, text, size, fill, fg, line=None, bold=False, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
              font=None):
        shp = self._rect(s, int(x), int(y), int(w), int(h), fill, shape, line=line,
                         radius=0.25 if shape == MSO_SHAPE.ROUNDED_RECTANGLE else None)
        self._shape_text(shp, text, size, fg, bold=bold, font=font)
        tf = shp.text_frame
        tf.margin_left = tf.margin_right = Inches(0.08)
        tf.margin_top = tf.margin_bottom = Inches(0.04)
        return shp

    def _label_size(self, text: str, box_w_in: float, max_pt: int = 16, min_pt: int = 10, lines: int = 2,
                    heading: bool = False) -> int:
        longest = max((len(w) for w in text.split()), default=1)
        font = self.theme.heading_font if heading else self.theme.body_font
        factor = 0.7 if font in ("Georgia", "Trebuchet MS", "Segoe UI", "Arial") else 0.62
        for size in range(max_pt, min_pt - 1, -1):
            char_w = size * factor / 72  # generous average glyph width (inches) for bold labels
            cpl = max(4, box_w_in / char_w)
            if longest <= cpl and math.ceil(len(text) * 1.1 / cpl) <= lines:
                return size
        return min_pt

    def _draw_mindmap(self, s, diag: Diagram, x, y, w, h, compact: bool = False):
        """Centre concept with related nodes on an ellipse, joined by connectors."""
        t = self.theme
        nodes = diag.nodes[:6]
        n = max(1, len(nodes))
        if compact:
            self._draw_concept_tree(s, diag, x, y, w, h)
            return
        cx, cy = x + w / 2, y + h / 2
        cw, ch = (w * 0.38, h * 0.22) if compact else (w * 0.27, h * 0.22)
        nw, nh = (w * 0.36, h * 0.15) if compact else (w * 0.23, h * 0.17)
        rx, ry = (w - nw) / 2, (h - nh) / 2
        pos = []
        for i in range(n):
            ang = -math.pi / 2 + 2 * math.pi * i / n
            pos.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
        for px, py in pos:  # connectors first so they sit behind the shapes
            self._line(s, cx, cy, px, py, t.border if t.id != "dark_academic" else t.muted, 2.0)
        center = diag.center or "Topic"
        csize = self._label_size(center, Emu(int(cw)).inches * 0.72, 20, 11, 2, heading=True)
        self._node(s, cx - cw / 2, cy - ch / 2, cw, ch, center, csize, t.primary, t.on_primary, bold=True,
                   shape=MSO_SHAPE.OVAL, font=t.heading_font)
        for node, (px, py) in zip(nodes, pos):
            label = node.label if not node.detail or compact else f"{node.label}"
            size = self._label_size(label, Emu(int(nw)).inches - 0.2, 15 if not compact else 13, 9, 2)
            self._node(s, px - nw / 2, py - nh / 2, nw, nh, label, size, t.surface, t.text, line=t.primary, bold=True)

    def _draw_concept_tree(self, s, diag: Diagram, x, y, w, h):
        """Compact concept map for split layouts: topic on top, key terms in two columns below."""
        t = self.theme
        nodes = diag.nodes[:6]
        rows = math.ceil(len(nodes) / 2)
        top_h = Inches(1.0)
        cw = w * 0.78
        center = diag.center or "Topic"
        csize = self._label_size(center, Emu(int(cw)).inches - 0.3, 18, 11, 2, heading=True)
        self._node(s, x + (w - cw) / 2, y + Inches(0.1), cw, top_h, center, csize, t.primary, t.on_primary, bold=True,
                   font=t.heading_font)
        bus_y = y + Inches(0.1) + top_h + Inches(0.3)
        line_c = t.border if t.id != "dark_academic" else t.muted
        self._line(s, x + w / 2, y + Inches(0.1) + top_h, x + w / 2, bus_y, line_c, 2.0)
        gap = Inches(0.25)
        nw = (w - gap) / 2
        avail = y + h - bus_y - Inches(0.25)
        nh = min(Inches(0.95), (avail - Inches(0.22) * (rows - 1)) / max(rows, 1))
        col_x = [x + nw / 2, x + nw + gap + nw / 2]
        self._line(s, col_x[0], bus_y, col_x[1] if len(nodes) > 1 else col_x[0], bus_y, line_c, 2.0)
        for i, node in enumerate(nodes):
            r, c = divmod(i, 2)
            ny = bus_y + Inches(0.25) + r * (nh + Inches(0.22))
            if r == 0:
                self._line(s, col_x[c], bus_y, col_x[c], ny, line_c, 2.0)
            else:
                self._line(s, col_x[c], ny - Inches(0.22), col_x[c], ny, line_c, 2.0)
            size = self._label_size(node.label, Emu(int(nw)).inches - 0.3, 15, 10, 2)
            self._node(s, col_x[c] - nw / 2, ny, nw, nh, node.label, size, t.surface, t.text, line=t.primary, bold=True)

    def _draw_timeline(self, s, diag: Diagram, x, y, w, h):
        """Numbered roadmap: label cards above a line, short descriptions below."""
        t = self.theme
        nodes = diag.nodes[:7]
        n = max(1, len(nodes))
        slot = w / n
        y = y + Inches(0.35)
        h = h - Inches(0.35)
        line_y = y + h * 0.42
        self._rect(s, int(x + slot / 2), int(line_y - Inches(0.03)), int(slot * (n - 1)) or 1, int(Inches(0.06)),
                   t.accent)
        r = Inches(0.27)
        card_w = slot - Inches(0.18)
        for i, node in enumerate(nodes):
            cx = x + slot * i + slot / 2
            size = self._label_size(node.label, Emu(int(card_w)).inches - 0.25, 15, 9, 3, heading=True)
            self._node(s, cx - card_w / 2, y + Inches(0.15), card_w, line_y - y - Inches(0.65), node.label, size,
                       t.surface, t.text, line=t.border, bold=True, font=t.heading_font)
            self._line(s, cx, line_y - Inches(0.5), cx, line_y - r, t.border, 1.25)
            badge = self._rect(s, int(cx - r), int(line_y - r), int(2 * r), int(2 * r), t.primary, MSO_SHAPE.OVAL)
            self._shape_text(badge, str(i + 1), 13, t.on_primary, bold=True)
            if node.detail:
                dsize = self._label_size(node.detail, Emu(int(card_w)).inches - 0.1, 13, 9, 6)
                self._text(s, int(cx - card_w / 2), int(line_y + r + Inches(0.15)), int(card_w),
                           int(y + h - line_y - r - Inches(0.2)), node.detail, dsize, t.muted, align=PP_ALIGN.CENTER)

    def _draw_cycle(self, s, steps: list[str], x, y, w, h):
        """Steps arranged in a loop with arrows from each step to the next (last returns to first)."""
        t = self.theme
        n = len(steps)
        cx, cy = x + w / 2, y + h / 2
        nw, nh = Inches(3.5), Inches(1.3)
        rx, ry = (w - nw) / 2 * 0.86, (h - nh) / 2
        pos = [(cx + rx * math.cos(-math.pi / 2 + 2 * math.pi * i / n),
                cy + ry * math.sin(-math.pi / 2 + 2 * math.pi * i / n)) for i in range(n)]
        for i in range(n):  # arrows behind nodes, trimmed so the heads stay visible
            (x1, y1), (x2, y2) = pos[i], pos[(i + 1) % n]
            dx, dy = x2 - x1, y2 - y1
            dist = math.hypot(dx, dy) or 1
            ux, uy = dx / dist, dy / dist
            tx = abs(nw / 2 / ux) if ux else float("inf")
            ty = abs(nh / 2 / uy) if uy else float("inf")
            trim = min(tx, ty) + Inches(0.08)
            if dist > 2 * trim:
                self._line(s, x1 + ux * trim, y1 + uy * trim, x2 - ux * trim, y2 - uy * trim, t.accent, 2.5, arrow=True)
        hub = self._rect(s, int(cx - Inches(0.95)), int(cy - Inches(0.5)), int(Inches(1.9)), int(Inches(1.0)),
                         t.surface, MSO_SHAPE.OVAL, line=t.border)
        self._shape_text(hub, "↻ Repeats", 13, t.primary, bold=True)
        size = min(self._label_size(st, Emu(int(nw)).inches - 0.8, 15, 10, 4) for st in steps)
        for i, (step, (px, py)) in enumerate(zip(steps, pos)):
            card = self._rect(s, int(px - nw / 2), int(py - nh / 2), int(nw), int(nh), t.surface,
                              MSO_SHAPE.ROUNDED_RECTANGLE, line=t.primary, radius=0.2)
            badge = self._rect(s, int(px - nw / 2 + Inches(0.12)), int(py - Inches(0.22)), int(Inches(0.44)),
                               int(Inches(0.44)), t.primary, MSO_SHAPE.OVAL)
            self._shape_text(badge, str(i + 1), 12, t.on_primary, bold=True)
            self._text(s, int(px - nw / 2 + Inches(0.62)), int(py - nh / 2), int(nw - Inches(0.7)), int(nh), step,
                       size, t.text, anchor=MSO_ANCHOR.MIDDLE)
            card.name = f"Step {i + 1}"

    def _diagram_slide(self, s, d: Slide, idx):
        t = self.theme
        self._bg(s, t.background)
        diag = d.diagram or Diagram(kind="mindmap", center=d.title, nodes=[])
        eyebrow = {"timeline": "Roadmap", "mindmap": "Concept map", "cycle": "Cycle", "flow": "Process"}[diag.kind]
        self._header(s, d.title, eyebrow=eyebrow)
        area = (MARGIN, CONTENT_TOP + Inches(0.05), SLIDE_W - 2 * MARGIN, Inches(5.1))
        if diag.kind == "timeline" and diag.nodes:
            self._draw_timeline(s, diag, *area)
        elif diag.kind == "mindmap" and diag.nodes:
            self._draw_mindmap(s, diag, *area)
        elif diag.kind == "cycle" and len(diag.nodes) >= 3:
            self._draw_cycle(s, [nd.label for nd in diag.nodes], *area)
        elif d.bullets:
            self._bullets(s, MARGIN, CONTENT_TOP + Inches(0.1), SLIDE_W - 2 * MARGIN, Inches(5.0), d.bullets)
        self._footer(s, idx, d.source_pages)

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
            elif d.type == SlideType.diagram:
                self._diagram_slide(s, d, i)
            else:
                self._content_slide(s, d, i)
            self._notes(s, d)
        self.prs.core_properties.title = slides[0].title if slides else "Presentation"
        self.prs.core_properties.author = ""
        self.prs.core_properties.subject = f"{self.kind.title()} presentation"
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(".tmp.pptx")
        self.prs.save(str(tmp))
        tmp.replace(output)
        return output


def render_presentation(slides: list[Slide], theme_id: str, doc_name: str, kind: str, output: Path) -> Path:
    return DeckBuilder(theme_id, doc_name, kind).build(slides, output)
