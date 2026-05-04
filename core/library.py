"""Lettura della biblioteca di output salvati su disco + ricerca full-text."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


UNSAFE = re.compile(r"[^\w\- ]+", re.UNICODE)


def sanitize(name: str) -> str:
    name = name.strip()
    if not name:
        return "_"
    name = UNSAFE.sub("_", name)
    name = re.sub(r"\s+", "_", name)
    return name[:120]


def build_path(
    root: Path, corso: str, modulo: str, sottomodulo: str, item: str | None = None
) -> Path:
    parts = [
        sanitize(corso or "_senza_corso"),
        sanitize(modulo or "_senza_modulo"),
        sanitize(sottomodulo or "_senza_sottomodulo"),
    ]
    p = root.joinpath(*parts)
    if item:
        p = p / sanitize(item)
    return p


def _load_result(dir_path: Path) -> dict:
    r: dict = {}
    tr = dir_path / "transcript.txt"
    if tr.exists():
        r["_text"] = tr.read_text(encoding="utf-8", errors="ignore")
    summ = dir_path / "summary.md"
    if summ.exists():
        r["summary"] = summ.read_text(encoding="utf-8", errors="ignore")
    fc = dir_path / "flashcards.json"
    if fc.exists():
        try:
            r["flashcards"] = json.loads(fc.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            r["flashcards"] = []
    gl = dir_path / "glossary.md"
    if gl.exists():
        r["glossary"] = gl.read_text(encoding="utf-8", errors="ignore")
    q = dir_path / "questions.md"
    if q.exists():
        r["questions"] = q.read_text(encoding="utf-8", errors="ignore")
    mm = dir_path / "mindmap.md"
    if mm.exists():
        r["mindmap"] = mm.read_text(encoding="utf-8", errors="ignore")
    mcq = dir_path / "mcq.json"
    if mcq.exists():
        try:
            r["mcq"] = json.loads(mcq.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            r["mcq"] = []
    return r


def list_corsi(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])


def list_moduli(root: Path, corso: str) -> list[str]:
    p = root / corso
    if not p.exists():
        return []
    return sorted([c.name for c in p.iterdir() if c.is_dir()])


def list_sottomoduli(root: Path, corso: str, modulo: str) -> list[str]:
    p = root / corso / modulo
    if not p.exists():
        return []
    return sorted([c.name for c in p.iterdir() if c.is_dir()])


def list_items(root: Path, corso: str, modulo: str, sottomodulo: str) -> list[str]:
    p = root / corso / modulo / sottomodulo
    if not p.exists():
        return []
    items: list[str] = []
    if (p / "summary.md").exists() or (p / "flashcards.json").exists():
        items.append("(contenuto diretto)")
    for child in sorted(p.iterdir()):
        if child.is_dir() and child.name != "sources":
            items.append(child.name)
    return items


def load_item(
    root: Path, corso: str, modulo: str, sottomodulo: str, item: str
) -> dict:
    base = root / corso / modulo / sottomodulo
    if item == "(contenuto diretto)":
        return _load_result(base)
    return _load_result(base / item)


def item_already_processed(
    root: Path, corso: str, modulo: str, sottomodulo: str, item_stem: str
) -> bool:
    """Controlla se un elemento è già stato elaborato (ha almeno summary.md)."""
    p = build_path(root, corso, modulo, sottomodulo, item_stem)
    return (p / "summary.md").exists()


# ---------- Full-text search ----------

_SEARCHABLE_FILES = [
    "summary.md",
    "glossary.md",
    "questions.md",
    "transcript.txt",
    "mindmap.md",
]


def iter_all_items(root: Path):
    """Genera tuple (corso, modulo, sottomodulo, item, dir_path) per ogni elemento."""
    if not root.exists():
        return
    for corso_dir in sorted(root.iterdir()):
        if not corso_dir.is_dir():
            continue
        for modulo_dir in sorted(corso_dir.iterdir()):
            if not modulo_dir.is_dir():
                continue
            for sub_dir in sorted(modulo_dir.iterdir()):
                if not sub_dir.is_dir():
                    continue
                # Contenuto diretto del sottomodulo
                if (sub_dir / "summary.md").exists():
                    yield (corso_dir.name, modulo_dir.name, sub_dir.name, "(contenuto diretto)", sub_dir)
                for item_dir in sorted(sub_dir.iterdir()):
                    if item_dir.is_dir() and item_dir.name != "sources":
                        yield (corso_dir.name, modulo_dir.name, sub_dir.name, item_dir.name, item_dir)


def search_library(root: Path, query: str, max_results: int = 30) -> list[dict[str, Any]]:
    """Ricerca full-text case-insensitive. Ritorna snippet per ogni hit."""
    if not query.strip():
        return []
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results: list[dict[str, Any]] = []

    for corso, modulo, sub, item, dir_path in iter_all_items(root):
        for fname in _SEARCHABLE_FILES:
            fpath = dir_path / fname
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            hits = list(pattern.finditer(content))
            if not hits:
                continue
            # Crea uno snippet dal primo match
            first = hits[0]
            start = max(0, first.start() - 80)
            end = min(len(content), first.end() + 120)
            snippet = content[start:end].strip()
            # Evidenzia con markdown bold
            snippet_hl = pattern.sub(lambda m: f"**{m.group(0)}**", snippet)
            results.append({
                "corso": corso,
                "modulo": modulo,
                "sottomodulo": sub,
                "item": item,
                "file": fname,
                "hits": len(hits),
                "snippet": ("… " if start > 0 else "") + snippet_hl + (" …" if end < len(content) else ""),
                "path": str(fpath),
            })
            if len(results) >= max_results:
                return results
    return results


# ---------- Cross-reference ----------
def dashboard_stats(root: Path) -> dict[str, Any]:
    """Statistiche rapide per homepage."""
    corsi = list_corsi(root)
    total_items = 0
    total_modules = 0
    total_submodules = 0
    recent_items: list[tuple[float, str, str, str, str]] = []

    for corso in corsi:
        moduli = list_moduli(root, corso)
        total_modules += len(moduli)
        for modulo in moduli:
            subs = list_sottomoduli(root, corso, modulo)
            total_submodules += len(subs)
            for sub in subs:
                items = list_items(root, corso, modulo, sub)
                total_items += len(items)
                for item in items:
                    dir_path = root / corso / modulo / sub
                    if item != "(contenuto diretto)":
                        dir_path = dir_path / item
                    summ = dir_path / "summary.md"
                    if summ.exists():
                        recent_items.append((
                            summ.stat().st_mtime, corso, modulo, sub, item,
                        ))

    recent_items.sort(key=lambda x: -x[0])
    return {
        "n_corsi": len(corsi),
        "n_moduli": total_modules,
        "n_sottomoduli": total_submodules,
        "n_items": total_items,
        "recent": recent_items[:6],
        "corsi": corsi,
    }

def extract_glossary_terms(glossary_md: str) -> list[str]:
    """Estrae i termini in grassetto dal glossario (formato `- **Termine**: def`)."""
    return re.findall(r"-\s*\*\*(.+?)\*\*", glossary_md)


def build_cross_references(root: Path, corso: str) -> dict[str, list[dict[str, str]]]:
    """Per ogni termine del glossario, trova tutti gli elementi del corso che lo menzionano.

    Ritorna: {termine: [{"modulo": ..., "sottomodulo": ..., "item": ...}, ...]}
    """
    refs: dict[str, list[dict[str, str]]] = {}
    # Raccogli tutti i termini da tutti i glossari del corso
    all_terms: set[str] = set()
    items_content: list[tuple[dict[str, str], str]] = []

    for c, m, s, it, dir_path in iter_all_items(root):
        if c != corso:
            continue
        gloss = dir_path / "glossary.md"
        if gloss.exists():
            terms = extract_glossary_terms(gloss.read_text(encoding="utf-8", errors="ignore"))
            all_terms.update(terms)
        # Prendi sommario e testo per cercarci
        searchable = ""
        for fname in ("summary.md", "transcript.txt", "questions.md"):
            f = dir_path / fname
            if f.exists():
                searchable += "\n" + f.read_text(encoding="utf-8", errors="ignore")
        items_content.append(({"modulo": m, "sottomodulo": s, "item": it}, searchable))

    for term in all_terms:
        if len(term) < 3:
            continue
        # Pattern word-boundary case-insensitive
        pat = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        locations = []
        for meta, content in items_content:
            if pat.search(content):
                locations.append(meta)
        if len(locations) >= 2:  # interessante solo se compare in >= 2 posti
            refs[term] = locations
    return refs
