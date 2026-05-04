"""Lettura di file di vari formati e scansione cartelle di input."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4a", ".mp3", ".wav", ".flac"}
TEXT_EXTS = {".txt", ".md", ".markdown"}
PDF_EXTS = {".pdf"}
HTML_EXTS = {".html", ".htm"}

SUPPORTED_EXTS = VIDEO_EXTS | TEXT_EXTS | PDF_EXTS | HTML_EXTS


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf non installato. pip install pypdf") from e

    reader = PdfReader(str(path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        try:
            t = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            t = ""
        if t.strip():
            parts.append(f"[Pagina {i}]\n{t.strip()}")
    return "\n\n".join(parts)


def read_html(path: Path) -> str:
    """Estrae il contenuto principale da un HTML.

    Usa trafilatura se disponibile (riconosce automaticamente il contenuto
    principale ignorando navigation/footer/sidebar). Fallback su BeautifulSoup.
    """
    raw = path.read_text(encoding="utf-8", errors="ignore")

    # Strada 1: trafilatura (molto migliore per pagine web)
    try:
        import trafilatura
        text = trafilatura.extract(
            raw,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,
        )
        if text and len(text.strip()) > 100:
            return text.strip()
    except ImportError:
        pass

    # Strada 2: fallback con BeautifulSoup, ma più aggressivo
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise RuntimeError(
            "Per i file HTML installa: pip install trafilatura beautifulsoup4"
        ) from e

    soup = BeautifulSoup(raw, "html.parser")

    # Rimuovi tag non testuali
    for tag in soup([
        "script", "style", "nav", "footer", "header", "aside", "noscript",
        "form", "button", "iframe", "svg", "img", "video", "audio",
    ]):
        tag.decompose()

    # Rimuovi elementi con classi/id "navigationali" comuni
    for el in soup.find_all(class_=re.compile(
        r"(nav|menu|sidebar|footer|header|breadcrumb|cookie|banner|advertisement)",
        re.IGNORECASE,
    )):
        el.decompose()

    # Prova a trovare il main content (Coursera usa <main>, <article>, role=main)
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.find(class_=re.compile(r"(content|main|article|body)", re.IGNORECASE))
        or soup
    )

    text = main.get_text(separator="\n")
    # Pulizia spazi
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTS


def is_media(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


@dataclass
class InputFile:
    path: Path
    rel_path: Path
    kind: str


def scan_inputs(root: Path) -> list[InputFile]:
    if not root.exists():
        return []
    items: list[InputFile] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            continue
        if ext in TEXT_EXTS:
            kind = "text"
        elif ext in PDF_EXTS:
            kind = "pdf"
        elif ext in HTML_EXTS:
            kind = "html"
        else:
            kind = "media"
        items.append(InputFile(path=p, rel_path=p.relative_to(root), kind=kind))
    return items


def group_by_folder(files: list[InputFile]) -> dict[Path, list[InputFile]]:
    out: dict[Path, list[InputFile]] = {}
    for f in files:
        parent = f.rel_path.parent
        out.setdefault(parent, []).append(f)
    return out


def list_folders(files: list[InputFile]) -> list[Path]:
    return sorted({f.rel_path.parent for f in files})


def find_companion_text(video_path: Path) -> Path | None:
    """Cerca un file .txt o .md con lo stesso nome base del video.

    Esempio: video '01_intro.mp4' → cerca '01_intro.txt' nella stessa cartella.
    Restituisce None se non trovato.
    """
    stem = video_path.stem
    parent = video_path.parent
    for ext in (".txt", ".md", ".markdown"):
        candidate = parent / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None
