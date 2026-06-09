#!/usr/bin/env bash
# Script di avvio della demo VideoBot
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🎬  VideoBot – Assistente Produzione"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Controlla che Ollama sia avviato
if ! ollama list &>/dev/null; then
  echo "⚠️  Ollama non trovato o non in esecuzione."
  echo "   Avvialo con: ollama serve"
  exit 1
fi

# 2. Crea e attiva il virtual environment se non esiste
if [ ! -d ".venv" ]; then
  echo "📦 Creo virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# 3. Installa le dipendenze
echo "📥 Installo dipendenze..."
pip install -q -r requirements.txt

# 4. Avvia il backend
echo ""
echo "✅ Backend pronto su: http://localhost:8000"
echo "   Premi CTRL+C per fermare."
echo ""
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
