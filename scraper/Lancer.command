#!/bin/zsh
set -eu
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import playwright; import rapidocr_onnxruntime' >/dev/null 2>&1; then
    .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python scrape.py "$@"
printf '\nAppuyez sur Entrée pour fermer cette fenêtre.'
read -r
