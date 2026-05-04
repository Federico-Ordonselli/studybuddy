# 📚 StudyBuddy

App locale per trasformare **video, audio, testi, PDF e HTML** in materiale di studio strutturato.
Dark UI, accenti viola, font Inter.

## ✨ Funzionalità

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
| 📁 **Cartella inputs** | Batch automatico della struttura `inputs/` |
| 📚 **Biblioteca** | Navigazione corso → modulo → sottomodulo |
| 🔎 **Cerca** | Ricerca full-text con snippet |
| 🔗 **Cross-reference** | Concetti che ricorrono tra moduli |
| 🎴 **Ripasso** | Spaced repetition integrato (SM-2) |
| 📝 **Export Obsidian** | Vault con wikilinks + MOC |
| 💪 **Anki esterno** | (Opzionale) sync con Anki desktop |

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
    ├── 02 Model the data/
    │   ├── 01 Design data model/
    │   ├── 02 Develop data model/
    │   ├── 03 Create measures with DAX/
    │   └── 04 Optimize performance/
    ├── 03 Visualize and analyze/
    │   └── …
    └── 04 Deploy and maintain/
        └── …
```

Produce in `outputs/` la stessa gerarchia speculare con tutti i materiali generati.

**Setup rapido per il PL-300** (copia e incolla in terminale dal tuo `StudBud/`):

```fish
mkdir -p inputs/PL-300/{"01 Prepare the data","02 Model the data","03 Visualize and analyze","04 Deploy and maintain"}
mkdir -p inputs/PL-300/"01 Prepare the data"/{"01 Identify sources","02 Clean data","03 Transform and load"}
mkdir -p inputs/PL-300/"02 Model the data"/{"01 Design model","02 Develop model","03 Create DAX measures","04 Optimize performance"}
mkdir -p inputs/PL-300/"03 Visualize and analyze"/{"01 Create reports","02 Enhance reports","03 Identify patterns"}
mkdir -p inputs/PL-300/"04 Deploy and maintain"/{"01 Create dashboards","02 Manage workspaces","03 Manage datasets"}
```

Poi butta i .txt e .pdf nelle cartelle giuste e vai in **📁 Cartella inputs** dall'app.

### Formati supportati in input

- **Testo**: `.txt`, `.md`, `.markdown`
- **Documenti**: `.pdf` (solo testuali, no OCR), `.html`, `.htm`
- **Audio/Video**: `.mp4`, `.mkv`, `.webm`, `.mov`, `.avi`, `.m4a`, `.mp3`, `.wav`, `.flac`

## 🚀 Setup

### 1. Ollama + modelli
```fish
yay -S ollama-cuda
sudo systemctl enable --now ollama
ollama pull qwen2.5:14b   # consigliato
ollama pull llama3.1:8b   # più leggero
```

### 2. FFmpeg (per i media)
```fish
sudo pacman -S ffmpeg
```

### 3. Ambiente Python
```fish
python -m venv .venv
source .venv/bin/activate.fish
pip install -r requirements.txt
```

### 4. CUDA (per Whisper GPU)
```fish
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

## ▶️ Avvio

```fish
./run.fish
```

Oppure doppio click sull'icona `StudyBuddy.desktop` se l'hai creata.

## 🎯 Workflow consigliato

1. Organizza file in `inputs/` con la struttura 3-livelli
2. Apri l'app, vai in **📁 Cartella inputs** → vedi anteprima → Elabora
3. **🎴 Ripasso → Gestione → Sincronizza** per importare le flashcard nel ripasso
4. Studia in **🎴 Ripasso** ogni giorno, consulta in **📚 Biblioteca**
5. Usa **🔎 Cerca** per recuperare concetti al volo
6. Quando vuoi una knowledge base navigabile → **📝 Export Obsidian**

## 🎨 Tema

Dark minimal con accenti viola. File: `.streamlit/config.toml`. CSS custom in `core/ui.py`.

Puoi cambiare colori modificando queste variabili in `config.toml`:
```toml
primaryColor = "#a78bfa"          # viola accento
backgroundColor = "#0f0f14"       # sfondo principale
secondaryBackgroundColor = "#1a1a24"
textColor = "#e5e7eb"
```

## 🛠️ Struttura progetto

```
studybuddy/
├── app.py                  # UI principale
├── run.fish                # Wrapper avvio con CUDA
├── requirements.txt
├── .streamlit/
│   └── config.toml         # Tema
├── core/
│   ├── ui.py               # CSS + componenti UI
│   ├── llm.py              # Ollama client
│   ├── transcribe.py       # Whisper
│   ├── readers.py          # PDF, HTML, scan inputs
│   ├── processor.py        # Orchestrazione
│   ├── library.py          # Biblioteca + search + xref
│   ├── review.py           # Ripasso SM-2
│   ├── obsidian.py         # Export vault
│   └── anki.py             # AnkiConnect (legacy)
├── inputs/                 # ← I tuoi file di input
└── outputs/                # ← Generato automaticamente
    └── .review_state.json  # Stato ripasso
```

## 🐛 Troubleshooting

- **Ollama non raggiungibile** → `sudo systemctl start ollama`
- **Mindmap rotta / MCQ senza opzioni** → usa `qwen2.5:14b` (i modelli 7-8B sono meno affidabili col JSON)
- **PDF vuoto** → PDF scansionato senza OCR. Servirebbe `ocrmypdf` (non incluso).
- **CUDA OOM su Whisper** → `compute_type=int8_float16` o modello `small`

## 🏗️ Hardware consigliato

Setup testato (RTX 4080 Super 16 GB, Ryzen 7 9700X, 32 GB DDR5):
- Whisper `medium` float16 → ~4 GB VRAM
- Qwen 2.5 14B → ~9 GB VRAM
- Totale a regime: ~13 GB con margine
