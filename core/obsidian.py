"""Export della biblioteca in un vault Obsidian con wikilinks."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .library import extract_glossary_terms, iter_all_items


def _note_name(item_name: str) -> str:
    """Nome nota Obsidian (senza estensione .md)."""
    # Obsidian accetta quasi tutto tranne alcuni caratteri
    s = re.sub(r"[\\/:*?\"<>|#\[\]]", "", item_name)
    return s.strip() or "_"


def _link(name: str) -> str:
    return f"[[{_note_name(name)}]]"


def export_vault(source_root: Path, dest_root: Path, corso_filter: str | None = None) -> dict:
    """Costruisce un vault Obsidian in `dest_root` a partire dagli output.

    Struttura vault:
      <corso>/
        _MOC Corso.md                   ← indice corso
        <modulo>/
          _MOC Modulo.md                ← indice modulo
          <sottomodulo>_aggregato.md    ← se c'è contenuto diretto
          <item>.md                     ← una nota per lezione
    """
    dest_root.mkdir(parents=True, exist_ok=True)
    stats = {"corsi": 0, "note": 0, "wikilinks": 0}

    # Indicizza: per ogni corso, raccogli tutti i termini glossario (case-insensitive)
    term_to_note: dict[str, dict[str, str]] = {}  # corso -> {term_lower: note_name}
    for c, m, s, it, dir_path in iter_all_items(source_root):
        if corso_filter and c != corso_filter:
            continue
        gloss = dir_path / "glossary.md"
        if gloss.exists():
            for term in extract_glossary_terms(gloss.read_text(encoding="utf-8", errors="ignore")):
                note = _note_name(it if it != "(contenuto diretto)" else s + "_aggregato")
                term_to_note.setdefault(c, {}).setdefault(term.lower(), note)

    corsi_seen: dict[str, dict] = {}

    for c, m, s, it, dir_path in iter_all_items(source_root):
        if corso_filter and c != corso_filter:
            continue

        note_name = _note_name(it if it != "(contenuto diretto)" else s + "_aggregato")
        note_dir = dest_root / c / m
        note_dir.mkdir(parents=True, exist_ok=True)
        note_path = note_dir / f"{note_name}.md"

        # Componi il contenuto della nota
        parts: list[str] = []
        parts.append(f"# {note_name}")
        parts.append(f"\n**Corso**: {_link(c)} · **Modulo**: {_link(m)} · **Sottomodulo**: {s}\n")

        for key, header, fname in [
            ("summary", "## Riassunto", "summary.md"),
            ("glossary", "## Glossario", "glossary.md"),
            ("questions", "## Domande di ripasso", "questions.md"),
            ("mindmap", "## Mappa concettuale", "mindmap.md"),
        ]:
            f = dir_path / fname
            if f.exists():
                content = f.read_text(encoding="utf-8", errors="ignore").strip()
                parts.append(f"\n{header}\n\n{content}\n")

        # Flashcards come callout
        fc = dir_path / "flashcards.json"
        if fc.exists():
            try:
                import json
                cards = json.loads(fc.read_text(encoding="utf-8"))
                if cards:
                    parts.append("\n## Flashcard\n")
                    for c_ in cards:
                        q = c_.get("domanda", "")
                        a = c_.get("risposta", "")
                        parts.append(f"> [!question] {q}\n> {a}\n")
            except json.JSONDecodeError:
                pass

        text = "\n".join(parts)

        # Aggiungi wikilinks automatici ai termini di glossario del corso
        course_terms = term_to_note.get(c, {})
        if course_terms:
            # Sostituisci solo la prima occorrenza di ogni termine per non spammare
            seen_in_note: set[str] = set()
            def _replace(match: re.Match) -> str:
                word = match.group(0)
                key = word.lower()
                if key in seen_in_note or key not in course_terms:
                    return word
                target = course_terms[key]
                if target == note_name:
                    return word  # non link a se stesso
                seen_in_note.add(key)
                stats["wikilinks"] += 1
                return f"[[{target}|{word}]]"

            # Regex con tutti i termini ordinati per lunghezza decrescente
            sorted_terms = sorted(course_terms.keys(), key=len, reverse=True)
            if sorted_terms:
                pattern = re.compile(
                    r"\b(" + "|".join(re.escape(t) for t in sorted_terms) + r")\b",
                    re.IGNORECASE,
                )
                # Evita di linkare dentro header o dentro wikilink esistenti: semplice ma efficace
                text = pattern.sub(_replace, text)

        note_path.write_text(text, encoding="utf-8")
        stats["note"] += 1
        corsi_seen.setdefault(c, {}).setdefault(m, []).append(note_name)

    # MOC (Map of Content) per corso e modulo
    for c, moduli in corsi_seen.items():
        stats["corsi"] += 1
        moc_path = dest_root / c / "_MOC Corso.md"
        lines = [f"# MOC - {c}\n"]
        for m, notes in sorted(moduli.items()):
            lines.append(f"\n## {m}\n")
            for n in sorted(notes):
                lines.append(f"- [[{n}]]")
        moc_path.write_text("\n".join(lines), encoding="utf-8")

        for m, notes in moduli.items():
            moc_m = dest_root / c / m / "_MOC Modulo.md"
            lines = [f"# MOC - {m}\n\nCorso: [[{c}]]\n"]
            for n in sorted(notes):
                lines.append(f"- [[{n}]]")
            moc_m.write_text("\n".join(lines), encoding="utf-8")

    return stats
