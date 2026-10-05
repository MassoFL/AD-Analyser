#!/bin/zsh
cd "${0:A:h}" || exit 1
python3 scrape.py --connexion
printf '\nAppuyez sur Entrée pour fermer cette fenêtre.'
read -r
