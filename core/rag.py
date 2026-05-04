"""RAG (Retrieval-Augmented Generation) sui documenti della biblioteca.

Pipeline completa:
1. Indicizzazione: documenti -> chunk -> embedding -> ChromaDB persistente
2. Query: domanda -> embedding -> retrieval top-k -> prompt -> LLM -> risposta

Usa Ollama sia per gli embedding (nomic-embed-text) sia per la generazione (qwen2.5:14b).
ChromaDB salva l'indice su disco in outputs/.rag/<corso>/.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import chromadb
import ollama


EMBED_MODEL = "nomic-embed-text"
RAG_DIR_NAME = ".rag"


@dataclass
class Chunk:
    """Un pezzo di documento pronto per essere indicizzato."""
    text: str
    source_path: str       # path relativo al file sorgente
    source_type: str       # "summary" | "transcript"
    corso: str
    modulo: str
    sottomodulo: str
    item: str
    chunk_index: int       # posizione del chunk nel documento

    def to_metadata(self) -> dict:
        """ChromaDB metadata (solo tipi semplici: str, int, float, bool)."""
        return {
            "source_path": self.source_path,
            "source_type": self.source_type,
            "corso": self.corso,
            "modulo": self.modulo,
            "sottomodulo": self.sottomodulo,
            "item": self.item,
            "chunk_index": self.chunk_index,
        }


# ---------------------------------------------------------------------------
# Chunking: spezza un testo lungo in pezzi indicizzabili
# ---------------------------------------------------------------------------

def chunk_text(text: str, max_chars: int = 1500, overlap: int = 150) -> list[str]:
    """Divide il testo in pezzi di ~max_chars, con overlap tra pezzi consecutivi.

    Strategia: prova a spezzare ai paragrafi, fallback su frase singola, fallback su hard cut.
    L'overlap serve a non perdere contesto al confine tra chunk.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    # Spezza per paragrafi
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current)
            # Mantieni un overlap del finale del chunk precedente
            tail = current[-overlap:] if len(current) > overlap else ""
            current = tail + "\n\n" + para if tail else para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(current)

    # Hard split sui pezzi ancora troppo grossi (es. paragrafi enormi)
    final: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            final.append(c)
        else:
            for i in range(0, len(c), max_chars - overlap):
                final.append(c[i : i + max_chars])
    return final


# ---------------------------------------------------------------------------
# Discovery: scansiona outputs/ e produce chunk pronti per l'indicizzazione
# ---------------------------------------------------------------------------

def iter_chunks_for_corso(outputs_root: Path, corso: str) -> Iterator[Chunk]:
    """Genera i chunk di tutti i documenti di un corso.

    Considera summary.md e transcript.txt (in questa priorità) per ogni elemento
    della biblioteca del corso.
    """
    corso_root = outputs_root / corso
    if not corso_root.exists():
        return

    for modulo_dir in sorted(corso_root.iterdir()):
        if not modulo_dir.is_dir():
            continue
        modulo = modulo_dir.name
        for sub_dir in sorted(modulo_dir.iterdir()):
            if not sub_dir.is_dir():
                continue
            sottomodulo = sub_dir.name

            # "Contenuto diretto" del sottomodulo (aggregato)
            yield from _chunks_from_item_dir(
                sub_dir, corso, modulo, sottomodulo, item="(contenuto diretto)"
            )

            # Sottoelementi
            for item_dir in sorted(sub_dir.iterdir()):
                if not item_dir.is_dir() or item_dir.name == "sources":
                    continue
                yield from _chunks_from_item_dir(
                    item_dir, corso, modulo, sottomodulo, item=item_dir.name
                )


def _chunks_from_item_dir(
    item_dir: Path, corso: str, modulo: str, sottomodulo: str, item: str
) -> Iterator[Chunk]:
    """Estrae chunk da summary.md e transcript.txt di una specifica item directory."""
    for fname, source_type in [("summary.md", "summary"), ("transcript.txt", "transcript")]:
        fpath = item_dir / fname
        if not fpath.exists():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text.strip():
            continue

        for idx, ch_text in enumerate(chunk_text(text)):
            yield Chunk(
                text=ch_text,
                source_path=str(fpath.relative_to(item_dir.parent.parent.parent)),
                source_type=source_type,
                corso=corso,
                modulo=modulo,
                sottomodulo=sottomodulo,
                item=item,
                chunk_index=idx,
            )


# ---------------------------------------------------------------------------
# Embedding: vettorializza un testo via Ollama
# ---------------------------------------------------------------------------

def embed_text(text: str, model: str = EMBED_MODEL) -> list[float]:
    """Calcola l'embedding di un singolo testo via Ollama API."""
    response = ollama.embeddings(model=model, prompt=text)
    return response["embedding"]


# ---------------------------------------------------------------------------
# ChromaDB: gestione del vector DB persistente
# ---------------------------------------------------------------------------

def _client(outputs_root: Path, corso: str) -> chromadb.PersistentClient:
    """Restituisce un client ChromaDB persistente per un corso specifico."""
    rag_dir = outputs_root / RAG_DIR_NAME / corso
    rag_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(rag_dir))


def _collection_name(corso: str) -> str:
    """Nome della collection ChromaDB per un corso (sanificato)."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", corso)[:60]
    return f"corso_{safe}"


# ---------------------------------------------------------------------------
# Indicizzazione: pipeline completa documenti -> ChromaDB
# ---------------------------------------------------------------------------

def index_corso(
    outputs_root: Path,
    corso: str,
    progress_callback=None,
) -> dict:
    """Indicizza tutti i documenti di un corso. Sovrascrive l'indice esistente.

    Restituisce: {"chunks_indexed": N, "documents": M, "errors": K}
    """
    client = _client(outputs_root, corso)
    coll_name = _collection_name(corso)

    # Drop & recreate per garantire freschezza
    try:
        client.delete_collection(coll_name)
    except Exception:  # noqa: BLE001
        pass
    coll = client.create_collection(
        name=coll_name,
        metadata={
            "corso": corso,
            "embedding_model": EMBED_MODEL,
            "hnsw:space": "cosine",
        },
    )

    chunks_list = list(iter_chunks_for_corso(outputs_root, corso))
    if not chunks_list:
        return {"chunks_indexed": 0, "documents": 0, "errors": 0}

    # Indicizza in batch (ChromaDB gestisce bene fino a centinaia per call)
    batch_size = 32
    total = len(chunks_list)
    indexed = 0
    errors = 0
    documents_set: set[str] = set()

    for i in range(0, total, batch_size):
        batch = chunks_list[i : i + batch_size]
        ids: list[str] = []
        embeddings: list[list[float]] = []
        documents: list[str] = []
        metadatas: list[dict] = []

        for j, chunk in enumerate(batch):
            try:
                emb = embed_text(chunk.text)
                ids.append(f"{i + j}__{chunk.source_type}__{chunk.chunk_index}")
                embeddings.append(emb)
                documents.append(chunk.text)
                metadatas.append(chunk.to_metadata())
                documents_set.add(chunk.source_path)
            except Exception:  # noqa: BLE001
                errors += 1

        if embeddings:
            coll.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            indexed += len(embeddings)

        if progress_callback:
            progress_callback(min(i + batch_size, total), total)

    return {
        "chunks_indexed": indexed,
        "documents": len(documents_set),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Stato indice
# ---------------------------------------------------------------------------

def get_index_stats(outputs_root: Path, corso: str) -> dict | None:
    """Restituisce statistiche sull'indice esistente, o None se non esiste."""
    client = _client(outputs_root, corso)
    coll_name = _collection_name(corso)
    try:
        coll = client.get_collection(coll_name)
    except Exception:  # noqa: BLE001
        return None
    return {
        "name": coll_name,
        "chunks": coll.count(),
        "metadata": coll.metadata or {},
    }


# ---------------------------------------------------------------------------
# Retrieval: trova i chunk più rilevanti per una query
# ---------------------------------------------------------------------------

@dataclass
class RetrievedChunk:
    text: str
    metadata: dict
    distance: float

    @property
    def similarity(self) -> float:
        # Cosine distance: 0=identico, 2=opposto. Convertiamo a similarity 0-1.
        return max(0.0, 1.0 - self.distance)


def retrieve(
    outputs_root: Path, corso: str, query: str, top_k: int = 5
) -> list[RetrievedChunk]:
    """Recupera i top-k chunk più rilevanti per la query."""
    client = _client(outputs_root, corso)
    coll_name = _collection_name(corso)
    try:
        coll = client.get_collection(coll_name)
    except Exception:  # noqa: BLE001
        return []

    query_embedding = embed_text(query)
    results = coll.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    out: list[RetrievedChunk] = []
    if not results.get("documents"):
        return out

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, dist in zip(docs, metas, distances):
        out.append(RetrievedChunk(text=doc, metadata=meta or {}, distance=float(dist)))
    return out


# ---------------------------------------------------------------------------
# Generation: combina retrieved chunks + query e genera risposta via LLM
# ---------------------------------------------------------------------------

def build_rag_prompt(query: str, retrieved: list[RetrievedChunk], language: str = "italiano") -> str:
    """Costruisce il prompt user da passare al LLM."""
    if not retrieved:
        return (
            f"L'utente ha chiesto: {query}\n\n"
            f"Non ho trovato informazioni nei documenti del corso. "
            f"Rispondi che non hai trovato riferimenti rilevanti, in {language}."
        )

    context_parts: list[str] = []
    for i, rc in enumerate(retrieved, 1):
        meta = rc.metadata
        ref = f"[{meta.get('modulo', '?')} / {meta.get('sottomodulo', '?')} / {meta.get('item', '?')}]"
        context_parts.append(f"=== Frammento {i} {ref} ===\n{rc.text}")

    context = "\n\n".join(context_parts)
    return (
        f"Rispondi alla domanda dell'utente usando ESCLUSIVAMENTE i frammenti di testo qui sotto, "
        f"estratti dai materiali del corso. Se l'informazione non è presente nei frammenti, "
        f"dillo esplicitamente. Cita i frammenti rilevanti tra parentesi quadre. "
        f"Rispondi in {language}.\n\n"
        f"--- FRAMMENTI ---\n{context}\n--- FINE FRAMMENTI ---\n\n"
        f"Domanda: {query}"
    )


def answer_with_rag(
    outputs_root: Path,
    corso: str,
    query: str,
    llm_model: str = "qwen2.5:14b",
    top_k: int = 5,
    language: str = "italiano",
) -> dict:
    """Pipeline completa: query -> retrieval -> generation. Restituisce risposta + sorgenti."""
    retrieved = retrieve(outputs_root, corso, query, top_k=top_k)

    user_prompt = build_rag_prompt(query, retrieved, language=language)
    system_prompt = (
        f"Sei un assistente didattico. Rispondi solo basandoti sui frammenti forniti. "
        f"Se non trovi risposta nei frammenti, dichiaralo. Rispondi in {language}."
    )

    response = ollama.chat(
        model=llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0.2},
    )

    return {
        "answer": response["message"]["content"],
        "retrieved": retrieved,
        "n_retrieved": len(retrieved),
    }
