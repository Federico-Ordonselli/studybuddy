"""Integrazione con AnkiConnect per identificare i punti deboli dell'utente.

Richiede l'addon AnkiConnect installato su Anki Desktop (https://ankiweb.net/shared/info/2055492159).
Anki deve essere in esecuzione e l'addon attivo.
"""
from __future__ import annotations

from typing import Any

import json
import urllib.error
import urllib.request


ANKI_URL = "http://127.0.0.1:8765"


class AnkiConnectError(Exception):
    pass


def _invoke(action: str, **params: Any) -> Any:
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(ANKI_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise AnkiConnectError(
            f"Impossibile contattare AnkiConnect: {e}. "
            "Controlla che Anki sia aperto e l'addon AnkiConnect installato."
        ) from e
    if data.get("error"):
        raise AnkiConnectError(data["error"])
    return data.get("result")


def is_available() -> bool:
    try:
        _invoke("version")
        return True
    except Exception:  # noqa: BLE001
        return False


def list_decks() -> list[str]:
    return _invoke("deckNames") or []


def get_weak_cards(deck: str, limit: int = 30) -> list[dict[str, Any]]:
    """Restituisce le carte con più lapse (sbagliate più volte) dal deck scelto.

    Usa lapses>=1, ordinate per numero di lapses decrescente.
    """
    # Query Anki: carte del deck con almeno 1 lapse
    query = f'deck:"{deck}" prop:lapses>=1'
    card_ids = _invoke("findCards", query=query) or []
    if not card_ids:
        return []

    info = _invoke("cardsInfo", cards=card_ids) or []
    # Ordina per lapses decrescente, poi per 'fields' (per ora)
    info.sort(key=lambda c: c.get("lapses", 0), reverse=True)
    out: list[dict[str, Any]] = []
    for c in info[:limit]:
        fields = c.get("fields", {})
        # Prendi i primi due campi come front/back (genericamente funziona)
        field_vals = list(fields.items())
        front = field_vals[0][1].get("value", "") if len(field_vals) > 0 else ""
        back = field_vals[1][1].get("value", "") if len(field_vals) > 1 else ""
        # Strippa HTML minimale
        import re
        def strip_html(s: str) -> str:
            return re.sub(r"<[^>]+>", "", s).strip()
        out.append({
            "front": strip_html(front),
            "back": strip_html(back),
            "lapses": c.get("lapses", 0),
            "reps": c.get("reps", 0),
            "interval": c.get("interval", 0),
        })
    return out


def summarize_weak_topics(weak_cards: list[dict[str, Any]]) -> str:
    """Costruisce un prompt/testo con le carte deboli, da dare in pasto all'LLM."""
    if not weak_cards:
        return ""
    lines: list[str] = []
    for i, c in enumerate(weak_cards, 1):
        lines.append(f"{i}. [lapses: {c['lapses']}] {c['front']}\n   Risposta: {c['back']}")
    return "\n".join(lines)
