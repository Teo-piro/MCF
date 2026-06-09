"""
Logica core del sistema di prenotazione attrezzatura.

UNICA FONTE DI VERITÀ: sia i tool del chatbot (tools.py) sia gli endpoint REST
(main.py) chiamano queste funzioni. Le funzioni ritornano dati strutturati (dict/list),
non testo: la formattazione per la chat o per il sito avviene a valle.

Modello:
- Si prenota per TIPO + QUANTITÀ; il sistema assegna automaticamente i pezzi
  specifici disponibili (es. 2 SD → assegna 2 codici SD liberi nel periodo).
- Una prenotazione multi-pezzo crea N righe che condividono lo stesso gruppo_id.
- Prenotazione a giorni (data_inizio → data_fine); orari opzionali (intra-giornata).
"""

import uuid
from datetime import datetime, date

from database import get_connection


# ---------------------------------------------------------------------------
# Eccezioni
# ---------------------------------------------------------------------------

class PrenotazioneError(Exception):
    """Errore di validazione o di disponibilità nella prenotazione."""


# ---------------------------------------------------------------------------
# Parsing / validazione date e ore
# ---------------------------------------------------------------------------

def parse_data(testo: str) -> str:
    """
    Normalizza una data in formato ISO 'AAAA-MM-GG'.
    Accetta: 'GG/MM/AAAA', 'GG-MM-AAAA', 'AAAA-MM-GG'.
    Solleva PrenotazioneError se non valida.
    """
    testo = (testo or "").strip()
    formati = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y")
    for fmt in formati:
        try:
            return datetime.strptime(testo, fmt).date().isoformat()
        except ValueError:
            continue
    raise PrenotazioneError(
        f"Data '{testo}' non valida. Usa il formato GG/MM/AAAA (es. 15/07/2025)."
    )


def parse_ora(testo: str | None) -> str | None:
    """Normalizza un'ora in 'HH:MM' oppure None se vuota. Solleva errore se invalida."""
    if not testo or not str(testo).strip():
        return None
    testo = str(testo).strip()
    for fmt in ("%H:%M", "%H.%M", "%H"):
        try:
            return datetime.strptime(testo, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise PrenotazioneError(f"Ora '{testo}' non valida. Usa il formato HH:MM (es. 09:30).")


def _valida_periodo(data_inizio: str, data_fine: str) -> tuple[str, str]:
    """Valida e normalizza un intervallo di date. Ritorna (iso_inizio, iso_fine)."""
    di = parse_data(data_inizio)
    df = parse_data(data_fine) if data_fine else di
    if df < di:
        raise PrenotazioneError("La data di fine non può precedere quella di inizio.")
    return di, df


# ---------------------------------------------------------------------------
# Logica di sovrapposizione (conflitto)
# ---------------------------------------------------------------------------

def _date_si_sovrappongono(a_in: str, a_fin: str, b_in: str, b_fin: str) -> bool:
    """True se i due intervalli di date hanno almeno un giorno in comune."""
    return a_in <= b_fin and a_fin >= b_in


def _ore_si_sovrappongono(a_in, a_fin, b_in, b_fin) -> bool:
    """
    True se le due fasce orarie si sovrappongono.
    Se una delle due prenotazioni NON ha orari (giornata intera), si considera
    occupato tutto il giorno → sovrapposizione su qualsiasi giorno condiviso.
    """
    if not (a_in and a_fin) or not (b_in and b_fin):
        return True  # almeno una è a giornata intera → occupa tutto il giorno
    return a_in < b_fin and a_fin > b_in


def _in_conflitto(nuova: dict, esistente: dict) -> bool:
    """Conflitto se le date si sovrappongono E (giornata intera O ore sovrapposte)."""
    if not _date_si_sovrappongono(
        nuova["data_inizio"], nuova["data_fine"],
        esistente["data_inizio"], esistente["data_fine"],
    ):
        return False
    return _ore_si_sovrappongono(
        nuova.get("ora_inizio"), nuova.get("ora_fine"),
        esistente.get("ora_inizio"), esistente.get("ora_fine"),
    )


# ---------------------------------------------------------------------------
# Disponibilità
# ---------------------------------------------------------------------------

def pezzi_disponibili(
    tipo: str,
    data_inizio: str,
    data_fine: str = "",
    ora_inizio: str | None = None,
    ora_fine: str | None = None,
) -> dict:
    """
    Trova i pezzi di un determinato 'tipo' liberi nel periodo richiesto.

    Ritorna:
        {
          "tipo": str,
          "periodo": {"data_inizio","data_fine","ora_inizio","ora_fine"},
          "totale": int,         # pezzi totali di quel tipo nel magazzino
          "disponibili": [ {codice, nome}, ... ],
          "occupati":    [ {codice, nome, prenotato_da, progetto, data_inizio, data_fine}, ... ],
        }
    """
    di, df = _valida_periodo(data_inizio, data_fine)
    oi = parse_ora(ora_inizio)
    of = parse_ora(ora_fine)
    nuova = {"data_inizio": di, "data_fine": df, "ora_inizio": oi, "ora_fine": of}

    conn = get_connection()
    cur = conn.cursor()

    # Tutti i pezzi di quel tipo
    cur.execute(
        "SELECT codice, nome FROM attrezzatura WHERE tipo = ? ORDER BY codice",
        (tipo,),
    )
    pezzi = [dict(r) for r in cur.fetchall()]

    disponibili, occupati = [], []
    for p in pezzi:
        # Prenotazioni esistenti su questo pezzo
        cur.execute(
            "SELECT prenotato_da, progetto, data_inizio, data_fine, ora_inizio, ora_fine "
            "FROM prenotazioni WHERE codice = ?",
            (p["codice"],),
        )
        prenotazioni_pezzo = [dict(r) for r in cur.fetchall()]
        conflitto = next((pr for pr in prenotazioni_pezzo if _in_conflitto(nuova, pr)), None)
        if conflitto:
            occupati.append({**p, **conflitto})
        else:
            disponibili.append(p)

    conn.close()
    return {
        "tipo": tipo,
        "periodo": {"data_inizio": di, "data_fine": df, "ora_inizio": oi, "ora_fine": of},
        "totale": len(pezzi),
        "disponibili": disponibili,
        "occupati": occupati,
    }


# ---------------------------------------------------------------------------
# Creazione prenotazione
# ---------------------------------------------------------------------------

def crea_prenotazione_multipla(
    articoli: list[dict],
    data_inizio: str,
    data_fine: str = "",
    prenotato_da: str = "",
    progetto: str = "",
    ora_inizio: str | None = None,
    ora_fine: str | None = None,
    note: str = "",
) -> dict:
    """
    Prenota PIÙ articoli diversi nello stesso periodo, in un'unica prenotazione
    ("lista della spesa"). Es: 2 Videocamere + 4 Schede SD + 1 Microfono.
    Il sistema assegna automaticamente i pezzi liberi di ogni tipo.

    ATOMICA (tutto-o-niente): se anche UN solo articolo non è disponibile nella
    quantità richiesta, NESSUNA prenotazione viene creata e viene sollevato un errore
    che elenca tutti i problemi.

    Args:
        articoli: lista di dict {"tipo": str, "quantita": int}.
        (gli altri parametri sono condivisi da tutti gli articoli)

    Ritorna:
        {
          "gruppo_id": str,
          "periodo": {...},
          "prenotato_da": str, "progetto": str,
          "articoli": [ {tipo, quantita, assegnati:[{codice,nome}]}, ... ],
          "totale_pezzi": int,
        }
    """
    if not articoli:
        raise PrenotazioneError("Nessun articolo specificato per la prenotazione.")

    # Unisce eventuali duplicati dello stesso tipo (es. "2 SD" + "3 SD" → 5 SD),
    # così il controllo di disponibilità per tipo è corretto.
    richieste: dict[str, int] = {}
    for art in articoli:
        tipo = (art.get("tipo") or "").strip()
        qta = int(art.get("quantita") or 0)
        if not tipo:
            raise PrenotazioneError("Ogni articolo deve avere un 'tipo'.")
        if qta < 1:
            raise PrenotazioneError(f"La quantità per '{tipo}' deve essere almeno 1.")
        richieste[tipo] = richieste.get(tipo, 0) + qta

    # --- FASE 1: verifica disponibilità di TUTTI gli articoli (nessuna scrittura) ---
    periodo = None
    assegnazioni: list[tuple[str, int, list[dict]]] = []  # (tipo, quantita, pezzi)
    errori: list[str] = []
    for tipo, qta in richieste.items():
        disp = pezzi_disponibili(tipo, data_inizio, data_fine, ora_inizio, ora_fine)
        periodo = disp["periodo"]
        if disp["totale"] == 0:
            errori.append(f"'{tipo}': tipo inesistente in inventario")
        elif len(disp["disponibili"]) < qta:
            errori.append(
                f"'{tipo}': richiesti {qta}, disponibili solo {len(disp['disponibili'])}"
            )
        else:
            assegnazioni.append((tipo, qta, disp["disponibili"][:qta]))

    if errori:
        per = periodo or {"data_inizio": parse_data(data_inizio),
                          "data_fine": parse_data(data_fine or data_inizio)}
        raise PrenotazioneError(
            "Prenotazione annullata, disponibilità insufficiente nel periodo "
            f"{per['data_inizio']} → {per['data_fine']}:\n  - " + "\n  - ".join(errori)
        )

    # --- FASE 2: scrittura atomica, tutto sotto lo stesso gruppo_id ---
    gruppo_id = uuid.uuid4().hex[:12]
    creato_il = datetime.now().isoformat(timespec="seconds")
    p = periodo

    conn = get_connection()
    cur = conn.cursor()
    for tipo, qta, pezzi in assegnazioni:
        for pezzo in pezzi:
            cur.execute(
                "INSERT INTO prenotazioni "
                "(gruppo_id, codice, prenotato_da, progetto, data_inizio, data_fine, "
                " ora_inizio, ora_fine, note, creato_il) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (gruppo_id, pezzo["codice"], prenotato_da, progetto,
                 p["data_inizio"], p["data_fine"], p["ora_inizio"], p["ora_fine"],
                 note, creato_il),
            )
    conn.commit()
    conn.close()

    dettaglio_articoli = [
        {"tipo": tipo, "quantita": qta, "assegnati": pezzi}
        for tipo, qta, pezzi in assegnazioni
    ]
    return {
        "gruppo_id": gruppo_id,
        "periodo": p,
        "prenotato_da": prenotato_da,
        "progetto": progetto,
        "articoli": dettaglio_articoli,
        "totale_pezzi": sum(len(pezzi) for _, _, pezzi in assegnazioni),
    }


def crea_prenotazione(
    tipo: str,
    quantita: int,
    data_inizio: str,
    data_fine: str = "",
    prenotato_da: str = "",
    progetto: str = "",
    ora_inizio: str | None = None,
    ora_fine: str | None = None,
    note: str = "",
) -> dict:
    """
    Prenota `quantita` pezzi di un singolo `tipo`. Comodità che delega alla
    versione multipla. Ritorna lo stesso formato "single" di prima per compatibilità.
    """
    r = crea_prenotazione_multipla(
        [{"tipo": tipo, "quantita": quantita}],
        data_inizio, data_fine, prenotato_da, progetto, ora_inizio, ora_fine, note,
    )
    art = r["articoli"][0]
    return {
        "gruppo_id": r["gruppo_id"],
        "tipo": art["tipo"],
        "quantita": art["quantita"],
        "assegnati": art["assegnati"],
        "periodo": r["periodo"],
        "prenotato_da": r["prenotato_da"],
        "progetto": r["progetto"],
    }


# ---------------------------------------------------------------------------
# Lettura / cancellazione
# ---------------------------------------------------------------------------

def lista_prenotazioni(dal: str = "", al: str = "") -> list[dict]:
    """
    Elenca le prenotazioni, raggruppate per gruppo_id (una voce per prenotazione,
    anche se impegna più pezzi). Filtri opzionali per periodo (date ISO o GG/MM/AAAA).
    """
    conn = get_connection()
    cur = conn.cursor()

    # Join con l'inventario per avere nome e tipo di ogni pezzo prenotato.
    query = (
        "SELECT p.gruppo_id, p.prenotato_da, p.progetto, p.data_inizio, p.data_fine, "
        "p.ora_inizio, p.ora_fine, p.note, p.creato_il, "
        "p.codice, a.nome, a.tipo "
        "FROM prenotazioni p LEFT JOIN attrezzatura a ON a.codice = p.codice "
    )
    condizioni, params = [], []
    if dal:
        condizioni.append("p.data_fine >= ?")
        params.append(parse_data(dal))
    if al:
        condizioni.append("p.data_inizio <= ?")
        params.append(parse_data(al))
    if condizioni:
        query += "WHERE " + " AND ".join(condizioni) + " "
    query += "ORDER BY p.data_inizio, p.creato_il, p.codice"

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    # Raggruppa per gruppo_id mantenendo l'ordine di apparizione.
    gruppi: dict[str, dict] = {}
    for r in rows:
        g = r["gruppo_id"]
        if g not in gruppi:
            gruppi[g] = {
                "gruppo_id": g,
                "prenotato_da": r["prenotato_da"],
                "progetto": r["progetto"],
                "data_inizio": r["data_inizio"],
                "data_fine": r["data_fine"],
                "ora_inizio": r["ora_inizio"],
                "ora_fine": r["ora_fine"],
                "note": r["note"],
                "creato_il": r["creato_il"],
                "pezzi": [],
            }
        gruppi[g]["pezzi"].append({
            "codice": r["codice"],
            "nome": r["nome"],
            "tipo": r["tipo"] or "—",
        })

    # Aggiunge i campi derivati: codici (compat), n_pezzi, e riepilogo per tipo.
    risultato = []
    for g in gruppi.values():
        pezzi = g["pezzi"]
        g["codici"] = ", ".join(p["codice"] for p in pezzi)
        g["n_pezzi"] = len(pezzi)
        # conteggio per tipo, preservando l'ordine
        conteggio: dict[str, list[str]] = {}
        for p in pezzi:
            conteggio.setdefault(p["tipo"], []).append(p["codice"])
        g["per_tipo"] = [
            {"tipo": t, "quantita": len(codici), "codici": codici}
            for t, codici in conteggio.items()
        ]
        risultato.append(g)
    return risultato


def dettaglio_prenotazione(gruppo_id: str) -> dict | None:
    """Ritorna i dettagli di una prenotazione (con i singoli pezzi) o None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT p.codice, a.nome, p.prenotato_da, p.progetto, p.data_inizio, "
        "p.data_fine, p.ora_inizio, p.ora_fine, p.note, p.creato_il "
        "FROM prenotazioni p LEFT JOIN attrezzatura a ON a.codice = p.codice "
        "WHERE p.gruppo_id = ? ORDER BY p.codice",
        (gruppo_id,),
    )
    righe = [dict(r) for r in cur.fetchall()]
    conn.close()
    if not righe:
        return None
    primo = righe[0]
    return {
        "gruppo_id": gruppo_id,
        "prenotato_da": primo["prenotato_da"],
        "progetto": primo["progetto"],
        "data_inizio": primo["data_inizio"],
        "data_fine": primo["data_fine"],
        "ora_inizio": primo["ora_inizio"],
        "ora_fine": primo["ora_fine"],
        "note": primo["note"],
        "creato_il": primo["creato_il"],
        "pezzi": [{"codice": r["codice"], "nome": r["nome"]} for r in righe],
    }


def cancella_prenotazione(gruppo_id: str) -> int:
    """Cancella una prenotazione (tutti i pezzi del gruppo). Ritorna le righe eliminate."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM prenotazioni WHERE gruppo_id = ?", (gruppo_id,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    if n == 0:
        raise PrenotazioneError(f"Nessuna prenotazione trovata con id '{gruppo_id}'.")
    return n
