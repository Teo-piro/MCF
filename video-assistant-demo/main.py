"""
Entry point dell'applicazione FastAPI.
Espone l'endpoint POST /api/chat e serve il frontend statico.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import chat
from database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Avvio applicazione – inizializzazione database...")
    init_db()
    logger.info("Database pronto.")
    yield
    logger.info("Arresto applicazione.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Video Assistant Demo",
    description="Assistente AI per la produzione video e podcast",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In produzione, limitare alle origini autorizzate
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class Messaggio(BaseModel):
    role: str   # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: list[Messaggio]

class ChatResponse(BaseModel):
    reply: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(body: ChatRequest):
    """
    Riceve la cronologia della conversazione e restituisce la risposta dell'assistente.

    Body JSON:
        { "messages": [{"role": "user", "content": "..."}, ...] }
    """
    if not body.messages:
        raise HTTPException(status_code=400, detail="La lista dei messaggi è vuota.")

    # Convertiamo i modelli Pydantic in dict semplici per l'agente
    cronologia = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        risposta = chat(cronologia)
    except Exception as e:
        logger.exception("Errore durante la chiamata all'agente")
        raise HTTPException(status_code=500, detail=f"Errore interno: {e}")

    return ChatResponse(reply=risposta)


@app.get("/api/health")
async def health():
    """Endpoint di health check."""
    return {"status": "ok", "model": "llama3.1"}


# Serve il frontend statico (index.html + assets)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
