# StudyBuddy Dockerfile
# Base: Python 3.12 slim (light + recente)
FROM python:3.12-slim

# Metadata
LABEL maintainer="Federico Ordonselli"
LABEL description="StudyBuddy - GenAI study assistant"

# Variabili d'ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dipendenze di sistema (FFmpeg per audio/video, build tools per pypdf etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Working directory dentro il container
WORKDIR /app

# Copia prima i requirements (cache Docker: se non cambiano, non reinstalla)
COPY requirements.txt .

# Installa dipendenze Python
RUN pip install -r requirements.txt

# Copia il resto del codice
COPY . .

# Crea cartelle che servono a runtime (verranno montate come volumi)
RUN mkdir -p /app/inputs /app/outputs /app/uploads_tmp

# Espone la porta di Streamlit
EXPOSE 8501

# Health check: Streamlit risponde su /_stcore/health
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

# Comando di avvio
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
