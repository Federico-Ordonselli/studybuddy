"""Orchestrazione del processing di file singoli e di gruppi."""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from .llm import LLMClient


def process_file(
    text: str,
    llm: LLMClient,
    do_summary: bool = True,
    do_flashcards: bool = True,
    n_flashcards: int = 15,
    do_glossary: bool = True,
    do_questions: bool = True,
    n_questions: int = 8,
    do_mindmap: bool = False,
    do_mcq: bool = False,
    n_mcq: int = 15,
    context_label: str | None = None,
    status_cb: Callable[[str], None] | None = None,
) -> dict:
    def log(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    out: dict = {}
    if do_summary:
        log("Genero il riassunto…")
        out["summary"] = llm.summarize(text, context_label=context_label)
    if do_flashcards:
        log(f"Genero {n_flashcards} flashcard…")
        out["flashcards"] = llm.flashcards(text, n=n_flashcards, context_label=context_label)
    if do_glossary:
        log("Genero il glossario…")
        out["glossary"] = llm.glossary(text, context_label=context_label)
    if do_questions:
        log(f"Genero {n_questions} domande di ripasso…")
        out["questions"] = llm.questions(text, n=n_questions, context_label=context_label)
    if do_mindmap:
        log("Genero la mappa concettuale…")
        out["mindmap"] = llm.mindmap(text, context_label=context_label)
    if do_mcq:
        log(f"Genero {n_mcq} domande a scelta multipla…")
        out["mcq"] = llm.mcq(text, n=n_mcq, context_label=context_label)
    return out


def build_group_text(files: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    for name, text in files:
        parts.append(f"# Lezione: {name}\n\n{text.strip()}")
    return "\n\n---\n\n".join(parts)


def process_group(
    files: list[tuple[str, str]],
    llm: LLMClient,
    group_label: str,
    do_summary: bool = True,
    do_flashcards: bool = True,
    n_flashcards: int = 20,
    do_glossary: bool = True,
    do_questions: bool = True,
    n_questions: int = 10,
    do_mindmap: bool = False,
    do_mcq: bool = False,
    n_mcq: int = 20,
    status_cb: Callable[[str], None] | None = None,
) -> dict:
    combined = build_group_text(files)
    return process_file(
        text=combined,
        llm=llm,
        do_summary=do_summary,
        do_flashcards=do_flashcards,
        n_flashcards=n_flashcards,
        do_glossary=do_glossary,
        do_questions=do_questions,
        n_questions=n_questions,
        do_mindmap=do_mindmap,
        do_mcq=do_mcq,
        n_mcq=n_mcq,
        context_label=group_label,
        status_cb=status_cb,
    )
