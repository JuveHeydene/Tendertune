#!/usr/bin/env bash
# Compilation du mémoire BTP RAG
set -euo pipefail
cd "$(dirname "$0")"

if command -v latexmk >/dev/null 2>&1; then
  latexmk -pdf -interaction=nonstopmode -file-line-error main.tex
else
  pdflatex -interaction=nonstopmode main.tex
  pdflatex -interaction=nonstopmode main.tex
fi

echo "→ PDF généré : main.pdf"
