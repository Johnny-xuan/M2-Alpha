#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
xelatex -interaction=nonstopmode -halt-on-error M2Alpha_Technical_Report.tex
xelatex -interaction=nonstopmode -halt-on-error M2Alpha_Technical_Report.tex
xelatex -interaction=nonstopmode -halt-on-error M2Alpha_Technical_Report.tex
