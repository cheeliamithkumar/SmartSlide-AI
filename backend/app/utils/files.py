"""File handling helpers: safe filenames, path containment, deletion."""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_filename(name: str | None, default: str = "document.pdf", max_len: int = 120) -> str:
    """Return a display-safe filename: strips directories, control chars and odd symbols.

    The returned name is only used for display / download names. Files on disk are
    always stored under random UUID names, never under user-provided names.
    """
    if not name:
        return default
    name = name.replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = _SAFE_CHARS.sub("_", name).strip(" ._")
    name = re.sub(r"_+", "_", name)
    if not name:
        return default
    if len(name) > max_len:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            name = stem[: max_len - len(ext) - 1] + "." + ext
        else:
            name = name[:max_len]
    return name


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return (text[:max_len].rstrip("-")) or "presentation"


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_unlink(path: str | Path | None, root: Path) -> bool:
    """Delete a file only if it lives inside ``root``."""
    if not path:
        return False
    p = Path(path)
    if not is_within(p, root):
        logger.warning("Refusing to delete file outside storage root: %s", p)
        return False
    try:
        p.unlink(missing_ok=True)
        return True
    except OSError as exc:  # pragma: no cover - OS specific
        logger.warning("Could not delete %s: %s", p, exc)
        return False
