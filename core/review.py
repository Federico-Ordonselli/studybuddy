"""Sistema di ripasso integrato (spaced repetition, algoritmo SM-2).

Le flashcard vengono importate automaticamente dalla biblioteca e gestite con
un proprio stato di ripasso persistente. Nessuna dipendenza da Anki.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .library import iter_all_items


STATE_FILENAME = ".review_state.json"


# ---------- Modello dati ----------

@dataclass
class ReviewCard:
    """Una singola carta nel sistema di ripasso."""
    id: str                          # hash stabile di (front+back+path)
    front: str
    back: str
    corso: str
    modulo: str
    sottomodulo: str
    item: str                        # lezione
    source_path: str                 # cartella da cui proviene
    # Stato SM-2
    ease: float = 2.5
    interval: int = 0                # giorni
    reps: int = 0                    # ripetizioni consecutive riuscite
    lapses: int = 0                  # volte che è andata male
    due: str = ""                    # ISO date YYYY-MM-DD
    last_review: str = ""            # ISO date
    suspended: bool = False

    def is_due(self, today: date | None = None) -> bool:
        if self.suspended:
            return False
        if not self.due:
            return True
        today = today or date.today()
        try:
            return date.fromisoformat(self.due) <= today
        except ValueError:
            return True

    def is_new(self) -> bool:
        return self.reps == 0 and not self.last_review


# ---------- Algoritmo SM-2 ----------

def apply_rating(card: ReviewCard, rating: str) -> ReviewCard:
    """Aggiorna la carta secondo il rating dell'utente.

    rating: 'again' | 'hard' | 'good' | 'easy'

    SM-2 semplificato ispirato ad Anki:
    - again: reset reps, lapse++, due domani, ease -= 0.2 (min 1.3)
    - hard:  ease -= 0.15, interval *= 1.2 (se reps>=1) o 1 giorno
    - good:  ease invariato, primo review = 1, secondo = 6, poi interval*ease
    - easy:  ease += 0.15, primo review = 4, poi interval*ease*1.3
    """
    today = date.today()
    card.last_review = today.isoformat()

    if rating == "again":
        card.lapses += 1
        card.reps = 0
        card.ease = max(1.3, card.ease - 0.2)
        card.interval = 0
        card.due = (today + timedelta(days=1)).isoformat()
        return card

    if rating == "hard":
        card.reps += 1
        card.ease = max(1.3, card.ease - 0.15)
        if card.interval == 0:
            card.interval = 1
        else:
            card.interval = max(1, int(card.interval * 1.2))
    elif rating == "good":
        card.reps += 1
        if card.reps == 1:
            card.interval = 1
        elif card.reps == 2:
            card.interval = 6
        else:
            card.interval = max(1, int(card.interval * card.ease))
    elif rating == "easy":
        card.reps += 1
        card.ease = min(3.5, card.ease + 0.15)
        if card.reps == 1:
            card.interval = 4
        elif card.reps == 2:
            card.interval = 8
        else:
            card.interval = max(1, int(card.interval * card.ease * 1.3))
    else:
        raise ValueError(f"Rating sconosciuto: {rating}")

    card.due = (today + timedelta(days=card.interval)).isoformat()
    return card


# ---------- Persistenza ----------

def state_path(root: Path) -> Path:
    return root / STATE_FILENAME


def load_state(root: Path) -> dict[str, ReviewCard]:
    p = state_path(root)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, ReviewCard] = {}
    for cid, data in raw.items():
        try:
            out[cid] = ReviewCard(**data)
        except TypeError:
            # schema diverso, ignoralo
            continue
    return out


def save_state(root: Path, state: dict[str, ReviewCard]) -> None:
    p = state_path(root)
    serial = {cid: asdict(card) for cid, card in state.items()}
    p.write_text(json.dumps(serial, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- Import automatico ----------

def _card_id(front: str, back: str, path: str) -> str:
    h = hashlib.sha256(f"{path}::{front}::{back}".encode("utf-8")).hexdigest()
    return h[:16]


def sync_from_library(root: Path, state: dict[str, ReviewCard] | None = None) -> dict[str, Any]:
    """Scansiona outputs/ e aggiunge al sistema di ripasso le flashcard nuove.

    Ritorna: {'added': N, 'existing': M, 'total': T, 'state': dict}
    """
    if state is None:
        state = load_state(root)

    added = 0
    existing = 0
    seen_ids: set[str] = set()

    for corso, modulo, sub, item, dir_path in iter_all_items(root):
        fc_path = dir_path / "flashcards.json"
        if not fc_path.exists():
            continue
        try:
            cards = json.loads(fc_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(cards, list):
            continue

        for c in cards:
            if not isinstance(c, dict):
                continue
            front = (c.get("domanda") or c.get("question") or c.get("front") or "").strip()
            back = (c.get("risposta") or c.get("answer") or c.get("back") or "").strip()
            if not front or not back:
                continue

            cid = _card_id(front, back, str(dir_path))
            seen_ids.add(cid)
            if cid in state:
                existing += 1
                continue

            state[cid] = ReviewCard(
                id=cid,
                front=front,
                back=back,
                corso=corso,
                modulo=modulo,
                sottomodulo=sub,
                item=item,
                source_path=str(dir_path),
            )
            added += 1

    save_state(root, state)
    return {
        "added": added,
        "existing": existing,
        "total": len(state),
        "orphan": len(state) - len(seen_ids),  # carte non più presenti nelle fonti
        "state": state,
    }


# ---------- Query ----------

def get_due_cards(
    state: dict[str, ReviewCard],
    corso: str | None = None,
    modulo: str | None = None,
    include_new: bool = True,
    max_new_per_session: int = 20,
) -> list[ReviewCard]:
    """Ritorna carte scadute (+ un batch di nuove), filtrate per corso/modulo."""
    today = date.today()
    due_review: list[ReviewCard] = []
    new_cards: list[ReviewCard] = []

    for card in state.values():
        if corso and card.corso != corso:
            continue
        if modulo and card.modulo != modulo:
            continue
        if card.suspended:
            continue
        if card.is_new():
            new_cards.append(card)
        elif card.is_due(today):
            due_review.append(card)

    # Ordina: scadute (prima quelle con lapses maggiori), poi nuove
    due_review.sort(key=lambda c: (-c.lapses, c.due))
    result = due_review
    if include_new:
        result = result + new_cards[:max_new_per_session]
    return result


def get_stats(state: dict[str, ReviewCard]) -> dict[str, Any]:
    today = date.today()
    total = len(state)
    new = sum(1 for c in state.values() if c.is_new())
    due = sum(1 for c in state.values() if c.is_due(today) and not c.is_new())
    learning = sum(1 for c in state.values() if c.reps > 0 and c.interval < 21)
    mature = sum(1 for c in state.values() if c.interval >= 21)
    suspended = sum(1 for c in state.values() if c.suspended)

    # Per corso
    per_corso: dict[str, dict[str, int]] = {}
    for c in state.values():
        d = per_corso.setdefault(c.corso, {"total": 0, "due": 0, "new": 0, "mature": 0})
        d["total"] += 1
        if c.is_due(today) and not c.is_new():
            d["due"] += 1
        if c.is_new():
            d["new"] += 1
        if c.interval >= 21:
            d["mature"] += 1

    # Punti deboli (lapses >= 2)
    weak = sorted(
        [c for c in state.values() if c.lapses >= 2],
        key=lambda c: -c.lapses,
    )[:20]

    return {
        "total": total,
        "new": new,
        "due": due,
        "learning": learning,
        "mature": mature,
        "suspended": suspended,
        "per_corso": per_corso,
        "weak_cards": weak,
    }


def list_courses_modules(state: dict[str, ReviewCard]) -> tuple[list[str], dict[str, list[str]]]:
    courses: set[str] = set()
    mods: dict[str, set[str]] = {}
    for c in state.values():
        courses.add(c.corso)
        mods.setdefault(c.corso, set()).add(c.modulo)
    return sorted(courses), {k: sorted(v) for k, v in mods.items()}


def export_to_csv_anki(state: dict[str, ReviewCard]) -> str:
    """Esporta tutte le carte in formato CSV compatibile Anki (separatore ;)."""
    import io
    import csv
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    for card in state.values():
        writer.writerow([card.front, card.back])
    return buf.getvalue()


def reset_progress(state: dict[str, ReviewCard], corso: str | None = None) -> int:
    """Azzera lo stato di ripasso (ma non elimina le carte). Ritorna quante resettate."""
    count = 0
    for card in state.values():
        if corso and card.corso != corso:
            continue
        card.ease = 2.5
        card.interval = 0
        card.reps = 0
        card.lapses = 0
        card.due = ""
        card.last_review = ""
        card.suspended = False
        count += 1
    return count
