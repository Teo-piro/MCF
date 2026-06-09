"""
Entry point FastAPI. Espone POST /api/chat e serve il frontend.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal .env
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import chat
from database import init_db, get_connection
import prenotazioni as P
from email_service import invia_notifica_prenotazione

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Avvio – inizializzazione database dai CSV...")
    init_db()
    logging.info("Database pronto.")
    yield


app = FastAPI(
    title="FlatBot – Assistente Flatmates",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Messaggio(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[Messaggio]

class ChatResponse(BaseModel):
    reply: str


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(body: ChatRequest):
    if not body.messages:
        raise HTTPException(status_code=400, detail="Lista messaggi vuota.")

    cronologia = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        risposta = chat(cronologia)
    except Exception as e:
        logging.exception("Errore agente")
        raise HTTPException(status_code=500, detail=str(e))

    return ChatResponse(reply=risposta)


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": "llama3.1"}


@app.get("/api/collaboratori")
async def lista_collaboratori():
    """Debug: restituisce tutti i collaboratori importati dal CSV."""
    from database import get_connection
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT nome, ruolo, domicilio, status FROM collaboratori ORDER BY ruolo, status")
    righe = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"count": len(righe), "data": righe}


@app.get("/api/fornitori")
async def lista_fornitori():
    """
    Restituisce tutti i collaboratori (fornitori freelance):
    nome, cognome (estratti dal campo nome), ruolo, affidabilità,
    email, telefono, domicilio.
    """
    from database import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT nome, ruolo, domicilio, email, telefono, status FROM collaboratori "
        "ORDER BY status DESC, ruolo, nome"
    )
    righe = [dict(r) for r in cur.fetchall()]
    conn.close()

    def estrai_cognome(nome_completo: str) -> tuple[str, str]:
        """Estrae nome e cognome da 'Nome Cognome' (semplicemente split per spazio)."""
        parti = (nome_completo or "").strip().split()
        if len(parti) >= 2:
            return parti[0], " ".join(parti[1:])
        return nome_completo or "", ""

    arricchiti = []
    for r in righe:
        nome, cognome = estrai_cognome(r["nome"])
        arricchiti.append({
            "nome": nome,
            "cognome": cognome,
            "ruolo": r["ruolo"] or "—",
            "affidabilita": r["status"] or "—",
            "email": r["email"] or "—",
            "telefono": r["telefono"] or "—",
            "domicilio": r["domicilio"] or "—",
        })

    return {"count": len(arricchiti), "data": arricchiti}


@app.get("/api/tariffe")
async def lista_tariffe():
    """Debug: restituisce tutte le tariffe importate dal CSV."""
    from database import get_connection
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT fornitore, servizio, dettagli, costo_testo FROM tariffe ORDER BY fornitore")
    righe = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"count": len(righe), "data": righe}


# ===========================================================================
# INVENTARIO – endpoint per la vista del magazzino sul sito
# ===========================================================================

@app.get("/api/inventario")
async def api_inventario(tipo: str = "", macro: str = ""):
    """
    Lista completa dell'attrezzatura (con tipo/macro). Filtri opzionali per tipo o macro.
    """
    conn = get_connection()
    cur = conn.cursor()
    query = ("SELECT codice, nome, descrizione, categoria, posizione, stato, tipo, macro "
             "FROM attrezzatura")
    cond, params = [], []
    if tipo:
        cond.append("tipo = ?"); params.append(tipo)
    if macro:
        cond.append("macro = ?"); params.append(macro)
    if cond:
        query += " WHERE " + " AND ".join(cond)
    query += " ORDER BY macro, tipo, codice"
    cur.execute(query, params)
    righe = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"count": len(righe), "data": righe}


@app.get("/api/inventario/riepilogo")
async def api_inventario_riepilogo():
    """Conteggi per tipo e macro-categoria (per filtri e dropdown lato UI)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT macro, tipo, COUNT(*) n FROM attrezzatura GROUP BY macro, tipo ORDER BY macro, n DESC")
    righe = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"data": righe}


# ===========================================================================
# PRENOTAZIONI – endpoint REST per disponibilità, creazione, lista, cancellazione
# ===========================================================================

class ArticoloInput(BaseModel):
    tipo: str
    quantita: int = 1


class PrenotazioneInput(BaseModel):
    # Campi obbligatori per una prenotazione valida
    articoli: list[ArticoloInput] | None = None
    tipo: str = ""
    quantita: int = 1
    data_inizio: str  # OBBLIGATORIO
    data_fine: str = ""
    prenotato_da: str  # OBBLIGATORIO
    progetto: str  # OBBLIGATORIO
    ora_inizio: str = ""
    ora_fine: str = ""
    note: str = ""

    def validate_prenotazione(self):
        """Valida che i campi obbligatori siano presenti."""
        if not self.data_inizio or not self.data_inizio.strip():
            raise ValueError("Data inizio è obbligatoria")
        if not self.prenotato_da or not self.prenotato_da.strip():
            raise ValueError("Nome di chi prenota è obbligatorio")
        if not self.progetto or not self.progetto.strip():
            raise ValueError("Nome del progetto è obbligatorio")
        if not self.articoli and not self.tipo:
            raise ValueError("Specifica almeno un articolo")
        return True


@app.get("/api/disponibilita")
async def api_disponibilita(tipo: str, data_inizio: str, data_fine: str = "",
                            ora_inizio: str = "", ora_fine: str = ""):
    """Quanti pezzi di `tipo` sono liberi nel periodo indicato."""
    try:
        return P.pezzi_disponibili(tipo, data_inizio, data_fine or data_inizio,
                                   ora_inizio or None, ora_fine or None)
    except P.PrenotazioneError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/prenotazioni")
async def api_lista_prenotazioni(dal: str = "", al: str = ""):
    """Elenco delle prenotazioni (raggruppate), opzionalmente filtrate per periodo."""
    try:
        righe = P.lista_prenotazioni(dal, al)
    except P.PrenotazioneError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": len(righe), "data": righe}


@app.post("/api/prenotazioni")
async def api_crea_prenotazione(body: PrenotazioneInput):
    """
    Crea una prenotazione (uno o più articoli): il sistema assegna i pezzi liberi
    automaticamente. Atomica: se un articolo non è disponibile, non prenota nulla.
    VALIDAZIONE: data_inizio, prenotato_da, progetto sono obbligatori.
    """
    # Valida campi obbligatori
    try:
        body.validate_prenotazione()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Normalizza: lista di articoli da `articoli`, oppure dal singolo tipo/quantita.
    if body.articoli:
        articoli = [{"tipo": a.tipo, "quantita": a.quantita} for a in body.articoli]
    elif body.tipo:
        articoli = [{"tipo": body.tipo, "quantita": body.quantita}]
    else:
        raise HTTPException(status_code=400, detail="Specifica 'articoli' oppure 'tipo'.")

    try:
        risultato = P.crea_prenotazione_multipla(
            articoli=articoli,
            data_inizio=body.data_inizio, data_fine=body.data_fine,
            prenotato_da=body.prenotato_da, progetto=body.progetto,
            ora_inizio=body.ora_inizio or None, ora_fine=body.ora_fine or None,
            note=body.note,
        )
        # Invia notifica email (asincrono, non blocca la risposta)
        logging.info(f"Invio email per prenotazione {risultato['gruppo_id']}")
        success = invia_notifica_prenotazione(risultato)
        if success:
            logging.info(f"✅ Email inviata per {risultato['gruppo_id']}")
        else:
            logging.warning(f"⚠️ Errore invio email per {risultato['gruppo_id']}")
        return risultato
    except P.PrenotazioneError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/prenotazioni/{gruppo_id}")
async def api_cancella_prenotazione(gruppo_id: str):
    """Cancella una prenotazione dato il suo gruppo_id."""
    try:
        n = P.cancella_prenotazione(gruppo_id)
    except P.PrenotazioneError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"cancellati": n, "gruppo_id": gruppo_id}


# ---------------------------------------------------------------------------
# Studio endpoints
# ---------------------------------------------------------------------------
STUDIO_TIPO = "Sala Studio"

@app.get("/api/studio/disponibilita")
async def api_studio_disponibilita(
    data_inizio: str,
    data_fine: str = "",
    ora_inizio: str = "",
    ora_fine: str = "",
):
    """Verifica se la Sala Studio è libera nel periodo indicato."""
    try:
        return P.pezzi_disponibili(
            STUDIO_TIPO, data_inizio, data_fine or data_inizio,
            ora_inizio or None, ora_fine or None
        )
    except P.PrenotazioneError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/studio/prenotazioni")
async def api_studio_prenotazioni(dal: str = "", al: str = ""):
    """Elenco prenotazioni studio."""
    try:
        tutte = P.lista_prenotazioni(dal, al)
        studio = [p for p in tutte if any(
            (x.get("tipo") == STUDIO_TIPO) for x in (p.get("pezzi") or [])
        )]
        return {"count": len(studio), "data": studio}
    except P.PrenotazioneError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/studio/prenotazioni")
async def api_studio_crea(body: PrenotazioneInput):
    """Prenota la Sala Studio (controlla disponibilità, poi inserisce)."""
    if not body.data_inizio:
        raise HTTPException(status_code=400, detail="Data inizio è obbligatoria")
    if not body.prenotato_da:
        raise HTTPException(status_code=400, detail="Nome di chi prenota è obbligatorio")
    if not body.progetto:
        raise HTTPException(status_code=400, detail="Nome del progetto è obbligatorio")

    try:
        risultato = P.crea_prenotazione_multipla(
            articoli=[{"tipo": STUDIO_TIPO, "quantita": 1}],
            data_inizio=body.data_inizio, data_fine=body.data_fine or body.data_inizio,
            prenotato_da=body.prenotato_da, progetto=body.progetto,
            ora_inizio=body.ora_inizio or None, ora_fine=body.ora_fine or None,
            note=body.note,
        )
        invia_notifica_prenotazione(risultato)
        return risultato
    except P.PrenotazioneError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Serve il frontend statico (index.html + assets)
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
