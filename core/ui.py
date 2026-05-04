"""Componenti UI riutilizzabili e CSS custom per StudyBuddy."""
from __future__ import annotations

import streamlit as st


CUSTOM_CSS = """
<style>
/* Import Inter font */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="st-"], .stMarkdown, .stText, button, input, textarea, select {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

code, pre {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Non toccare le icone Material Design di Streamlit */
[data-testid="stIconMaterial"],
[data-testid="collapsedControl"],
.material-icons,
.material-icons-outlined,
span[class*="material"] {
    font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}

/* Headings */
h1, h2, h3, h4 {
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}
h1 { font-size: 2.1rem !important; }
h2 { font-size: 1.5rem !important; margin-top: 1.2rem !important; }
h3 { font-size: 1.2rem !important; }

/* Container principale: NON forzare width, lascia gestire a Streamlit */
.block-container {
    padding-top: 2rem !important;
    padding-bottom: 3rem !important;
}

/* Sidebar style */
section[data-testid="stSidebar"] {
    background-color: #0b0b10 !important;
    border-right: 1px solid #27272f;
}
section[data-testid="stSidebar"] .stRadio label {
    padding: 0.3rem 0 !important;
}

/* Buttons: rounded + subtle */
.stButton button, .stDownloadButton button, .stFormSubmitButton button {
    border-radius: 10px !important;
    font-weight: 500 !important;
    transition: border-color 0.15s ease !important;
    border: 1px solid #2d2d3a !important;
}
.stButton button:hover, .stDownloadButton button:hover {
    border-color: #a78bfa !important;
}
.stButton button[kind="primary"] {
    background: linear-gradient(135deg, #a78bfa 0%, #8b5cf6 100%) !important;
    border: none !important;
    color: white !important;
}
.stButton button[kind="primary"]:hover {
    filter: brightness(1.1);
}

/* Metrics */
[data-testid="stMetric"] {
    background-color: #14141c;
    padding: 0.9rem 1.1rem;
    border-radius: 12px;
    border: 1px solid #27272f;
}
[data-testid="stMetricLabel"] {
    color: #9ca3af !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}
[data-testid="stMetricValue"] {
    color: #e5e7eb !important;
    font-weight: 700 !important;
}

/* Input fields */
.stTextInput input, .stTextArea textarea {
    border-radius: 8px !important;
    border-color: #2d2d3a !important;
    background-color: #14141c !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid #27272f !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0 !important;
    padding: 0.5rem 1rem !important;
    font-weight: 500 !important;
}
.stTabs [aria-selected="true"] {
    background-color: #1a1a24 !important;
    color: #a78bfa !important;
}

/* Containers with border */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: #27272f !important;
    border-radius: 12px !important;
    background-color: #131319;
}

/* Alerts */
.stAlert {
    border-radius: 10px !important;
    border: 1px solid #27272f !important;
}

/* Progress bar */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #a78bfa, #8b5cf6) !important;
}

/* Dividers */
hr {
    border-color: #27272f !important;
    margin: 1.2rem 0 !important;
}

/* Footer visibility: nascondi solo il footer vero */
footer[class*="st-emotion"] { visibility: hidden; height: 0 !important; }

/* Custom badge */
.sb-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-right: 6px;
    background-color: #2d2d3a;
    color: #c4b5fd;
    border: 1px solid #3d3d4a;
}
.sb-badge-success { background-color: #064e3b33; color: #6ee7b7; border-color: #065f46; }
.sb-badge-warn { background-color: #78350f33; color: #fcd34d; border-color: #92400e; }
.sb-badge-purple { background-color: #5b21b633; color: #c4b5fd; border-color: #6d28d9; }

/* Card */
.sb-card {
    background: linear-gradient(135deg, #14141c 0%, #1a1a24 100%);
    border: 1px solid #27272f;
    border-radius: 14px;
    padding: 1.1rem 1.3rem;
    margin-bottom: 0.7rem;
    transition: border-color 0.15s ease;
}
.sb-card:hover {
    border-color: #a78bfa;
}
.sb-card-title {
    font-size: 1.05rem;
    font-weight: 600;
    margin-bottom: 0.2rem;
    color: #e5e7eb;
}
.sb-card-subtitle {
    font-size: 0.8rem;
    color: #9ca3af;
    margin-bottom: 0.6rem;
}
.sb-card-body {
    font-size: 0.9rem;
    color: #d1d5db;
    line-height: 1.5;
}

/* Hero */
.sb-hero {
    background: radial-gradient(ellipse at top left, rgba(139, 92, 246, 0.15), transparent 50%);
    padding: 1.6rem 1.8rem 1.2rem 1.8rem;
    border-radius: 18px;
    border: 1px solid #27272f;
    margin-bottom: 1.5rem;
}
.sb-hero h1 {
    margin: 0 0 0.3rem 0 !important;
    background: linear-gradient(135deg, #e5e7eb, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.sb-hero-sub {
    color: #9ca3af;
    font-size: 0.95rem;
}

/* Section header */
.sb-section {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #9ca3af;
    font-weight: 600;
    margin: 1.2rem 0 0.6rem 0;
}
</style>
"""


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str = "") -> None:
    html = f'<div class="sb-hero"><h1>{title}</h1>'
    if subtitle:
        html += f'<div class="sb-hero-sub">{subtitle}</div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def section(label: str) -> None:
    st.markdown(f'<div class="sb-section">{label}</div>', unsafe_allow_html=True)


def badge(text: str, kind: str = "") -> str:
    klass = "sb-badge"
    if kind == "success":
        klass += " sb-badge-success"
    elif kind == "warn":
        klass += " sb-badge-warn"
    elif kind == "purple":
        klass += " sb-badge-purple"
    return f'<span class="{klass}">{text}</span>'


def card(title: str, subtitle: str = "", body: str = "", badges: list[tuple[str, str]] | None = None) -> None:
    badges_html = ""
    if badges:
        badges_html = " ".join(badge(text, kind) for text, kind in badges)

    html = f"""
    <div class="sb-card">
      <div class="sb-card-title">{title}</div>
      <div class="sb-card-subtitle">{subtitle}</div>
      <div style="margin-bottom:0.6rem;">{badges_html}</div>
      <div class="sb-card-body">{body}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
