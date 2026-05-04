"""StudyBuddy — App locale per trasformare video/testi/pdf/html in materiale di studio."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.library import (
    build_cross_references,
    build_path,
    dashboard_stats,
    item_already_processed,
    list_corsi,
    list_items,
    list_moduli,
    list_sottomoduli,
    load_item,
    sanitize,
    search_library,
)
from core.llm import LLMClient, list_ollama_models
from core.obsidian import export_vault
from core.processor import process_file, process_group
from core.readers import (
    HTML_EXTS,
    PDF_EXTS,
    TEXT_EXTS,
    VIDEO_EXTS,
    InputFile,
    group_by_folder,
    read_html,
    read_pdf,
    read_text,
    scan_inputs,
)
from core.transcribe import Transcriber
from core.ui import badge, card, hero, inject_css, section

# ---------- Config ----------
st.set_page_config(page_title="StudyBuddy", page_icon="📚", layout="wide")
inject_css()

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = Path("uploads_tmp")
UPLOAD_DIR.mkdir(exist_ok=True)
INPUTS_DIR = Path("inputs")
INPUTS_DIR.mkdir(exist_ok=True)
OBSIDIAN_EXPORT_DIR = Path("obsidian_vault")

# ---------- Session state ----------
if "last_results" not in st.session_state:
    st.session_state.last_results = {}

# ---------- Helpers ----------
def save_result(dir_path: Path, result: dict, text: str | None = None) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    if text is not None:
        (dir_path / "transcript.txt").write_text(text, encoding="utf-8")
    if "summary" in result:
        (dir_path / "summary.md").write_text(result["summary"], encoding="utf-8")
    if "flashcards" in result:
        (dir_path / "flashcards.json").write_text(
            json.dumps(result["flashcards"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        df = pd.DataFrame(result["flashcards"])
        if not df.empty:
            df.to_csv(dir_path / "flashcards_anki.csv", index=False, header=False, sep=";")
    if "glossary" in result:
        (dir_path / "glossary.md").write_text(result["glossary"], encoding="utf-8")
    if "questions" in result:
        (dir_path / "questions.md").write_text(result["questions"], encoding="utf-8")
    if "mindmap" in result:
        (dir_path / "mindmap.md").write_text(
            f"```mermaid\n{result['mindmap']}\n```", encoding="utf-8"
        )
    if "mcq" in result:
        (dir_path / "mcq.json").write_text(
            json.dumps(result["mcq"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def read_input_file(inp: InputFile, transcriber_getter) -> str:
    if inp.kind == "text":
        return read_text(inp.path)
    if inp.kind == "pdf":
        return read_pdf(inp.path)
    if inp.kind == "html":
        return read_html(inp.path)
    if inp.kind == "media":
        t = transcriber_getter()
        return t.transcribe(str(inp.path))
    raise ValueError(f"Tipo non gestito: {inp.kind}")


def render_result(r: dict, stem: str, key_prefix: str = "") -> None:
    """Mostra un risultato nei tab standard."""
    tabs = st.tabs(["📝 Riassunto", "🗂️ Flashcard", "📖 Glossario", "❓ Domande", "🧠 Mindmap", "🎯 Quiz MCQ", "📄 Testo"])

    with tabs[0]:
        if r.get("summary"):
            st.markdown(r["summary"])
            st.download_button("⬇️ Scarica riassunto (.md)", r["summary"],
                file_name=f"{stem}_summary.md", key=f"{key_prefix}_dl_sum")
        else:
            st.info("Nessun riassunto.")

    with tabs[1]:
        if r.get("flashcards"):
            df = pd.DataFrame(r["flashcards"])
            st.dataframe(df, use_container_width=True)
            csv_anki = df.to_csv(index=False, header=False, sep=";").encode("utf-8")
            st.download_button("⬇️ Per Anki (.csv)", csv_anki,
                file_name=f"{stem}_flashcards.csv", mime="text/csv",
                key=f"{key_prefix}_dl_fc")
        else:
            st.info("Nessuna flashcard.")

    with tabs[2]:
        if r.get("glossary"):
            st.markdown(r["glossary"])
        else:
            st.info("Nessun glossario.")

    with tabs[3]:
        if r.get("questions"):
            st.markdown(r["questions"])
        else:
            st.info("Nessuna domanda.")

    with tabs[4]:
        if r.get("mindmap"):
            mindmap_code = r["mindmap"]
            html = f"""
            <div style="background:white;border-radius:10px;padding:1rem;">
              <div class="mermaid">{mindmap_code}</div>
            </div>
            <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
            <script>mermaid.initialize({{startOnLoad:true, theme:'default'}});</script>
            """
            st.components.v1.html(html, height=600, scrolling=True)
            with st.expander("Codice Mermaid"):
                st.code(mindmap_code, language="text")
            st.download_button("⬇️ Scarica mindmap (.md)",
                f"```mermaid\n{mindmap_code}\n```",
                file_name=f"{stem}_mindmap.md", key=f"{key_prefix}_dl_mm")
        else:
            st.info("Nessuna mappa concettuale.")

    with tabs[5]:
        render_mcq(r.get("mcq", []), key_prefix=key_prefix)

    with tabs[6]:
        text = r.get("_text", "")
        if text:
            st.text_area("Testo", text, height=400, key=f"{key_prefix}_txt")
        else:
            st.info("Testo non disponibile.")


def render_mcq(mcq_list: list[dict], key_prefix: str) -> None:
    if not mcq_list:
        st.info("Nessun quiz MCQ disponibile.")
        return

    col_a, _ = st.columns([1, 3])
    if col_a.button("🔄 Reset quiz", key=f"{key_prefix}_reset"):
        keys_to_clear = [k for k in st.session_state.keys() if k.startswith(f"mcq_{key_prefix}_")]
        for k in keys_to_clear:
            del st.session_state[k]
        st.rerun()

    submit_key = f"mcq_{key_prefix}_submitted"
    submitted = st.session_state.get(submit_key, False)

    with st.form(key=f"mcq_form_{key_prefix}"):
        for i, q in enumerate(mcq_list):
            st.markdown(f"**{i + 1}. {q['domanda']}**")
            if q.get("topic"):
                st.caption(f"🏷️ {q['topic']}")
            st.radio(
                f"Domanda {i + 1}",
                options=range(len(q["opzioni"])),
                format_func=lambda x, opts=q["opzioni"]: f"{chr(65 + x)}. {opts[x]}",
                index=None,
                key=f"mcq_{key_prefix}_q{i}",
                label_visibility="collapsed",
            )
            st.divider()
        submit = st.form_submit_button("✅ Correggi", type="primary")

    if submit:
        st.session_state[submit_key] = True
        submitted = True

    if submitted:
        correct_count = 0
        wrong_topics: dict[str, int] = {}
        for i, q in enumerate(mcq_list):
            user_ans = st.session_state.get(f"mcq_{key_prefix}_q{i}")
            correct = q["corretta"]
            is_correct = user_ans == correct
            if is_correct:
                correct_count += 1
                st.success(f"**{i + 1}.** ✅ Corretta! ({chr(65 + correct)}: {q['opzioni'][correct]})")
            else:
                topic = q.get("topic", "Generale")
                wrong_topics[topic] = wrong_topics.get(topic, 0) + 1
                user_txt = (f"{chr(65 + user_ans)}: {q['opzioni'][user_ans]}"
                    if user_ans is not None else "(non risposta)")
                st.error(f"**{i + 1}.** ❌ Tua: {user_txt}  \n**Corretta**: {chr(65 + correct)}: {q['opzioni'][correct]}")
            if q.get("spiegazione"):
                with st.expander("💡 Spiegazione"):
                    st.write(q["spiegazione"])

        st.divider()
        total = len(mcq_list)
        score_pct = 100 * correct_count / total if total else 0
        c1, c2 = st.columns(2)
        c1.metric("🎯 Punteggio", f"{correct_count}/{total}", f"{score_pct:.0f}%")

        if wrong_topics:
            st.markdown("### 🔍 Topic da ripassare")
            for topic, count in sorted(wrong_topics.items(), key=lambda x: -x[1]):
                st.markdown(badge(f"{topic} · {count} errori", "warn"), unsafe_allow_html=True)


# ===========================================================================
# SIDEBAR
# ===========================================================================
st.sidebar.markdown("# 📚 StudyBuddy")
st.sidebar.caption("Local study assistant")
st.sidebar.markdown("---")

MODES = [
    ("🏠 Home", "home"),
    ("🆕 Nuovo elaborato", "new"),
    ("📁 Cartella inputs", "inputs"),
    ("📚 Biblioteca", "library"),
    ("🔎 Cerca", "search"),
    ("🔗 Cross-reference", "xref"),
    ("🎴 Ripasso", "review"),
    ("📝 Export Obsidian", "obsidian"),
    ("💪 Anki esterno", "anki_ext"),
]

if "mode_key" not in st.session_state:
    st.session_state.mode_key = "home"

mode_labels = [m[0] for m in MODES]
current_idx = next((i for i, (_, k) in enumerate(MODES) if k == st.session_state.mode_key), 0)
selected_label = st.sidebar.radio("Navigazione", mode_labels, index=current_idx, label_visibility="collapsed")
st.session_state.mode_key = next(k for lbl, k in MODES if lbl == selected_label)
mode_key = st.session_state.mode_key

st.sidebar.markdown("---")

# ---------- Sidebar config helpers ----------
def llm_sidebar_config() -> dict:
    with st.sidebar.expander("🤖 LLM (Ollama)", expanded=True):
        try:
            available_models = list_ollama_models()
        except Exception as e:  # noqa: BLE001
            available_models = []
            st.error(f"Ollama non raggiungibile: {e}")

        default_model = ("qwen2.5:14b" if "qwen2.5:14b" in available_models
            else ("llama3.1:8b" if "llama3.1:8b" in available_models
                else (available_models[0] if available_models else "llama3.1:8b")))
        llm_model = st.selectbox("Modello", available_models or ["llama3.1:8b"],
            index=(available_models.index(default_model) if default_model in available_models else 0))
        llm_language = st.selectbox("Lingua output", ["english", "italiano"], index=0)
        context_window = st.slider("Context window", 2048, 32768, 8192, step=1024)
    return {"model": llm_model, "language": llm_language, "num_ctx": context_window}


def whisper_sidebar_config() -> dict:
    with st.sidebar.expander("🎙️ Whisper (per media)", expanded=False):
        whisper_size = st.selectbox("Modello Whisper", ["tiny", "base", "small", "medium", "large-v3"], index=3)
        whisper_device = st.selectbox("Device", ["cuda", "cpu"], index=0)
        whisper_compute = st.selectbox("Compute type", ["float16", "int8_float16", "int8", "float32"], index=0)
        whisper_language = st.text_input("Lingua media", value="en")
    return {"size": whisper_size, "device": whisper_device, "compute": whisper_compute, "language": whisper_language}


def generation_sidebar_config() -> dict:
    with st.sidebar.expander("✨ Cosa generare", expanded=True):
        gen_summary = st.checkbox("📝 Riassunto", value=True)
        gen_flashcards = st.checkbox("🗂️ Flashcard", value=True)
        n_flashcards = st.slider("N° flashcard", 5, 40, 15)
        gen_glossary = st.checkbox("📖 Glossario", value=True)
        gen_questions = st.checkbox("❓ Domande aperte", value=True)
        n_questions = st.slider("N° domande", 3, 20, 8)
        gen_mindmap = st.checkbox("🧠 Mappa concettuale", value=True)
        gen_mcq = st.checkbox("🎯 Quiz MCQ", value=True)
        n_mcq = st.slider("N° MCQ", 5, 30, 12)
    return {
        "summary": gen_summary, "flashcards": gen_flashcards, "n_fc": n_flashcards,
        "glossary": gen_glossary, "questions": gen_questions, "n_q": n_questions,
        "mindmap": gen_mindmap, "mcq": gen_mcq, "n_mcq": n_mcq,
    }


# ===========================================================================
# HOME
# ===========================================================================
if mode_key == "home":
    stats = dashboard_stats(OUTPUT_DIR)

    # Stats ripasso (se disponibili)
    review_stats = None
    review_state_path = OUTPUT_DIR / ".review_state.json"
    if review_state_path.exists():
        try:
            from core.review import get_stats as _rev_stats, load_state
            review_state = load_state(OUTPUT_DIR)
            review_stats = _rev_stats(review_state)
        except Exception:  # noqa: BLE001
            review_stats = None

    hero(
        "📚 StudyBuddy",
        "Il tuo assistente di studio locale — trasforma lezioni in materiale organizzato, pronto da ripassare."
    )

    # Metriche veloci
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📚 Corsi", stats["n_corsi"])
    c2.metric("📂 Moduli", stats["n_moduli"])
    c3.metric("📑 Sottomoduli", stats["n_sottomoduli"])
    c4.metric("✨ Elaborati", stats["n_items"])

    if review_stats:
        st.markdown("<br>", unsafe_allow_html=True)
        section("Ripasso di oggi")
        c1, c2, c3 = st.columns(3)
        due_badge = badge(f"{review_stats['due']} scadute", "warn" if review_stats["due"] > 0 else "success")
        new_badge = badge(f"{review_stats['new']} nuove", "purple")
        c1.metric("🎴 Da ripassare oggi", review_stats["due"] + review_stats["new"])
        c2.metric("💚 Mature", review_stats["mature"])
        c3.metric("🌱 In apprendimento", review_stats["learning"])
        if review_stats["due"] + review_stats["new"] > 0:
            if st.button("🎴 Inizia ripasso di oggi", type="primary"):
                st.session_state.mode_key = "review"
                st.rerun()

    # Recenti
    if stats["recent"]:
        st.markdown("<br>", unsafe_allow_html=True)
        section("Elaborati recenti")
        for mtime, corso, modulo, sub, item in stats["recent"]:
            ts = datetime.fromtimestamp(mtime).strftime("%d %b %Y · %H:%M")
            title = item if item != "(contenuto diretto)" else f"📑 {sub} [aggregato]"
            subtitle = f"{corso} › {modulo} › {sub} · {ts}"
            badges_list = [(corso, "purple")]
            card(title=title, subtitle=subtitle, body="", badges=badges_list)

    # Suggerimenti
    if stats["n_items"] == 0:
        st.markdown("<br>", unsafe_allow_html=True)
        section("Come iniziare")
        with st.container(border=True):
            st.markdown("""
**Benvenuto!** Ecco da dove partire:

1. **Organizza i file** in `inputs/` con la struttura `inputs/<Corso>/<Modulo>/<Sottomodulo>/…`
   (es: `inputs/PL-300/02 Model the data/03 Create measures with DAX/lezione_01.txt`)
2. **Vai in 📁 Cartella inputs**, vedi l'anteprima e clicca Elabora
3. Una volta generato il materiale, sincronizza con **🎴 Ripasso → Gestione** per importarlo nel sistema di ripasso
4. Studia in **🎴 Ripasso** o esplora in **📚 Biblioteca**
            """)

    st.markdown("<br>", unsafe_allow_html=True)
    section("Azioni rapide")
    qa_cols = st.columns(4)
    actions = [
        ("🆕 Nuovo", "new"),
        ("📁 Elabora cartelle", "inputs"),
        ("📚 Biblioteca", "library"),
        ("🎴 Ripassa", "review"),
    ]
    for col, (label, key) in zip(qa_cols, actions):
        if col.button(label, use_container_width=True):
            st.session_state.mode_key = key
            st.rerun()


# ===========================================================================
# MODALITÀ: NUOVO ELABORATO
# ===========================================================================
elif mode_key == "new":
    section("Organizzazione")
    cc1, cc2, cc3 = st.sidebar.columns(1)[0:1] * 3 if False else (st.sidebar.container(),) * 3
    with st.sidebar:
        section("Destinazione output")
        corso = st.text_input("Corso", placeholder="PL-300")
        modulo = st.text_input("Modulo", placeholder="01 Get Started")
        sottomodulo = st.text_input("Sottomodulo", placeholder="01 Intro")

    llm_cfg = llm_sidebar_config()
    whisper_cfg = whisper_sidebar_config()
    gen = generation_sidebar_config()

    with st.sidebar.expander("⚙️ Modalità batch", expanded=True):
        per_file = st.checkbox("Singolarmente", value=True)
        aggregate = st.checkbox("Aggregato del sottomodulo", value=False)

    hero("🆕 Nuovo elaborato", "Upload manuale per prove veloci o singole lezioni.")

    preview = build_path(OUTPUT_DIR, corso or "_", modulo or "_", sottomodulo or "_")
    st.caption(f"📁 Output → `{preview}/`")

    uploaded = st.file_uploader(
        "Carica file (video, audio, txt, md, pdf, html)",
        type=[e.lstrip(".") for e in (VIDEO_EXTS | TEXT_EXTS | PDF_EXTS | HTML_EXTS)],
        accept_multiple_files=True,
    )

    c1, c2 = st.columns([3, 1])
    run = c1.button("🚀 Elabora", type="primary", use_container_width=True, disabled=not uploaded)
    if c2.button("🗑️ Pulisci", use_container_width=True):
        st.session_state.last_results = {}
        st.rerun()

    if run and uploaded:
        llm = LLMClient(**llm_cfg)
        transcriber_ref: list[Transcriber | None] = [None]
        def get_transcriber():
            if transcriber_ref[0] is None:
                transcriber_ref[0] = Transcriber(
                    model_size=whisper_cfg["size"],
                    device=whisper_cfg["device"],
                    compute_type=whisper_cfg["compute"],
                )
            return transcriber_ref[0]

        progress = st.progress(0.0)
        status = st.empty()
        file_texts: list[tuple[str, str]] = []

        for i, f in enumerate(uploaded):
            status.info(f"📖 Leggo {f.name} ({i + 1}/{len(uploaded)})…")
            save_path = UPLOAD_DIR / f.name
            save_path.write_bytes(f.getbuffer())
            ext = save_path.suffix.lower()
            try:
                if ext in VIDEO_EXTS:
                    status.info(f"🎙️ Trascrivo {f.name}…")
                    text = get_transcriber().transcribe(str(save_path), language=whisper_cfg["language"] or None)
                elif ext in TEXT_EXTS:
                    text = read_text(save_path)
                elif ext in PDF_EXTS:
                    text = read_pdf(save_path)
                elif ext in HTML_EXTS:
                    text = read_html(save_path)
                else:
                    st.warning(f"⚠️ Non supportato: {f.name}")
                    continue
                file_texts.append((f.name, text))
            except Exception as e:  # noqa: BLE001
                st.error(f"❌ Errore su {f.name}: {e}")

        total_steps = (len(file_texts) if per_file else 0) + (1 if aggregate else 0)
        total_steps = max(total_steps, 1)
        step = 0

        if per_file:
            for name, text in file_texts:
                step += 1
                stem = Path(name).stem
                try:
                    result = process_file(
                        text=text, llm=llm,
                        do_summary=gen["summary"],
                        do_flashcards=gen["flashcards"], n_flashcards=gen["n_fc"],
                        do_glossary=gen["glossary"],
                        do_questions=gen["questions"], n_questions=gen["n_q"],
                        do_mindmap=gen["mindmap"],
                        do_mcq=gen["mcq"], n_mcq=gen["n_mcq"],
                        context_label=f"{modulo} / {sottomodulo} / {name}",
                        status_cb=lambda msg, n=name: status.info(f"⚙️ {n}: {msg}"),
                    )
                    result["_text"] = text
                    st.session_state.last_results[name] = result
                    save_result(build_path(OUTPUT_DIR, corso, modulo, sottomodulo, stem), result, text=text)
                except Exception as e:  # noqa: BLE001
                    st.error(f"❌ Errore su {name}: {e}")
                progress.progress(step / total_steps)

        if aggregate and file_texts:
            step += 1
            try:
                result = process_group(
                    files=file_texts, llm=llm,
                    group_label=sottomodulo or modulo or corso or "aggregato",
                    do_summary=gen["summary"],
                    do_flashcards=gen["flashcards"], n_flashcards=int(gen["n_fc"] * 1.5),
                    do_glossary=gen["glossary"],
                    do_questions=gen["questions"], n_questions=int(gen["n_q"] * 1.5),
                    do_mindmap=gen["mindmap"],
                    do_mcq=gen["mcq"], n_mcq=int(gen["n_mcq"] * 1.5),
                    status_cb=lambda msg: status.info(f"⚙️ [aggregato] {msg}"),
                )
                out_dir = build_path(OUTPUT_DIR, corso, modulo, sottomodulo)
                save_result(out_dir, result)
                sources_dir = out_dir / "sources"
                sources_dir.mkdir(parents=True, exist_ok=True)
                for name, text in file_texts:
                    (sources_dir / f"{sanitize(Path(name).stem)}.txt").write_text(text, encoding="utf-8")
                st.session_state.last_results[f"[AGGREGATO] {sottomodulo or 'sottomodulo'}"] = result
            except Exception as e:  # noqa: BLE001
                st.error(f"❌ Errore aggregato: {e}")
            progress.progress(1.0)

        status.success(f"✅ Completato → `{build_path(OUTPUT_DIR, corso, modulo, sottomodulo).resolve()}`")

    if st.session_state.last_results:
        st.divider()
        section("Risultati")
        sel = st.selectbox("Elemento", list(st.session_state.last_results.keys()))
        render_result(st.session_state.last_results[sel], stem=sanitize(sel), key_prefix=sanitize(sel))
    else:
        st.info("⬆️ Carica file e clicca 'Elabora' per iniziare.")


# ===========================================================================
# MODALITÀ: CARTELLA INPUTS
# ===========================================================================
elif mode_key == "inputs":
    llm_cfg = llm_sidebar_config()
    whisper_cfg = whisper_sidebar_config()
    gen = generation_sidebar_config()

    with st.sidebar.expander("⚙️ Batch", expanded=True):
        skip_done = st.checkbox("Salta già elaborati", value=True)
        per_file = st.checkbox("Elabora ogni file", value=True)
        aggregate = st.checkbox("Aggregato sottomodulo", value=True)

    hero("📁 Cartella inputs", "Scansiona la struttura delle tue cartelle e elabora in batch.")

    st.markdown(
        f"Metti i file in `{INPUTS_DIR.resolve()}/` con la struttura "
        f"**inputs/<Corso>/<Modulo>/<Sottomodulo>/file**. "
        f"Esempio: `inputs/PL-300/02 Model the data/03 DAX/lezione_01.txt`"
    )

    inputs = scan_inputs(INPUTS_DIR)
    if not inputs:
        st.warning(f"⚠️ Nessun file trovato in `{INPUTS_DIR}/`. Crea la struttura e ricarica.")
        st.stop()

    by_folder = group_by_folder(inputs)

    c1, c2 = st.columns(2)
    c1.metric("📄 File totali", len(inputs))
    c2.metric("📂 Cartelle", len(by_folder))

    def interpret(folder_rel: Path) -> tuple[str, str, str]:
        parts = folder_rel.parts
        corso = parts[0] if len(parts) > 0 else "_senza_corso"
        modulo = parts[1] if len(parts) > 1 else "_senza_modulo"
        sottomodulo = parts[2] if len(parts) > 2 else "_senza_sottomodulo"
        if len(parts) > 3:
            sottomodulo = "_".join(parts[2:])
        return corso, modulo, sottomodulo

    section("Anteprima struttura rilevata")
    rows = []
    for folder_rel, files in sorted(by_folder.items()):
        c, m, s = interpret(folder_rel)
        done = sum(
            1 for f in files
            if item_already_processed(OUTPUT_DIR, c, m, s, Path(f.path.name).stem)
        )
        rows.append({
            "Corso": c, "Modulo": m, "Sottomodulo": s,
            "File": len(files), "Già fatti": done,
            "Da elaborare": len(files) - (done if skip_done else 0),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    section("Selezione cartelle")
    folder_options = ["[TUTTO]"] + [str(f) for f in sorted(by_folder.keys())]
    selected = st.multiselect("Cartelle da elaborare", folder_options, default=["[TUTTO]"])
    selected_folders = (list(by_folder.keys()) if "[TUTTO]" in selected else [Path(s) for s in selected])

    if st.button("🚀 Elabora cartelle selezionate", type="primary", disabled=not selected_folders, use_container_width=True):
        llm = LLMClient(**llm_cfg)
        transcriber_ref: list[Transcriber | None] = [None]
        def get_transcriber():
            if transcriber_ref[0] is None:
                transcriber_ref[0] = Transcriber(
                    model_size=whisper_cfg["size"],
                    device=whisper_cfg["device"],
                    compute_type=whisper_cfg["compute"],
                )
            return transcriber_ref[0]

        progress = st.progress(0.0)
        status = st.empty()
        done_count = skip_count = err_count = 0

        for fi, folder_rel in enumerate(selected_folders):
            files = by_folder[folder_rel]
            c, m, s = interpret(folder_rel)
            status.info(f"📂 {c} › {m} › {s}")

            file_texts: list[tuple[str, str]] = []
            for inp in files:
                stem = Path(inp.path.name).stem
                if skip_done and per_file and item_already_processed(OUTPUT_DIR, c, m, s, stem):
                    skip_count += 1
                    continue
                try:
                    status.info(f"📖 Leggo: {inp.rel_path}")
                    txt = read_input_file(inp, get_transcriber)
                    file_texts.append((inp.path.name, txt))
                except Exception as e:  # noqa: BLE001
                    st.error(f"❌ Lettura {inp.rel_path}: {e}")
                    err_count += 1

            if per_file:
                for name, text in file_texts:
                    stem = Path(name).stem
                    try:
                        status.info(f"⚙️ Elaboro: {name}")
                        result = process_file(
                            text=text, llm=llm,
                            do_summary=gen["summary"],
                            do_flashcards=gen["flashcards"], n_flashcards=gen["n_fc"],
                            do_glossary=gen["glossary"],
                            do_questions=gen["questions"], n_questions=gen["n_q"],
                            do_mindmap=gen["mindmap"],
                            do_mcq=gen["mcq"], n_mcq=gen["n_mcq"],
                            context_label=f"{m} / {s} / {name}",
                        )
                        save_result(build_path(OUTPUT_DIR, c, m, s, stem), result, text=text)
                        done_count += 1
                    except Exception as e:  # noqa: BLE001
                        st.error(f"❌ {name}: {e}")
                        err_count += 1

            if aggregate and file_texts:
                agg_dir = build_path(OUTPUT_DIR, c, m, s)
                if skip_done and (agg_dir / "summary.md").exists():
                    skip_count += 1
                else:
                    try:
                        status.info(f"⚙️ Aggregato {s}…")
                        result = process_group(
                            files=file_texts, llm=llm,
                            group_label=s or m or c,
                            do_summary=gen["summary"],
                            do_flashcards=gen["flashcards"], n_flashcards=int(gen["n_fc"] * 1.5),
                            do_glossary=gen["glossary"],
                            do_questions=gen["questions"], n_questions=int(gen["n_q"] * 1.5),
                            do_mindmap=gen["mindmap"],
                            do_mcq=gen["mcq"], n_mcq=int(gen["n_mcq"] * 1.5),
                        )
                        save_result(agg_dir, result)
                        sources_dir = agg_dir / "sources"
                        sources_dir.mkdir(parents=True, exist_ok=True)
                        for name, text in file_texts:
                            (sources_dir / f"{sanitize(Path(name).stem)}.txt").write_text(text, encoding="utf-8")
                        done_count += 1
                    except Exception as e:  # noqa: BLE001
                        st.error(f"❌ Aggregato {s}: {e}")
                        err_count += 1

            progress.progress((fi + 1) / len(selected_folders))

        status.success(f"✅ Completato · Elaborati: {done_count} · Saltati: {skip_count} · Errori: {err_count}")


# ===========================================================================
# MODALITÀ: BIBLIOTECA
# ===========================================================================
elif mode_key == "library":
    hero("📚 Biblioteca", f"Tutto il materiale elaborato, navigabile per corso.")
    st.caption(f"📁 Da: `{OUTPUT_DIR.resolve()}/`")

    corsi = list_corsi(OUTPUT_DIR)
    if not corsi:
        st.info("Biblioteca vuota. Elabora qualcosa prima.")
        st.stop()

    c1, c2, c3 = st.columns(3)
    corso = c1.selectbox("Corso", corsi)
    moduli = list_moduli(OUTPUT_DIR, corso)
    modulo = c2.selectbox("Modulo", moduli) if moduli else None
    sottomoduli = list_sottomoduli(OUTPUT_DIR, corso, modulo) if modulo else []
    sottomodulo = c3.selectbox("Sottomodulo", sottomoduli) if sottomoduli else None

    if not sottomodulo:
        st.stop()

    items = list_items(OUTPUT_DIR, corso, modulo, sottomodulo)
    if not items:
        st.warning("Vuoto.")
        st.stop()

    item = st.selectbox("Elemento", items)
    r = load_item(OUTPUT_DIR, corso, modulo, sottomodulo, item)
    if not any(k in r for k in ("summary", "flashcards", "glossary", "questions", "mindmap", "mcq")):
        st.warning("Contenuto non riconosciuto.")
        st.stop()

    render_result(r, stem=sanitize(f"{corso}_{sottomodulo}_{item}"),
        key_prefix=sanitize(f"lib_{corso}_{modulo}_{sottomodulo}_{item}"))


# ===========================================================================
# MODALITÀ: CERCA
# ===========================================================================
elif mode_key == "search":
    hero("🔎 Ricerca full-text", "Cerca in riassunti, glossari, domande e trascrizioni.")

    q = st.text_input("Query", placeholder="es. DAX measures, ETL, data modeling…")
    max_res = st.slider("Massimo risultati", 5, 100, 30)

    if q:
        with st.spinner("🔍 Cerco…"):
            hits = search_library(OUTPUT_DIR, q, max_results=max_res)

        if not hits:
            st.warning(f"Nessun risultato per '{q}'.")
        else:
            st.success(f"🎯 Trovati {len(hits)} risultati.")
            for h in hits:
                with st.container(border=True):
                    header = f"**{h['corso']}** › {h['modulo']} › {h['sottomodulo']} › *{h['item']}*"
                    st.markdown(header)
                    st.markdown(
                        badge(f"📄 {h['file']}", "purple") + " " + badge(f"{h['hits']} hit", "warn"),
                        unsafe_allow_html=True,
                    )
                    st.markdown(h["snippet"])
                    st.caption(h["path"])


# ===========================================================================
# MODALITÀ: CROSS-REFERENCE
# ===========================================================================
elif mode_key == "xref":
    hero("🔗 Cross-reference", "Concetti che compaiono in più moduli / sottomoduli.")

    corsi = list_corsi(OUTPUT_DIR)
    if not corsi:
        st.info("Biblioteca vuota.")
        st.stop()

    corso = st.selectbox("Corso", corsi)
    if st.button("🔍 Analizza cross-reference", type="primary"):
        with st.spinner("Costruisco indice dei termini…"):
            refs = build_cross_references(OUTPUT_DIR, corso)
        if not refs:
            st.info("Nessun termine ricorrente. Assicurati di aver generato i glossari.")
        else:
            st.success(f"🎯 Trovati {len(refs)} concetti ricorrenti.")
            sorted_refs = sorted(refs.items(), key=lambda x: -len(x[1]))
            for term, locations in sorted_refs:
                with st.expander(f"**{term}** — {len(locations)} occorrenze"):
                    for loc in locations:
                        st.markdown(f"- {loc['modulo']} › {loc['sottomodulo']} › *{loc['item']}*")


# ===========================================================================
# MODALITÀ: RIPASSO
# ===========================================================================
elif mode_key == "review":
    from core.review import (
        apply_rating, export_to_csv_anki, get_due_cards, get_stats,
        list_courses_modules, load_state, reset_progress, save_state, sync_from_library,
    )

    hero("🎴 Ripasso", "Spaced repetition integrato — algoritmo SM-2, stato persistente.")

    if "review_state" not in st.session_state:
        st.session_state.review_state = load_state(OUTPUT_DIR)
    if "review_session" not in st.session_state:
        st.session_state.review_session = {
            "queue": [], "idx": 0, "revealed": False,
            "stats": {"again": 0, "hard": 0, "good": 0, "easy": 0},
        }

    state = st.session_state.review_state
    tabs = st.tabs(["📖 Studia", "📊 Statistiche", "⚙️ Gestione"])

    with tabs[0]:
        if not state:
            st.info("ℹ️ Nessuna flashcard. Vai in **⚙️ Gestione → Sincronizza dalla biblioteca**.")
        else:
            courses, mods_by_course = list_courses_modules(state)
            c1, c2, c3 = st.columns([2, 2, 1])
            filter_corso = c1.selectbox("Corso", ["[Tutti]"] + courses, key="rev_filter_corso")
            filter_modulo = "[Tutti]"
            if filter_corso != "[Tutti]":
                mods_list = mods_by_course.get(filter_corso, [])
                filter_modulo = c2.selectbox("Modulo", ["[Tutti]"] + mods_list, key="rev_filter_modulo")
            max_new = c3.number_input("Nuove max", 0, 100, 20, key="rev_max_new")

            sess = st.session_state.review_session

            col_start, col_end = st.columns(2)
            if col_start.button("▶️ Nuova sessione", type="primary", use_container_width=True):
                queue = get_due_cards(
                    state,
                    corso=None if filter_corso == "[Tutti]" else filter_corso,
                    modulo=None if filter_modulo == "[Tutti]" else filter_modulo,
                    max_new_per_session=max_new,
                )
                sess["queue"] = [c.id for c in queue]
                sess["idx"] = 0
                sess["revealed"] = False
                sess["stats"] = {"again": 0, "hard": 0, "good": 0, "easy": 0}
                st.rerun()
            if col_end.button("⏹️ Termina", use_container_width=True):
                sess["queue"] = []
                sess["idx"] = 0
                sess["revealed"] = False
                st.rerun()

            if sess["queue"]:
                total = len(sess["queue"])
                idx = sess["idx"]
                if idx >= total:
                    s = sess["stats"]
                    st.success(f"🎉 Sessione completata! {total} carte ripassate.")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("😵 Again", s["again"])
                    c2.metric("😐 Hard", s["hard"])
                    c3.metric("🙂 Good", s["good"])
                    c4.metric("😎 Easy", s["easy"])
                    save_state(OUTPUT_DIR, state)
                else:
                    card_id = sess["queue"][idx]
                    rcard = state.get(card_id)
                    if rcard is None:
                        sess["idx"] += 1
                        st.rerun()
                    else:
                        st.progress(idx / total, text=f"Carta {idx + 1} di {total}")

                        with st.container(border=True):
                            st.markdown(
                                badge(rcard.corso, "purple") + " " +
                                badge(rcard.modulo, "") + " " +
                                badge(rcard.sottomodulo, ""),
                                unsafe_allow_html=True,
                            )
                            st.caption(f"*{rcard.item}*")
                            st.markdown(f"### ❓ {rcard.front}")

                            if not sess["revealed"]:
                                if st.button("👁️ Mostra risposta", type="primary", use_container_width=True):
                                    sess["revealed"] = True
                                    st.rerun()
                            else:
                                st.divider()
                                st.markdown(f"**💡 Risposta**")
                                st.markdown(rcard.back)
                                st.divider()

                                b1, b2, b3, b4 = st.columns(4)
                                def _rate(r: str) -> None:
                                    apply_rating(rcard, r)
                                    state[card_id] = rcard
                                    save_state(OUTPUT_DIR, state)
                                    sess["stats"][r] += 1
                                    sess["idx"] += 1
                                    sess["revealed"] = False

                                if b1.button("😵 Again", use_container_width=True, key="r_again"):
                                    _rate("again"); st.rerun()
                                if b2.button("😐 Hard", use_container_width=True, key="r_hard"):
                                    _rate("hard"); st.rerun()
                                if b3.button("🙂 Good", use_container_width=True, key="r_good"):
                                    _rate("good"); st.rerun()
                                if b4.button("😎 Easy", use_container_width=True, key="r_easy"):
                                    _rate("easy"); st.rerun()

                                with st.expander("📊 Dettagli carta"):
                                    st.write({
                                        "ease": round(rcard.ease, 2),
                                        "interval_days": rcard.interval,
                                        "reps": rcard.reps,
                                        "lapses": rcard.lapses,
                                        "due": rcard.due or "(nuova)",
                                        "last_review": rcard.last_review or "(mai)",
                                    })
            else:
                stats = get_stats(state)
                c1, c2, c3 = st.columns(3)
                c1.metric("🔴 Da ripassare", stats["due"])
                c2.metric("🌱 Nuove", stats["new"])
                c3.metric("📊 Totale", stats["total"])
                if stats["due"] == 0 and stats["new"] == 0:
                    st.success("🎊 Nulla da ripassare. Torna domani!")
                else:
                    st.info("👆 Clicca 'Nuova sessione' per iniziare.")

    with tabs[1]:
        if not state:
            st.info("Nessuna carta.")
        else:
            stats = get_stats(state)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📊 Totale", stats["total"])
            c2.metric("🌱 Nuove", stats["new"])
            c3.metric("⏳ Apprendimento", stats["learning"])
            c4.metric("💚 Mature", stats["mature"])

            if stats["per_corso"]:
                section("Per corso")
                st.dataframe(
                    pd.DataFrame([{"Corso": k, **v} for k, v in stats["per_corso"].items()]),
                    use_container_width=True, hide_index=True,
                )

            if stats["weak_cards"]:
                section("🎯 Punti deboli (>= 2 lapses)")
                st.dataframe(
                    pd.DataFrame([{
                        "Domanda": c.front[:80] + ("…" if len(c.front) > 80 else ""),
                        "Lapses": c.lapses, "Corso": c.corso,
                        "Sottomodulo": c.sottomodulo, "Ease": round(c.ease, 2),
                    } for c in stats["weak_cards"]]),
                    use_container_width=True, hide_index=True,
                )

                if st.button("🧠 Genera esercizi di rinforzo", type="primary"):
                    weak_text = "\n".join(
                        f"{i+1}. {c.front}\n   Risposta: {c.back}"
                        for i, c in enumerate(stats["weak_cards"])
                    )
                    with st.spinner("🤖 LLM al lavoro…"):
                        llm = LLMClient(model="qwen2.5:14b", language="english", num_ctx=8192)
                        practice = llm.focused_practice(weak_text, n=10)
                    st.markdown(practice)
                    st.download_button("⬇️ Scarica (.md)", practice,
                        file_name="esercizi_rinforzo.md")

    with tabs[2]:
        section("🔄 Sincronizza con biblioteca")
        st.caption("Aggiunge al sistema di ripasso le flashcard nuove dalla biblioteca.")
        if st.button("🔄 Sincronizza", type="primary"):
            with st.spinner("Scansione…"):
                result = sync_from_library(OUTPUT_DIR, state)
            st.success(
                f"✅ Aggiunte **{result['added']}** · Esistenti: {result['existing']} · "
                f"Totale: **{result['total']}**"
            )
            st.session_state.review_state = result["state"]

        st.divider()
        section("💾 Export / Backup")
        if state:
            csv_data = export_to_csv_anki(state)
            st.download_button(
                "⬇️ CSV per Anki", csv_data.encode("utf-8"),
                file_name="studybuddy_cards.csv", mime="text/csv",
            )
            json_data = json.dumps(
                {cid: {
                    "front": c.front, "back": c.back, "corso": c.corso,
                    "modulo": c.modulo, "sottomodulo": c.sottomodulo,
                    "item": c.item, "ease": c.ease, "interval": c.interval,
                    "reps": c.reps, "lapses": c.lapses, "due": c.due,
                } for cid, c in state.items()},
                ensure_ascii=False, indent=2,
            )
            st.download_button("⬇️ Backup stato (.json)",
                json_data.encode("utf-8"),
                file_name="review_state_backup.json", mime="application/json")

        st.divider()
        section("⚠️ Reset progresso")
        st.caption("Riporta le carte allo stato iniziale. Le carte NON vengono eliminate.")
        courses, _ = list_courses_modules(state)
        reset_scope = st.selectbox("Ambito", ["[Tutto]"] + courses)
        if st.button("🔁 Reset"):
            n = reset_progress(state, corso=None if reset_scope == "[Tutto]" else reset_scope)
            save_state(OUTPUT_DIR, state)
            st.success(f"Reset di {n} carte.")
            st.rerun()


# ===========================================================================
# MODALITÀ: EXPORT OBSIDIAN
# ===========================================================================
elif mode_key == "obsidian":
    hero("📝 Export Obsidian", "Crea un vault Obsidian con wikilinks automatici e MOC.")

    corsi = list_corsi(OUTPUT_DIR)
    if not corsi:
        st.info("Biblioteca vuota.")
        st.stop()

    which = st.selectbox("Corso", ["[TUTTI]"] + corsi)
    dest = st.text_input("Destinazione", value=str(OBSIDIAN_EXPORT_DIR.resolve()))

    if st.button("📦 Esporta vault", type="primary"):
        with st.spinner("Costruisco vault…"):
            stats = export_vault(
                OUTPUT_DIR, Path(dest),
                corso_filter=None if which == "[TUTTI]" else which,
            )
        st.success(
            f"✅ **{stats['note']}** note · **{stats['corsi']}** corsi · "
            f"**{stats['wikilinks']}** wikilinks automatici."
        )
        st.code(dest)
        st.info("📂 Apri Obsidian → Apri vault → seleziona questa cartella.")


# ===========================================================================
# MODALITÀ: ANKI ESTERNO
# ===========================================================================
elif mode_key == "anki_ext":
    hero("💪 Anki esterno", "Integrazione opzionale con Anki desktop via AnkiConnect.")
    st.info("ℹ️ Il sistema di ripasso integrato (**🎴 Ripasso**) è la modalità consigliata. "
        "Usa questa solo se vuoi sincronizzarti con Anki.")

    try:
        from core.anki import get_weak_cards, is_available, list_decks, summarize_weak_topics
    except ImportError as e:
        st.error(f"Modulo Anki non caricabile: {e}")
        st.stop()

    if not is_available():
        st.error("❌ AnkiConnect non raggiungibile. Apri Anki + installa addon 2055492159.")
        st.stop()

    llm_cfg = llm_sidebar_config()
    decks = list_decks()
    deck = st.selectbox("Deck Anki", decks) if decks else None
    n_weak = st.slider("Carte deboli", 5, 50, 20)
    n_exercises = st.slider("Esercizi", 5, 20, 10)

    if deck and st.button("🎯 Analizza e genera", type="primary"):
        with st.spinner("Recupero carte…"):
            weak = get_weak_cards(deck, limit=n_weak)
        if not weak:
            st.info("Nessuna carta con lapses. Ottimo!")
            st.stop()

        section(f"Carte sbagliate più spesso ({len(weak)})")
        st.dataframe(pd.DataFrame(weak), use_container_width=True, hide_index=True)

        weak_text = summarize_weak_topics(weak)
        with st.spinner("🤖 Genero esercizi…"):
            llm = LLMClient(**llm_cfg)
            practice = llm.focused_practice(weak_text, n=n_exercises)

        section("🧠 Esercizi personalizzati")
        st.markdown(practice)
        st.download_button("⬇️ Scarica (.md)", practice,
            file_name=f"esercizi_rinforzo_{sanitize(deck)}.md")
