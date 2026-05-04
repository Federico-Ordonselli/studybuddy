"""Client LLM basato su Ollama."""
from __future__ import annotations

import json
import re
from typing import Any

import ollama


def list_ollama_models() -> list[str]:
    data = ollama.list()
    models = data.get("models", []) if isinstance(data, dict) else getattr(data, "models", [])
    names: list[str] = []
    for m in models:
        if isinstance(m, dict):
            names.append(m.get("name") or m.get("model") or "")
        else:
            names.append(getattr(m, "name", None) or getattr(m, "model", "") or "")
    return [n for n in names if n]


def _system_prefix(language: str) -> str:
    return (
        f"Sei un assistente didattico esperto. "
        f"Il testo sorgente può essere in qualsiasi lingua (spesso inglese nei corsi tecnici). "
        f"IMPORTANTE: produci SEMPRE l'output in {language}, "
        f"traducendo e adattando se il sorgente è in un'altra lingua. "
        f"Non copiare frasi in inglese nell'output. "
    )


class LLMClient:
    def __init__(
        self,
        model: str = "llama3.1:8b",
        language: str = "italiano",
        num_ctx: int = 8192,
        temperature: float = 0.3,
    ) -> None:
        self.model = model
        self.language = language
        self.num_ctx = num_ctx
        self.temperature = temperature

    def _chat(self, system: str, user: str, json_mode: bool = False) -> str:
        opts: dict[str, Any] = {"num_ctx": self.num_ctx, "temperature": self.temperature}
        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["format"] = "json"
        resp = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options=opts,
            **kwargs,
        )
        return resp["message"]["content"]

    @staticmethod
    def _chunk(text: str, max_chars: int = 12000) -> list[str]:
        if len(text) <= max_chars:
            return [text]
        paragraphs = re.split(r"\n\s*\n", text)
        chunks: list[str] = []
        cur = ""
        for p in paragraphs:
            if len(cur) + len(p) + 2 > max_chars and cur:
                chunks.append(cur)
                cur = p
            else:
                cur = f"{cur}\n\n{p}" if cur else p
        if cur:
            chunks.append(cur)
        result: list[str] = []
        for c in chunks:
            if len(c) <= max_chars:
                result.append(c)
            else:
                for i in range(0, len(c), max_chars):
                    result.append(c[i : i + max_chars])
        return result

    def summarize(self, text: str, context_label: str | None = None) -> str:
        chunks = self._chunk(text)
        system = _system_prefix(self.language) + (
            "Produci riassunti chiari, strutturati, con concetti chiave in grassetto."
        )
        ctx = f" (contesto: {context_label})" if context_label else ""
        if len(chunks) == 1:
            user = (
                f"Riassumi il seguente testo{ctx} in modo completo ma conciso, in {self.language}. "
                "Usa markdown con titoli ## per le sezioni principali e bullet per i punti chiave. "
                "Evidenzia in **grassetto** i termini e concetti più importanti.\n\n"
                f"---\n{chunks[0]}\n---"
            )
            return self._chat(system, user)

        partials: list[str] = []
        for i, c in enumerate(chunks, 1):
            user = (
                f"Questa è la parte {i}/{len(chunks)} di un documento{ctx}. "
                f"Estrai i punti chiave come bullet list in {self.language}, senza introduzioni.\n\n"
                f"---\n{c}\n---"
            )
            partials.append(self._chat(system, user))
        combined = "\n\n".join(partials)
        user_final = (
            f"Di seguito ci sono i punti chiave estratti dalle varie sezioni di un documento{ctx}. "
            f"Unifica tutto in un unico riassunto coerente e ben strutturato in markdown in {self.language}, "
            "eliminando ripetizioni. Usa titoli ## e **grassetto** per i concetti importanti.\n\n"
            f"---\n{combined}\n---"
        )
        return self._chat(system, user_final)

    def flashcards(self, text: str, n: int = 15, context_label: str | None = None) -> list[dict[str, str]]:
        system = _system_prefix(self.language) + (
            "Generi flashcard di studio. Rispondi SOLO con JSON valido, niente altro."
        )
        source = text if len(text) <= 14000 else self.summarize(text, context_label=context_label)
        ctx = f" (contesto: {context_label})" if context_label else ""
        user = (
            f"Crea esattamente {n} flashcard dal seguente testo{ctx}, in {self.language}. "
            "Le domande devono essere specifiche e testare la comprensione (non banali). "
            "Le risposte devono essere concise ma complete (1-3 frasi). "
            'Restituisci un JSON con questa forma esatta: '
            '{"flashcards": [{"domanda": "...", "risposta": "..."}]}. '
            "Niente testo fuori dal JSON. "
            f"Sia le domande sia le risposte devono essere in {self.language}.\n\n"
            f"---\n{source}\n---"
        )
        raw = self._chat(system, user, json_mode=True)
        return _parse_flashcards(raw, n)

    def glossary(self, text: str, context_label: str | None = None) -> str:
        system = _system_prefix(self.language) + "Crei glossari tecnici chiari."
        source = text if len(text) <= 14000 else self.summarize(text, context_label=context_label)
        ctx = f" (contesto: {context_label})" if context_label else ""
        user = (
            f"Estrai dal testo{ctx} i termini tecnici, acronimi e concetti chiave e scrivi un glossario "
            f"in markdown, in {self.language}. "
            "Formato: `- **Termine**: definizione sintetica (1-2 frasi).` "
            "Ordina alfabeticamente. Includi tra 8 e 25 voci in base alla ricchezza del testo. "
            "Se i termini sono sigle o nomi propri tecnici (es. DAX, Power Query, ETL) mantieni "
            f"l'originale come **Termine** e scrivi la definizione in {self.language}.\n\n"
            f"---\n{source}\n---"
        )
        return self._chat(system, user)

    def questions(self, text: str, n: int = 8, context_label: str | None = None) -> str:
        system = _system_prefix(self.language) + (
            "Crei domande di ripasso che stimolano il ragionamento."
        )
        source = text if len(text) <= 14000 else self.summarize(text, context_label=context_label)
        ctx = f" (contesto: {context_label})" if context_label else ""
        user = (
            f"Crea {n} domande di ripasso sul testo{ctx}, in {self.language}. "
            "Mescola domande di comprensione, applicazione e ragionamento critico. "
            "Per ciascuna, fornisci anche una risposta modello. "
            "Formato markdown:\n\n"
            "### 1. Domanda\n"
            "Testo della domanda.\n\n"
            "**Risposta:** risposta modello.\n\n"
            f"---\n{source}\n---"
        )
        return self._chat(system, user)

    def focused_practice(self, weak_cards_text: str, n: int = 10) -> str:
        """Genera esercizi mirati a partire dalle carte deboli dell'utente."""
        system = _system_prefix(self.language) + (
            "Crei esercizi di rinforzo mirati sui punti deboli dello studente. "
            "Sei empatico ma rigoroso."
        )
        user = (
            f"Lo studente sbaglia spesso queste flashcard. "
            f"Crea {n} esercizi di rinforzo mirati in {self.language}. "
            "Mescola: (a) spiegazioni approfondite dei concetti, "
            "(b) nuove domande riformulate diversamente, "
            "(c) esempi pratici/casi d'uso. "
            "Formato markdown con titoli ### per esercizio. "
            "Identifica anche i pattern comuni negli errori (se ci sono).\n\n"
            "### Flashcard con errori frequenti:\n"
            f"{weak_cards_text}\n"
        )
        return self._chat(system, user)

    def mcq(self, text: str, n: int = 15, context_label: str | None = None) -> list[dict[str, Any]]:
        """Genera domande a scelta multipla con 4 opzioni e la risposta corretta."""
        system = _system_prefix(self.language) + (
            "Generi domande a scelta multipla di stile esame. "
            "Rispondi SOLO con JSON valido, niente altro."
        )
        source = text if len(text) <= 14000 else self.summarize(text, context_label=context_label)
        ctx = f" (contesto: {context_label})" if context_label else ""
        user = (
            f"Crea esattamente {n} domande a scelta multipla dal testo{ctx}, in {self.language}. "
            "Ogni domanda deve avere 4 opzioni (A, B, C, D) e UNA sola risposta corretta. "
            "Le opzioni sbagliate devono essere plausibili (non banali) per testare davvero la conoscenza. "
            "Includi una breve spiegazione della risposta corretta. "
            "Assegna a ogni domanda un 'topic' breve (2-4 parole) che descrive l'argomento trattato, "
            "utile per analizzare i punti deboli. "
            'Restituisci JSON così: {"questions":[{'
            '"domanda":"...", "opzioni":["...","...","...","..."], '
            '"corretta":0, "spiegazione":"...", "topic":"..."}]}. '
            "L'indice 'corretta' è 0-based (0=prima opzione, 3=ultima). "
            f"Tutto l'output in {self.language}.\n\n"
            f"---\n{source}\n---"
        )
        raw = self._chat(system, user, json_mode=True)
        return _parse_mcq(raw, n)

    def mindmap(self, text: str, context_label: str | None = None) -> str:
        """Genera una mappa concettuale in formato Mermaid mindmap."""
        system = _system_prefix(self.language) + (
            "Crei mappe concettuali in formato Mermaid mindmap. "
            "Rispondi SOLO con il blocco mermaid, niente testo fuori."
        )
        source = text if len(text) <= 14000 else self.summarize(text, context_label=context_label)
        ctx = f" (contesto: {context_label})" if context_label else ""
        user = (
            f"Crea una mappa concettuale (mindmap) del testo{ctx} in formato Mermaid, in {self.language}. "
            "Massimo 3 livelli di profondità. Il nodo root deve essere il tema principale. "
            "Rami di primo livello: concetti principali (4-8). Foglie: sotto-concetti chiave. "
            "Usa SOLO testo semplice nei nodi, niente caratteri speciali (no parentesi, virgole, due punti, "
            "trattini lunghi, simboli non ASCII tipo è é à). Sostituisci con trattini bassi o spazi normali. "
            "Formato OBBLIGATORIO (indentazione con spazi, non tab):\n\n"
            "```mermaid\n"
            "mindmap\n"
            "  root((Tema centrale))\n"
            "    Concetto_1\n"
            "      Dettaglio_a\n"
            "      Dettaglio_b\n"
            "    Concetto_2\n"
            "      Dettaglio_c\n"
            "```\n\n"
            "Rispondi SOLO con il blocco ```mermaid ... ```.\n\n"
            f"---\n{source}\n---"
        )
        raw = self._chat(system, user)
        return _extract_mermaid(raw)


def _extract_mermaid(raw: str) -> str:
    """Estrae il blocco mermaid dalla risposta dell'LLM, con sanificazione."""
    m = re.search(r"```mermaid\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    body = m.group(1).strip() if m else raw.strip()
    # Assicura che inizi con 'mindmap'
    if not body.lstrip().lower().startswith("mindmap"):
        body = "mindmap\n" + body
    # Rimuovi caratteri che rompono Mermaid nei nodi (parentesi tonde tranne root((...)))
    lines = body.splitlines()
    cleaned: list[str] = []
    for line in lines:
        if line.strip().startswith("root(("):
            cleaned.append(line)
        else:
            # sostituisci parentesi sporche con nulla, mantieni solo alfanumerici/spazi/_
            safe = re.sub(r"[\(\)\[\]\{\}:;,\"']", "", line)
            cleaned.append(safe)
    return "\n".join(cleaned)


def _parse_mcq(raw: str, expected: int) -> list[dict[str, Any]]:
    """Parser robusto per MCQ."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []

    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("questions") or data.get("mcq") or data.get("items") or []
    else:
        items = []

    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        q = it.get("domanda") or it.get("question")
        opts = it.get("opzioni") or it.get("options") or it.get("choices")
        correct = it.get("corretta")
        if correct is None:
            correct = it.get("correct")
        if correct is None:
            correct = it.get("answer")
        explanation = it.get("spiegazione") or it.get("explanation") or ""
        topic = it.get("topic") or it.get("argomento") or "Generale"

        if not q or not opts or not isinstance(opts, list) or len(opts) < 2:
            continue
        # Normalizza correct a int 0-based
        if isinstance(correct, str):
            s = correct.strip().upper()
            if s in "ABCD":
                correct = "ABCD".index(s)
            else:
                try:
                    correct = int(s)
                except ValueError:
                    continue
        if not isinstance(correct, int) or correct < 0 or correct >= len(opts):
            continue

        out.append({
            "domanda": str(q).strip(),
            "opzioni": [str(o).strip() for o in opts],
            "corretta": correct,
            "spiegazione": str(explanation).strip(),
            "topic": str(topic).strip(),
        })
    return out[:expected] if expected else out


def _parse_flashcards(raw: str, expected: int) -> list[dict[str, str]]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []

    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("flashcards") or data.get("cards") or data.get("items") or []
    else:
        items = []

    out: list[dict[str, str]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        q = it.get("domanda") or it.get("question") or it.get("q") or it.get("front")
        a = it.get("risposta") or it.get("answer") or it.get("a") or it.get("back")
        if q and a:
            out.append({"domanda": str(q).strip(), "risposta": str(a).strip()})
    return out[:expected] if expected else out
