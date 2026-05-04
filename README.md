# 📚 StudyBuddy

Local-first GenAI study assistant. Trasforma **video, audio, testi, PDF e HTML** in materiale di studio strutturato (riassunti, flashcard, glossari, mappe concettuali, quiz) e ti permette di **chiedere al corso in linguaggio naturale** grazie a un sistema RAG locale.

Tutto privato, tutto in locale. Zero API esterne.

---

## ✨ Cosa fa

| Cosa genera | Output |
|---|---|
| 📝 Riassunti strutturati | Markdown |
| 🗂️ Flashcard Q&A | JSON + CSV per Anki |
| 📖 Glossari | Markdown |
| ❓ Domande aperte | Markdown |
| 🧠 Mappe concettuali | Mermaid (renderizzato inline) |
| 🎯 Quiz MCQ | JSON + interattivo con scoring |

| Modalità | Cosa fa |
|---|---|
| 🏠 **Home** | Dashboard con stats, ripasso di oggi, elaborati recenti |
| 🆕 **Nuovo elaborato** | Upload manuale per singole lezioni |
| 📁 **Cartella inputs** | Batch automatico della struttura `inputs/` con ETA stimata |
| 📚 **Biblioteca** | Navigazione corso → modulo → sottomodulo |
| 🔎 **Cerca** | Ricerca full-text con snippet |
| 🔗 **Cross-reference** | Concetti che ricorrono tra moduli |
| 💬 **Chiedi al corso** | RAG: domande in linguaggio naturale con citazione delle fonti |
| 🎴 **Ripasso** | Spaced repetition integrato (algoritmo SM-2) |
| 📝 **Export Obsidian** | Vault con wikilinks + MOC |
| 💪 **Anki esterno** | (Opzionale) sync con Anki desktop |

---

## 🏗️ Stack tecnico

- **LLM locale**: [Ollama](https://ollama.com/) (qwen2.5:14b consigliato)
- **Embedding**: nomic-embed-text via Ollama
- **Vector database**: [ChromaDB](https://www.trychroma.com/) (persistente, file-based, locale)
- **Trascrizione audio/video**: faster-whisper su GPU (CUDA)
- **UI**: Streamlit con tema dark + accenti viola
- **Architettura**: modulare (`core/llm.py`, `core/transcribe.py`, `core/library.py`, `core/review.py`, `core/rag.py`, `core/obsidian.py`, ecc.)

---

## 📂 Come organizzare le cartelle (IMPORTANTE)

**Regola d'oro**: i primi 3 livelli di `inputs/` diventano automaticamente **Corso / Modulo / Sottomodulo**.

```
inputs/
└── PL-300/                              ← Livello 1: CORSO
    ├── 01 Prepare the data/              ← Livello 2: MODULO
    │   ├── 01 Identify sources/          ← Livello 3: SOTTOMODULO
    │   │   ├── 01_intro.txt              ← file da elaborare
    │   │   ├── 02_connect_source.txt
    │   │   └── study_guide.pdf
    │   ├── 02 Clean data/
    │   │   └── …
    │   └── 03 Transform and load/
    │       └── …
    └── 02 Model the data/
        ├── 01 Design data model/
        ├── 02 Develop data model/
        └── 03 Create measures with DAX/
```

Produce in `outputs/` la stessa gerarchia speculare con tutti i materiali generati.

### Formati supportati in input

- **Testo**: `.txt`, `.md`, `.markdown`
- **Documenti**: `.pdf` (solo testuali, no OCR), `.html`, `.htm`
- **Audio/Video**: `.mp4`, `.mkv`, `.webm`, `.mov`, `.avi`, `.m4a`, `.mp3`, `.wav`, `.flac`

### Tip: salta la trascrizione se hai già i .txt

Se i tuoi video hanno già un file `.txt` (o `.md`) con lo stesso nome base nella stessa cartella, attiva il toggle **⚡ Salta trascrizione video** in sidebar Whisper. L'app userà automaticamente il testo invece di trascrivere il video, risparmiando GPU e tempo.

---

## 🐳 Setup con Docker (consigliato)

Il modo più pulito per far girare StudyBuddy: due container che si parlano (app + Ollama), con persistenza dei modelli e supporto GPU NVIDIA.

### Prerequisiti

- Docker + Docker Compose
- (Opzionale ma consigliato) GPU NVIDIA con [NVIDIA Container Toolkit](https://github.com/NVIDIA/nvidia-container-toolkit)

### Avvio

```bash
git clone https://github.com/Federico-Ordonselli/studybuddy.git
cd studybuddy
docker compose up -d --build
```

Scarica un modello LLM nel container Ollama:

```bash
docker exec -it studybuddy-ollama ollama pull qwen2.5:14b
docker exec -it studybuddy-ollama ollama pull nomic-embed-text
```

Apri il browser su `http://localhost:8501` e sei pronto.

### Comandi utili

```bash
# Vedi i log dei container
docker compose logs -f

# Stoppa tutto
docker compose down

# Riavvia dopo modifiche al codice
docker compose up -d --build
```

### Note Docker

- Il container Ollama è esposto sulla porta `11435` lato host (per evitare conflitti con un Ollama nativo eventualmente in esecuzione sulla 11434).
- I modelli Ollama vivono nel volume Docker `studybuddy-ollama-data` e sopravvivono ai riavvii.
- Le cartelle `inputs/` e `outputs/` sono mappate come bind mount: i file restano sul tuo host.

---

## 🐍 Setup nativo (alternativo)

Se preferisci non usare Docker:

### 1. Ollama + modelli
```bash
# Arch Linux
yay -S ollama-cuda
sudo systemctl enable --now ollama
ollama pull qwen2.5:14b      # generazione
ollama pull nomic-embed-text # embedding per RAG
```

### 2. FFmpeg (per audio/video)
```bash
sudo pacman -S ffmpeg
```

### 3. Ambiente Python
```bash
python -m venv .venv
source .venv/bin/activate.fish  # o activate per bash
pip install -r requirements.txt
```

### 4. CUDA (per Whisper su GPU)
```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

### 5. Avvio
```bash
./run.fish
```

---

## 💬 Come funziona il RAG

La modalità "Chiedi al corso" implementa una pipeline RAG (Retrieval-Augmented Generation) completa, tutta locale:

1. **Indicizzazione** (manuale, una volta per corso):
   - Scansiona `outputs/<corso>/`
   - Estrae chunk da `summary.md` e `transcript.txt`
   - Chunking adattivo con overlap (1500 char, 150 di overlap)
   - Genera embedding con `nomic-embed-text` via Ollama
   - Salva in ChromaDB sotto `outputs/.rag/<corso>/` (metrica cosine)

2. **Query** (real-time, ad ogni domanda):
   - Embedding della domanda
   - Retrieval top-k (default 5) chunk più simili
   - Prompt construction con context grounding e citazioni
   - Generazione risposta via LLM Ollama
   - UI mostra risposta + frammenti espandibili con similarity score e metadata (modulo / sottomodulo / item)

L'indice è per-corso e persistente. Ogni corso ha la sua collection ChromaDB indipendente.

---

## 🎯 Workflow consigliato

1. Organizza file in `inputs/` con la struttura 3-livelli
2. Apri l'app, vai in **📁 Cartella inputs** → vedi anteprima → Elabora
3. Quando il batch è completo, vai in **💬 Chiedi al corso** → click **📚 Indicizza** per il corso
4. **🎴 Ripasso → Gestione → Sincronizza** per importare le flashcard nel ripasso
5. Studia in **🎴 Ripasso** ogni giorno, consulta in **📚 Biblioteca**
6. Usa **💬 Chiedi al corso** per domande mirate, **🔎 Cerca** per recupero veloce
7. Quando vuoi una knowledge base navigabile → **📝 Export Obsidian**

---

## 🎨 Tema

Dark minimal con accenti viola. File: `.streamlit/config.toml`. CSS custom in `core/ui.py`.

Puoi cambiare colori modificando queste variabili in `config.toml`:
```toml
primaryColor = "#a78bfa"          # viola accento
backgroundColor = "#0f0f14"       # sfondo principale
secondaryBackgroundColor = "#1a1a24"
textColor = "#e5e7eb"
```

---

## 🛠️ Struttura progetto

```
studybuddy/
├── app.py                  # UI principale (Streamlit)
├── run.fish                # Wrapper avvio nativo con CUDA
├── Dockerfile              # Container app
├── docker-compose.yml      # Orchestrazione app + Ollama
├── .dockerignore
├── .gitignore
├── requirements.txt
├── .streamlit/
│   └── config.toml         # Tema
└── core/
    ├── ui.py               # CSS + componenti UI
    ├── llm.py              # Client Ollama
    ├── transcribe.py       # Whisper (faster-whisper)
    ├── readers.py          # PDF, HTML, scan inputs, companion text
    ├── processor.py        # Orchestrazione elaborazione
    ├── library.py          # Biblioteca + search + xref
    ├── review.py           # Spaced repetition SM-2
    ├── rag.py              # RAG pipeline (ChromaDB + embedding)
    ├── obsidian.py         # Export vault
    └── anki.py             # AnkiConnect (legacy)
```

`inputs/` e `outputs/` sono creati al primo utilizzo, non versionati.

---

## 🐛 Troubleshooting

- **Ollama non raggiungibile** → `sudo systemctl start ollama` (nativo) o `docker compose start ollama` (Docker)
- **Mindmap rotta / MCQ senza opzioni** → usa `qwen2.5:14b` (i modelli 7-8B sono meno affidabili col JSON)
- **PDF vuoto** → PDF scansionato senza OCR. Servirebbe `ocrmypdf` (non incluso)
- **CUDA OOM su Whisper** → `compute_type=int8_float16` o modello `small`
- **RAG: similarity 0.00 ovunque** → reindicizza il corso. Se persiste, verifica che ChromaDB sia stato creato con metrica `cosine` (vedi `core/rag.py`)
- **DNS error nel container Docker** → vedi `docker-compose.yml` per le righe `dns: [8.8.8.8, 1.1.1.1]`

---

## 🏗️ Hardware consigliato

Setup testato (RTX 4080 Super 16 GB, Ryzen 7 9700X, 32 GB DDR5, Arch Linux):
- Whisper `medium` float16 → ~4 GB VRAM
- Qwen 2.5 14B → ~9 GB VRAM
- nomic-embed-text → ~300 MB VRAM
- Totale a regime: ~13 GB con margine

Funziona anche su hardware meno potente, ma:
- Su GPU < 12 GB: usa `llama3.1:8b` invece di `qwen2.5:14b`
- Solo CPU: tutto funziona, ma molto più lento (specialmente Whisper)

---

## 📝 Licenza

MIT — vedi [LICENSE](LICENSE).
