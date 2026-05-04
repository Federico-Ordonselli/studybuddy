#!/usr/bin/env fish
cd (dirname (status -f))
source .venv/bin/activate.fish

set -l SP .venv/lib/python3.14/site-packages/nvidia
set -x LD_LIBRARY_PATH $PWD/$SP/cublas/lib $PWD/$SP/cudnn/lib $LD_LIBRARY_PATH

# Apre il browser dopo 2 secondi, in parallelo
fish -c "sleep 2; xdg-open http://localhost:8501" &

streamlit run app.py --server.headless true
