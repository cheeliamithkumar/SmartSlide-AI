"""Presentation themes (colors + fonts) shared by the PPTX builder and the frontend preview."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    description: str
    background: str
    surface: str        # card background
    primary: str
    primary_dark: str
    accent: str
    text: str
    muted: str
    on_primary: str     # text on primary-colored backgrounds
    heading_font: str
    body_font: str
    border: str

    def colors(self) -> dict[str, str]:
        d = asdict(self)
        return {k: v for k, v in d.items() if k not in {"id", "name", "description", "heading_font", "body_font"}}


THEMES: dict[str, Theme] = {
    "modern_education": Theme(
        id="modern_education", name="Modern Education",
        description="Friendly indigo and amber palette with rounded cards. Great for classrooms.",
        background="FFFFFF", surface="EEF2FF", primary="4F46E5", primary_dark="3730A3", accent="F59E0B",
        text="1E293B", muted="64748B", on_primary="FFFFFF", heading_font="Trebuchet MS", body_font="Calibri",
        border="C7D2FE",
    ),
    "minimal_white": Theme(
        id="minimal_white", name="Minimal White",
        description="Clean black-on-white layout with a single teal accent and generous whitespace.",
        background="FFFFFF", surface="F5F5F4", primary="0F766E", primary_dark="134E4A", accent="0F766E",
        text="1C1917", muted="78716C", on_primary="FFFFFF", heading_font="Arial", body_font="Arial",
        border="E7E5E4",
    ),
    "professional_blue": Theme(
        id="professional_blue", name="Professional Blue",
        description="Corporate navy and sky blue design suited to lectures and seminars.",
        background="F8FAFC", surface="E0F2FE", primary="1D4ED8", primary_dark="1E3A8A", accent="0EA5E9",
        text="0F172A", muted="475569", on_primary="FFFFFF", heading_font="Segoe UI", body_font="Segoe UI",
        border="BAE6FD",
    ),
    "dark_academic": Theme(
        id="dark_academic", name="Dark Academic",
        description="Elegant dark slate background with gold accents and serif headings.",
        background="111827", surface="1F2937", primary="D4A84B", primary_dark="0B1120", accent="D4A84B",
        text="F3F4F6", muted="9CA3AF", on_primary="111827", heading_font="Georgia", body_font="Calibri",
        border="374151",
    ),
}

DEFAULT_THEME = "modern_education"


def get_theme(theme_id: str | None) -> Theme:
    return THEMES.get(theme_id or DEFAULT_THEME, THEMES[DEFAULT_THEME])


def list_themes() -> list[dict]:
    return [
        {"id": t.id, "name": t.name, "description": t.description, "colors": t.colors(), "font": t.heading_font}
        for t in THEMES.values()
    ]
