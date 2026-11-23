#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if ! python3 -c 'import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 15) else 1)'; then
  echo "Python 3.12 à 3.15 est requis."
  exit 1
fi

python_version=$(python3 -c 'import sys; print("{}.{}".format(*sys.version_info[:2]))')
if [ -e .venv ] && [ ! -x .venv/bin/python ]; then
  echo "L'environnement .venv est incomplet. Renommez-le puis relancez ce script."
  exit 1
fi
if [ ! -e .venv ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import sys; sys.exit(0 if "{}.{}".format(*sys.version_info[:2]) == sys.argv[1] else 1)' "$python_version"; then
  echo "L'environnement .venv n'utilise pas Python $python_version. Renommez-le puis relancez ce script."
  exit 1
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "🚀 Lancement de l'application Streamlit..."
.venv/bin/python -m streamlit run app.py