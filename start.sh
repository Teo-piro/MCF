#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  FlatBot – Assistente Flatmates"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! ollama list &>/dev/null; then
  echo "⚠️  Ollama non risponde. Avvialo con: ollama serve"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "📦 Creo virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "✅ Backend in ascolto su: http://localhost:8000"
echo "   Docs API:              http://localhost:8000/docs"
echo "   Premi CTRL+C per fermare."
echo ""
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
