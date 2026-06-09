"""
Strumenti (tools) invocabili dall'agente AI.
I dati provengono dal database SQLite popolato dai CSV reali di Flatmates.
Può anche fare ricerche su internet per trovare professionisti e informazioni esterne.
"""

import logging
import re
from pathlib import Path
from database import get_connection
import prenotazioni as P

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

logger = logging.getLogger(__name__)
PRENOTAZIONI_FILE = Path(__file__).parent / "prenotazioni.txt"


# ---------------------------------------------------------------------------
# Tool 1 – Cerca collaboratori per ruolo (e opzionalmente città)
# ---------------------------------------------------------------------------

def cerca_collaboratore(ruolo: str, domicilio: str = "") -> str:
    """
    Cerca nel database i collaboratori disponibili per un determinato ruolo
    (es. 'video editor', 'camera operator', 'fonico', 'producer', 'motion designer').
    Restituisce nome, città, contatti, attrezzatura, note e livello di affidabilità.
    Usa questo strumento quando il cliente chiede chi può occuparsi di riprese,
    montaggio, audio, motion graphics o regia nel progetto.

    Args:
        ruolo:     Ruolo professionale da cercare. Esempi: 'video editor',
                   'camera operator', 'fonico', 'videomaker', 'fotografo',
                   'motion designer', 'producer', 'studio audio'.
        domicilio: (opzionale) Città o regione per filtrare per prossimità,
                   es. 'Milano', 'Roma', 'Torino'. Lascia vuoto per tutti.

    Returns:
        Lista formattata dei collaboratori trovati con dettagli completi,
        oppure messaggio se nessuno corrisponde ai criteri.
    """
    conn = get_connection()
    cur  = conn.cursor()

    if domicilio:
        cur.execute(
            "SELECT nome, ruolo, domicilio, email, telefono, hardware_software, note, status "
            "FROM collaboratori WHERE ruolo LIKE ? AND domicilio LIKE ? ORDER BY status",
            (f"%{ruolo}%", f"%{domicilio}%"),
        )
    else:
        cur.execute(
            "SELECT nome, ruolo, domicilio, email, telefono, hardware_software, note, status "
            "FROM collaboratori WHERE ruolo LIKE ? ORDER BY status",
            (f"%{ruolo}%",),
        )
    righe = cur.fetchall()
    conn.close()

    if not righe:
        return f"Nessun collaboratore trovato per il ruolo '{ruolo}'" + (f" a {domicilio}" if domicilio else "") + "."

    # Raggruppa per status
    gruppi: dict[str, list] = {}
    for r in righe:
        s = r["status"] or "N/D"
        gruppi.setdefault(s, []).append(r)

    ordine_status = ["FIDAT+", "TESTAT+", "DA TESTARE", "N/D"]
    badge = {"FIDAT+": "⭐ Fidato", "TESTAT+": "✅ Testato", "DA TESTARE": "🔍 Da testare"}

    linee = [f"Collaboratori disponibili per '{ruolo}'" + (f" a {domicilio}" if domicilio else "") + ":"]
    for s in ordine_status:
        if s not in gruppi:
            continue
        linee.append(f"\n{badge.get(s, s)}")
        for r in gruppi[s]:
            linee.append(
                f"  • {r['nome']} — {r['domicilio']}\n"
                f"    📧 {r['email'] or '–'}  📞 {r['telefono'] or '–'}\n"
                f"    🎥 Attrezzatura: {r['hardware_software'] or '–'}\n"
                f"    📝 Note: {r['note'] or '–'}"
            )

    return "\n".join(linee)


# ---------------------------------------------------------------------------
# Tool 2 – Cerca tariffe e servizi dei fornitori
# ---------------------------------------------------------------------------

def cerca_tariffe(servizio: str) -> str:
    """
    Cerca nel database le tariffe e i costi dei fornitori per un determinato
    tipo di servizio. Utile per preventivi su: set design, consulenza creativa,
    render 3D, affitto studio, montaggio scenografie, pack design.
    Usa questo strumento quando il cliente chiede quanto costa un servizio
    specifico o vuole conoscere i prezzi dei fornitori di Flatmates.

    Args:
        servizio: Tipo di servizio da cercare. Esempi: 'consulenza', 'set design',
                  'affitto sala', '3D render', 'moodboard', 'planimetria',
                  'pack design', 'studio', 'props'.

    Returns:
        Elenco formattato delle tariffe trovate con fornitore, descrizione e costi,
        oppure messaggio se nessuna tariffa corrisponde.
    """
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT fornitore, servizio, dettagli, costo_testo, costo_valore, email "
        "FROM tariffe WHERE servizio LIKE ? OR dettagli LIKE ? ORDER BY fornitore, costo_valore",
        (f"%{servizio}%", f"%{servizio}%"),
    )
    righe = cur.fetchall()
    conn.close()

    if not righe:
        return f"Nessuna tariffa trovata per '{servizio}' nel database."

    linee = [f"Tariffe trovate per '{servizio}':"]
    fornitore_prec = None
    for r in righe:
        if r["fornitore"] != fornitore_prec:
            linee.append(f"\n📋 {r['fornitore']}  ({r['email'] or 'nessun contatto'})")
            fornitore_prec = r["fornitore"]
        dettaglio = f"  – {r['dettagli']}" if r["dettagli"] else ""
        linee.append(f"  • {r['servizio']}{dettaglio}: {r['costo_testo']}")

    return "\n".join(linee)


# ---------------------------------------------------------------------------
# Tool 3 – Calcolo attrezzatura tecnica
# ---------------------------------------------------------------------------

def calcola_attrezzatura(numero_persone: int) -> str:
    """
    Calcola l'attrezzatura tecnica necessaria (camere, microfoni, mixer, luci)
    in base al numero di persone che partecipano alle riprese di un podcast o video.
    Restituisce anche una stima del costo di noleggio giornaliero.
    Usa questo strumento quando il cliente chiede quante telecamere, microfoni
    o apparecchiature servono, o vuole una stima sui costi tecnici.

    Args:
        numero_persone: Numero totale di persone inquadrate in video
                        (conduttore + ospiti). Intero >= 1.

    Returns:
        Lista dell'attrezzatura consigliata con stima del costo di noleggio.
    """
    if numero_persone <= 0:
        return "Il numero di persone deve essere almeno 1."

    camere         = numero_persone
    camera_totale  = 1 if numero_persone >= 2 else 0
    microfoni      = numero_persone
    mixer          = 1 if numero_persone >= 3 else 0
    luci           = max(2, numero_persone)

    # Stime noleggio giornaliero (€)
    noleggio = (
        (camere + camera_totale) * 80
        + microfoni * 20
        + mixer * 60
        + luci * 25
    )

    righe = [f"Attrezzatura consigliata per {numero_persone} persona/e:"]
    righe.append(f"  📷  Camere soggetto:    {camere}")
    if camera_totale:
        righe.append(f"  📷  Camera wide/totale: {camera_totale} (shot d'insieme)")
    righe.append(f"  🎙️  Microfoni:           {microfoni}")
    if mixer:
        righe.append(f"  🎚️  Mixer audio:         {mixer} (obbligatorio con 3+ persone)")
    righe.append(f"  💡  Luci LED:            {luci} pannelli")
    righe.append(f"\n  💰  Stima noleggio giornaliero: ~€{noleggio}")
    righe.append("  (Prezzi indicativi; verificare disponibilità con i fornitori.)")
    return "\n".join(righe)


# ---------------------------------------------------------------------------
# Tool 4 – Prenotazione studio
# ---------------------------------------------------------------------------

def _norm_data(testo: str) -> str:
    """
    Normalizza QUALSIASI data a ISO 'AAAA-MM-GG' e corregge gli anni passati
    (errore tipico del LLM, che usa il 2023/2024 dei dati di training).
    Accetta sia ISO sia GG/MM/AAAA. Se non riesce a interpretarla, restituisce
    l'input invariato e lascia che sia parse_data() a valle a sollevare l'errore.
    """
    from datetime import date as _date
    if not testo or not str(testo).strip():
        return testo
    # toglie un eventuale suffisso orario tipo 'T00:00:00' o ' 00:00:00'
    s = re.split(r"[T ]", str(testo).strip())[0]
    try:
        iso = P.parse_data(s)  # -> 'AAAA-MM-GG'
    except Exception:
        return testo
    y, m, d = iso.split("-")
    if int(y) < _date.today().year:
        y = str(_date.today().year)
    return f"{y}-{m}-{d}"


def _fmt_it(iso: str) -> str:
    """Converte ISO 'AAAA-MM-GG' in 'GG/MM/AAAA' per la visualizzazione italiana."""
    if not iso:
        return iso
    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso


def verifica_disponibilita_studio(
    data_inizio: str,
    data_fine: str = "",
    ora_inizio: str = "",
    ora_fine: str = "",
) -> str:
    """
    Verifica se la Sala Studio è disponibile nel periodo indicato.
    Usa SEMPRE questo strumento PRIMA di prenota_sala_studio.

    Args:
        data_inizio: Data inizio nel formato AAAA-MM-GG (es. '2025-07-20').
        data_fine:   Data fine (opzionale, default = stesso giorno).
        ora_inizio:  Ora inizio HH:MM (es. '09:00').
        ora_fine:    Ora fine HH:MM (es. '18:00').

    Returns:
        Messaggio con disponibilità e, se occupata, chi l'ha prenotata.
    """
    data_inizio = _norm_data(data_inizio)
    data_fine   = _norm_data(data_fine) if data_fine else data_inizio
    try:
        result = P.pezzi_disponibili(
            "Sala Studio", data_inizio, data_fine,
            ora_inizio or None, ora_fine or None
        )
        per = result["periodo"]
        if result["disponibili"]:
            msg = f"✅ Sala Studio LIBERA per {_fmt_it(per['data_inizio'])}"
            if per["data_fine"] and per["data_fine"] != per["data_inizio"]:
                msg += f" → {_fmt_it(per['data_fine'])}"
            if ora_inizio:
                msg += f" dalle {ora_inizio}" + (f" alle {ora_fine}" if ora_fine else "")
            return msg
        else:
            occ = result["occupati"][0] if result["occupati"] else {}
            return (
                f"❌ Sala Studio OCCUPATA per quel periodo.\n"
                f"   Progetto: {occ.get('progetto','—')}\n"
                f"   Prenotato da: {occ.get('prenotato_da','—')}\n"
                f"   Dal {_fmt_it(occ.get('data_inizio','?'))} al {_fmt_it(occ.get('data_fine','?'))}"
            )
    except Exception as e:
        return f"❌ Errore verifica: {e}"


def prenota_sala_studio(
    data_inizio: str,
    data_fine: str = "",
    ora_inizio: str = "",
    ora_fine: str = "",
    prenotato_da: str = "",
    progetto: str = "",
) -> str:
    """
    Prenota la Sala Studio nel database (prenotazione reale, non mock).
    IMPORTANTE: chiama prima verifica_disponibilita_studio. Se occupata, NON procedere.
    Richiedi sempre: prenotato_da e progetto all'utente prima di chiamare questo tool.

    Args:
        data_inizio:  Data inizio AAAA-MM-GG (es. '2025-07-20').
        data_fine:    Data fine (opzionale, default = stesso giorno).
        ora_inizio:   Ora inizio HH:MM (es. '09:00').
        ora_fine:     Ora fine HH:MM (es. '18:00').
        prenotato_da: Nome di chi prenota (obbligatorio).
        progetto:     Nome del progetto (obbligatorio).

    Returns:
        Conferma con gruppo_id o messaggio di errore.
    """
    if not prenotato_da or not progetto:
        return "❌ Devi specificare sia 'prenotato_da' che 'progetto' per completare la prenotazione."
    if not data_inizio:
        return "❌ Specifica almeno data_inizio nel formato AAAA-MM-GG."
    data_inizio = _norm_data(data_inizio)
    data_fine   = _norm_data(data_fine) if data_fine else data_inizio
    try:
        risultato = P.crea_prenotazione_multipla(
            articoli=[{"tipo": "Sala Studio", "quantita": 1}],
            data_inizio=data_inizio,
            data_fine=data_fine,
            prenotato_da=prenotato_da,
            progetto=progetto,
            ora_inizio=ora_inizio or None,
            ora_fine=ora_fine or None,
        )
        # Usa le date CANONICHE salvate nel DB, non l'input grezzo del modello.
        per = risultato["periodo"]
        msg = (
            f"✅ Sala Studio prenotata!\n"
            f"   📅 {_fmt_it(per['data_inizio'])}"
            + (f" → {_fmt_it(per['data_fine'])}" if per["data_fine"] and per["data_fine"] != per["data_inizio"] else "")
            + "\n"
        )
        if per.get("ora_inizio"):
            msg += f"   🕐 {per['ora_inizio']}" + (f" – {per['ora_fine']}" if per.get("ora_fine") else "") + "\n"
        msg += f"   👤 {prenotato_da}  |  📁 {progetto}\n"
        msg += f"   ID prenotazione: {risultato['gruppo_id']}"
        return msg
    except P.PrenotazioneError as e:
        return f"❌ Impossibile prenotare: {e}"
    except Exception as e:
        return f"❌ Errore: {e}"


# ---------------------------------------------------------------------------
# Tool 5 – Ricerca nell'inventario attrezzatura
# ---------------------------------------------------------------------------

def cerca_attrezzatura(query: str) -> str:
    """
    Cerca nell'inventario locale di Flatmates l'attrezzatura disponibile.
    Puoi cercare per: codice, nome, categoria, posizione, stato.
    Restituisce dettagli completi di ogni attrezzatura trovata.
    Usa questo strumento quando il cliente chiede informazioni su:
    - Qual è il codice di una determinata attrezzatura
    - Quale attrezzatura abbiamo nella categoria "Luci" o "Cavi"
    - Dove si trova un determinato oggetto (Studio, Trasferta, ecc.)
    - Lo stato di un'attrezzatura (Operativo, In Riparazione, ecc.)

    Args:
        query: Parola chiave da cercare. Esempi: 'luce godox', 'SC-GDX-001',
               'cavo', 'categoria:Luci', 'posizione:Studio', 'stato:Operativo'

    Returns:
        Lista dell'attrezzatura trovata con codice, nome, descrizione, categoria,
        posizione e stato, oppure messaggio se nulla è trovato.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Ricerca per query generica in codice, nome, descrizione, categoria, tipo
    cur.execute(
        "SELECT codice, nome, descrizione, categoria, posizione, stato, appunti, tipo "
        "FROM attrezzatura "
        "WHERE codice LIKE ? OR nome LIKE ? OR descrizione LIKE ? OR categoria LIKE ? OR tipo LIKE ? "
        "ORDER BY codice",
        (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"),
    )
    righe = cur.fetchall()
    conn.close()

    if not righe:
        return f"❌ Nessuna attrezzatura trovata per: '{query}'"

    linee = [f"🔧 Attrezzatura trovata per '{query}': ({len(righe)} risultati)"]
    for r in righe:
        nome = r["nome"] or "(senza nome)"
        linee.append(f"\n  **{r['codice']}** – {nome}  [{r['tipo']}]")
        if r["descrizione"]:
            linee.append(f"    Descrizione: {r['descrizione']}")
        linee.append(f"    📍 Posizione: {r['posizione'] or '–'}  |  Stato: {r['stato'] or '–'}")
        if r["appunti"]:
            linee.append(f"    Note: {r['appunti']}")

    return "\n".join(linee)


# ---------------------------------------------------------------------------
# Tool 6 – Conta attrezzatura per tipo
# ---------------------------------------------------------------------------

# Mappa sinonimi → tipo canonico nel DB (vedi classifica() in database.py).
# Le chiavi sono parole che l'utente potrebbe usare; il valore è il 'tipo' esatto.
SINONIMI_TIPO: dict[str, str] = {
    # Video
    "fotocamera": "Videocamera", "fotocamere": "Videocamera",
    "videocamera": "Videocamera", "videocamere": "Videocamera",
    "camera": "Videocamera", "camere": "Videocamera",
    "macchina fotografica": "Videocamera", "lumix": "Videocamera",
    "obiettivo": "Obiettivo", "obiettivi": "Obiettivo",
    "lente": "Obiettivo", "lenti": "Obiettivo", "ottica": "Obiettivo", "ottiche": "Obiettivo",
    "batteria": "Batteria", "batterie": "Batteria",
    # Audio
    "microfono": "Microfono", "microfoni": "Microfono", "mic": "Microfono",
    "cuffia": "Cuffie", "cuffie": "Cuffie",
    "mixer": "Mixer audio", "rodecaster": "Mixer audio",
    # Luci
    "luce": "Luce", "luci": "Luce", "faro": "Luce", "fari": "Luce",
    "softbox": "Softbox", "lampada": "Lampada", "pannello": "Pannello LED", "pannelli": "Pannello LED",
    # Supporti
    "cavalletto": "Cavalletto videocamera", "cavalletti": "Cavalletto videocamera",
    "treppiede": "Cavalletto videocamera", "treppiedi": "Cavalletto videocamera",
    "tripod": "Cavalletto videocamera",
    "stativo luce": "Stativo luce", "stativi luce": "Stativo luce",
    "stativo microfono": "Stativo microfono",
    "teleprompter": "Teleprompter",
    # Storage
    "ssd": "SSD", "hard disk": "Hard Disk", "hdd": "Hard Disk",
    "scheda sd": "Scheda SD", "sd": "Scheda SD",
    "microsd": "Scheda MicroSD", "micro sd": "Scheda MicroSD",
    # Cavi
    "cavo hdmi": "Cavo HDMI", "hdmi": "Cavo HDMI",
    "cavo usb": "Cavo USB-C", "usb": "Cavo USB-C", "usb-c": "Cavo USB-C",
    "cavo xlr": "Cavo XLR", "xlr": "Cavo XLR",
    "alimentatore": "Alimentatore", "caricatore": "Caricatore",
    # Arredo / accessori
    "fondale": "Fondale", "fondali": "Fondale",
    "tavolo": "Tavolo", "tavoli": "Tavolo",
    "tablet": "Tablet", "telecomando": "Telecomando",
}


def _risolvi_tipo(termine: str) -> str | None:
    """Mappa un termine libero dell'utente al 'tipo' canonico nel DB."""
    t = termine.lower().strip()
    if t in SINONIMI_TIPO:
        return SINONIMI_TIPO[t]
    # Match parziale: cerca un sinonimo contenuto nel termine (o viceversa)
    for chiave, tipo in SINONIMI_TIPO.items():
        if chiave in t or t in chiave:
            return tipo
    return None


def conta_attrezzatura_per_tipo(tipo: str) -> str:
    """
    Conta quanti elementi di un determinato tipo ci sono nell'inventario e li elenca.
    Capisce i sinonimi: 'fotocamere' → Videocamera, 'mic' → Microfono, ecc.
    Usa questo strumento quando il cliente chiede QUANTITÀ, es:
    - "Quante fotocamere abbiamo?"  → conta le Videocamere (NON batterie o obiettivi)
    - "Quanti microfoni?"           → conta solo i Microfoni
    - "Quante batterie?" / "Quanti obiettivi?" / "Quante luci?"

    Tipi precisi disponibili nel DB:
    Video: Videocamera, Obiettivo, Batteria
    Audio: Microfono, Cuffie, Mixer audio
    Luci: Luce, Softbox, Lampada, Pannello LED
    Supporti: Cavalletto videocamera, Stativo luce, Stativo fondale, Stativo microfono,
              Palo fondale, Stativo teleprompter
    Storage: SSD, Scheda SD, Scheda MicroSD, Hard Disk
    Cavi: Cavo luce, Cavo microfono, Cavo HDMI, Cavo USB-C, Cavo XLR, Alimentatore
    Accessori: Caricatore, Teleprompter, Telecomando, Tablet
    Arredo: Fondale, Tavolo

    Args:
        tipo: Tipo o sinonimo da contare (es. 'fotocamere', 'Videocamera', 'microfoni').

    Returns:
        Il conteggio e la lista degli elementi di quel tipo.
    """
    # Risolve il sinonimo verso il tipo canonico; se non trovato, prova match diretto
    tipo_canonico = _risolvi_tipo(tipo) or tipo

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT codice, nome FROM attrezzatura WHERE tipo = ? ORDER BY codice",
        (tipo_canonico,),
    )
    righe = cur.fetchall()
    conn.close()

    if not righe:
        return (
            f"❌ Nessun elemento di tipo '{tipo}' (interpretato come '{tipo_canonico}').\n"
            f"   Usa il riepilogo inventario per vedere i tipi disponibili."
        )

    linee = [f"📦 **{tipo_canonico}**: {len(righe)} elementi"]
    for i, r in enumerate(righe, 1):
        nome = r["nome"] or "(senza nome)"
        linee.append(f"  {i}. {r['codice']:20} – {nome}")

    return "\n".join(linee)


# ---------------------------------------------------------------------------
# Tool 7 – Riepilogo completo dell'inventario
# ---------------------------------------------------------------------------

def riepilogo_inventario() -> str:
    """
    Restituisce un riepilogo completo dell'inventario: tutti i tipi di attrezzatura
    raggruppati per macro-categoria, con il conteggio di ciascuno.
    Usa questo strumento quando il cliente chiede una panoramica generale, es:
    - "Cosa abbiamo in magazzino?"
    - "Fammi l'inventario completo"
    - "Che attrezzatura abbiamo?"
    - "Quanti pezzi abbiamo in totale?"

    Returns:
        Il riepilogo per macro-categoria con i conteggi per tipo.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT macro, tipo, COUNT(*) n FROM attrezzatura "
        "GROUP BY macro, tipo ORDER BY macro, n DESC"
    )
    righe = cur.fetchall()
    cur.execute("SELECT COUNT(*) tot FROM attrezzatura")
    totale = cur.fetchone()["tot"]
    conn.close()

    linee = [f"📋 **Inventario Flatmates** – {totale} pezzi totali\n"]
    macro_prec = None
    for r in righe:
        if r["macro"] != macro_prec:
            linee.append(f"\n**{r['macro']}**")
            macro_prec = r["macro"]
        linee.append(f"  • {r['tipo']}: {r['n']}")

    return "\n".join(linee)


# ---------------------------------------------------------------------------
# Tool 8 – Verifica disponibilità attrezzatura per un periodo
# ---------------------------------------------------------------------------

def verifica_disponibilita(tipo: str, data_inizio: str, data_fine: str = "",
                           ora_inizio: str = "", ora_fine: str = "") -> str:
    """
    Verifica quanti pezzi di un tipo di attrezzatura sono LIBERI in un dato periodo,
    e quanti sono già prenotati. Usa questo strumento PRIMA di prenotare, o quando
    il cliente chiede "è libera la Lumix la prossima settimana?" o "quante SD posso
    prenotare dal 10 al 12?".

    Args:
        tipo: Tipo di attrezzatura (es. 'Videocamera', 'Scheda SD', 'Microfono').
        data_inizio: Data inizio (ISO AAAA-MM-GG, es. 2026-08-03).
        data_fine: Data fine (ISO AAAA-MM-GG, es. 2026-08-03). Se vuota = stesso giorno.
        ora_inizio: (opzionale) ora inizio HH:MM, solo se serve granularità oraria.
        ora_fine: (opzionale) ora fine HH:MM.

    Returns:
        Riepilogo testuale di disponibili e occupati nel periodo.
    """
    data_inizio = _norm_data(data_inizio)
    data_fine   = _norm_data(data_fine) if data_fine else data_inizio
    try:
        d = P.pezzi_disponibili(tipo, data_inizio, data_fine or data_inizio,
                                ora_inizio or None, ora_fine or None)
    except P.PrenotazioneError as e:
        return f"⚠️ {e}"

    per = d["periodo"]
    intestazione = (
        f"📅 Disponibilità **{d['tipo']}** dal {_fmt_it(per['data_inizio'])} al {_fmt_it(per['data_fine'])}"
        + (f" ({per['ora_inizio']}–{per['ora_fine']})" if per["ora_inizio"] else "")
        + ":"
    )
    linee = [intestazione,
             f"  ✅ Liberi: {len(d['disponibili'])} su {d['totale']} totali"]
    if d["disponibili"]:
        linee.append("     " + ", ".join(p["codice"] for p in d["disponibili"]))
    if d["occupati"]:
        linee.append(f"  🔴 Occupati: {len(d['occupati'])}")
        for o in d["occupati"]:
            chi = o.get("progetto") or o.get("prenotato_da") or "prenotato"
            linee.append(f"     {o['codice']} → {chi} ({_fmt_it(o['data_inizio'])}→{_fmt_it(o['data_fine'])})")
    return "\n".join(linee)


# ---------------------------------------------------------------------------
# Tool 9 – Prenota attrezzatura (assegna pezzi automaticamente)
# ---------------------------------------------------------------------------

def prenota_attrezzatura(tipo: str, quantita: int, data_inizio: str, data_fine: str = "",
                         prenotato_da: str = "", progetto: str = "",
                         ora_inizio: str = "", ora_fine: str = "") -> str:
    """
    Prenota una o più unità di un tipo di attrezzatura per un periodo. Il sistema
    sceglie e assegna automaticamente i pezzi specifici disponibili (es. se prenoti
    2 SD, assegna 2 codici SD liberi). Blocca la prenotazione se non ci sono abbastanza
    pezzi liberi. Usa questo strumento quando il cliente vuole RISERVARE attrezzatura.

    Chiedi sempre il nome di chi prenota e il progetto se non sono stati forniti.

    Args:
        tipo: Tipo di attrezzatura (es. 'Videocamera', 'Scheda SD', 'Microfono').
        quantita: Quante unità prenotare (intero >= 1).
        data_inizio: Data inizio (ISO AAAA-MM-GG, es. 2026-08-03).
        data_fine: Data fine (ISO AAAA-MM-GG, es. 2026-08-03). Se vuota = stesso giorno.
        prenotato_da: Nome di chi prenota.
        progetto: Nome del progetto/produzione.
        ora_inizio: (opzionale) ora inizio HH:MM.
        ora_fine: (opzionale) ora fine HH:MM.

    Returns:
        Conferma con i codici assegnati e l'id prenotazione, oppure errore.
    """
    data_inizio = _norm_data(data_inizio)
    data_fine   = _norm_data(data_fine) if data_fine else data_inizio
    try:
        r = P.crea_prenotazione(tipo, int(quantita), data_inizio, data_fine or data_inizio,
                                prenotato_da, progetto, ora_inizio or None, ora_fine or None)
    except (P.PrenotazioneError, ValueError) as e:
        return f"❌ Prenotazione non riuscita: {e}"

    per = r["periodo"]
    codici = ", ".join(p["codice"] for p in r["assegnati"])
    linee = [
        f"✅ Prenotazione confermata (id: {r['gruppo_id']})",
        f"   {r['quantita']}× {r['tipo']} → {codici}",
        f"   📅 Dal {_fmt_it(per['data_inizio'])} al {_fmt_it(per['data_fine'])}"
        + (f" ({per['ora_inizio']}–{per['ora_fine']})" if per["ora_inizio"] else ""),
    ]
    if r["prenotato_da"]:
        linee.append(f"   👤 {r['prenotato_da']}")
    if r["progetto"]:
        linee.append(f"   🎬 {r['progetto']}")
    return "\n".join(linee)


# ---------------------------------------------------------------------------
# Tool 9-bis – Prenota PIÙ articoli insieme (lista della spesa)
# ---------------------------------------------------------------------------

def _parse_articoli(testo: str) -> list[dict]:
    """
    Converte una stringa tipo "2 fotocamere, 4 SD, 1 microfono" in
    [{"tipo": "Videocamera", "quantita": 2}, ...] risolvendo i sinonimi.
    Senza numero iniziale, la quantità è 1.
    """
    articoli = []
    for parte in testo.split(","):
        parte = parte.strip()
        if not parte:
            continue
        m = re.match(r"(\d+)\s*[x×]?\s+(.*)", parte)  # es. "2 SD", "2x SD"
        if m:
            qta, termine = int(m.group(1)), m.group(2).strip()
        else:
            qta, termine = 1, parte
        tipo = _risolvi_tipo(termine) or termine  # canonicalizza (fotocamere→Videocamera)
        articoli.append({"tipo": tipo, "quantita": qta})
    return articoli


def prenota_piu_articoli(articoli: str, data_inizio: str, data_fine: str = "",
                         prenotato_da: str = "", progetto: str = "",
                         ora_inizio: str = "", ora_fine: str = "") -> str:
    """
    Prenota PIÙ articoli diversi nello stesso periodo, in un'unica prenotazione
    (come una lista della spesa). Il sistema assegna automaticamente i pezzi liberi.
    È ATOMICA: se anche un solo articolo non è disponibile, NON prenota nulla.
    Usa questo strumento quando il cliente vuole riservare più cose insieme, es:
    "prenota 2 fotocamere, 4 schede SD e 1 microfono per il 10-12 luglio".

    Args:
        articoli: Lista in formato testo separato da virgole, ogni voce "QUANTITÀ TIPO",
                  es. "2 fotocamere, 4 schede SD, 1 microfono". Capisce i sinonimi.
        data_inizio: Data inizio (ISO AAAA-MM-GG, es. 2026-08-03).
        data_fine: Data fine (ISO AAAA-MM-GG, es. 2026-08-03). Vuota = stesso giorno.
        prenotato_da: Nome di chi prenota.
        progetto: Nome del progetto/produzione.
        ora_inizio: (opzionale) ora inizio HH:MM.
        ora_fine: (opzionale) ora fine HH:MM.

    Returns:
        Conferma con tutti i pezzi assegnati per ciascun articolo, oppure errore
        che elenca cosa non era disponibile.
    """
    lista = _parse_articoli(articoli)
    if not lista:
        return "❌ Non ho capito quali articoli prenotare. Esempio: '2 fotocamere, 4 SD'."
    data_inizio = _norm_data(data_inizio)
    data_fine   = _norm_data(data_fine) if data_fine else data_inizio
    try:
        r = P.crea_prenotazione_multipla(
            lista, data_inizio, data_fine or data_inizio,
            prenotato_da, progetto, ora_inizio or None, ora_fine or None,
        )
    except P.PrenotazioneError as e:
        return f"❌ Prenotazione non riuscita: {e}"

    per = r["periodo"]
    linee = [
        f"✅ Prenotazione confermata (id: {r['gruppo_id']}) — {r['totale_pezzi']} pezzi totali",
        f"   📅 Dal {_fmt_it(per['data_inizio'])} al {_fmt_it(per['data_fine'])}"
        + (f" ({per['ora_inizio']}–{per['ora_fine']})" if per["ora_inizio"] else ""),
    ]
    for a in r["articoli"]:
        codici = ", ".join(p["codice"] for p in a["assegnati"])
        linee.append(f"   • {a['quantita']}× {a['tipo']} → {codici}")
    if r["prenotato_da"]:
        linee.append(f"   👤 {r['prenotato_da']}")
    if r["progetto"]:
        linee.append(f"   🎬 {r['progetto']}")
    return "\n".join(linee)


# ---------------------------------------------------------------------------
# Tool 10 – Elenca / cancella prenotazioni
# ---------------------------------------------------------------------------

def mostra_prenotazioni(dal: str = "", al: str = "") -> str:
    """
    Elenca le prenotazioni di attrezzatura esistenti, opzionalmente filtrate per periodo.
    Usa questo strumento quando il cliente chiede "cosa è prenotato?", "che prenotazioni
    ci sono a luglio?", "chi ha la Lumix questa settimana?".

    Args:
        dal: (opzionale) mostra prenotazioni attive dal (ISO AAAA-MM-GG, es. 2026-08-03).
        al:  (opzionale) ...fino al (ISO AAAA-MM-GG, es. 2026-08-03).

    Returns:
        Elenco delle prenotazioni con periodo, pezzi, responsabile e progetto.
    """
    try:
        righe = P.lista_prenotazioni(dal, al)
    except P.PrenotazioneError as e:
        return f"⚠️ {e}"

    if not righe:
        return "📭 Nessuna prenotazione trovata per il periodo indicato."

    linee = [f"📋 Prenotazioni ({len(righe)}):"]
    for r in righe:
        periodo = f"{_fmt_it(r['data_inizio'])}→{_fmt_it(r['data_fine'])}"
        if r["ora_inizio"]:
            periodo += f" {r['ora_inizio']}–{r['ora_fine']}"
        etichetta = r["progetto"] or r["prenotato_da"] or "—"
        # Mostra "Tipo (codice)" per ogni pezzo invece del solo codice
        dettaglio = ", ".join(f"{p['tipo']} ({p['codice']})" for p in r.get("pezzi", []))
        linee.append(
            f"\n  • [{r['gruppo_id']}] {etichetta}"
            f"\n    📅 {periodo}  |  {r['n_pezzi']} pezzi: {dettaglio or r['codici']}"
        )
    return "\n".join(linee)


def cancella_prenotazione(gruppo_id: str) -> str:
    """
    Cancella una prenotazione esistente dato il suo id (gruppo_id), liberando i pezzi.
    Usa questo strumento quando il cliente vuole annullare una prenotazione.

    Args:
        gruppo_id: L'id della prenotazione da cancellare (mostrato tra parentesi quadre).

    Returns:
        Conferma della cancellazione o errore se l'id non esiste.
    """
    try:
        n = P.cancella_prenotazione(gruppo_id)
    except P.PrenotazioneError as e:
        return f"❌ {e}"
    return f"🗑️ Prenotazione '{gruppo_id}' cancellata ({n} pezzi liberati)."


# ---------------------------------------------------------------------------
# Tool 11 – Ricerca su internet
# ---------------------------------------------------------------------------

def raccomanda_equipaggiamento_podcast(budget_euro: int, tipo_contenuto: str, luogo_registrazione: str) -> str:
    """
    Raccomanda un setup di equipaggiamento per podcast, video podcast o contenuti social.
    Propone 2-3 configurazioni diverse basate su budget, tipo di contenuto e location.

    Args:
        budget_euro: Budget totale in euro (es. 200, 500, 1500)
        tipo_contenuto: Tipo di produzione. Esempi: 'podcast audio', 'video podcast',
                       'social media', 'YouTube', 'TikTok/Reels', 'video intervista'
        luogo_registrazione: Ambiente. Esempi: 'stanza rumorosa', 'casa normale',
                            'studio trattato', 'esterno'

    Returns:
        Raccomandazioni concrete con modelli specifici e prezzi approssimativi.
    """
    setups = []

    # LIVELLO 1: Budget basso (<200€)
    if budget_euro < 200:
        setups.append("""
📍 SETUP ENTRY-LEVEL (Budget: <150€)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUDIO: Microfono USB economico (Samson Q2U ~80€) o Lavalier wireless (~50€)
VIDEO: Smartphone personale (iPhone/Samsung flagship)
LUCE: Luce naturale dalla finestra oppure Ring light economico (~30€)
MONTAGGIO: App gratis (DaVinci Resolve, CapCut)

✓ Perfetto per: Podcast amatoriale, content social veloce, test formato
⚠️ Limitazioni: Audio compresso, video limitato a smartphone, poco controllo luce
""")

    # LIVELLO 2: Budget medio (200-1000€)
    elif budget_euro < 1000:
        setups.append("""
📍 SETUP PROFESSIONALE ENTRY (Budget: 300-800€)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUDIO:
  • Microfono Rode PodMic (~100€) oppure Shure MV7X (~150€)
  • Interfaccia Focusrite Scarlett Solo (~100€)
  • Boom arm + Pop filter (~30€)
  • Cuffie monitoring Audio-Technica ATH-M50x (~100€)
VIDEO:
  • Smartphone flagship oppure Webcam 4K Logitech Brio (~100€)
  • Treppiedi regolabile (~30€)
LUCE:
  • Softbox LED Godox 60cm (~200€) oppure Amaran 60d
  • Stativo luce (~30€)

✓ Perfetto per: Podcast settimanale, YouTube, content social di qualità
✓ Setup modulare e espandibile
""")

    # LIVELLO 3: Budget alto (>1000€)
    if budget_euro >= 1000 or "studio" in luogo_registrazione.lower():
        setups.append("""
📍 SETUP BROADCAST PROFESSIONALE (Budget: >1500€)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUDIO:
  • Microfono Shure SM7B (~400€) - standard radiofonico
  • Rødecaster Pro II mixer (~600€) - registrazione multi-ospite
  • Boom arm Yellowtec o Rode PSA1 (~80€)
  • Cuffie Sony MDR-7506 (~100€)
VIDEO:
  • Camera Mirrorless Sony FX30 o A7IV (~1500€+)
  • Obiettivo luminoso f/1.8 (~300€)
  • Monitor esterno 4K (~200€)
LUCE:
  • Setup 3-luci professionali (Key + Fill + Backlight)
  • Aputure 600D Pro (~5000€) oppure Godox SL-300W (~800€)
  • Modificatori di luce professionali (softbox, octabox)

✓ Perfetto per: Podcast quotidiani, produzione broadcast, YouTube top-tier
✓ Qualità cinematografica
""")

    # CONSIDERAZIONI PER LOCATION
    location_notes = ""
    if "rumorosa" in luogo_registrazione.lower():
        location_notes = "\n🎤 STANZA RUMOROSA → Microfono DINAMICO essenziale (riduce rumori)"
    elif "esterno" in luogo_registrazione.lower():
        location_notes = "\n🌍 REGISTRAZIONE ESTERNA → Microfono lavalier wireless + protezione vento (deadcat)"
    elif "studio" in luogo_registrazione.lower():
        location_notes = "\n🏢 STUDIO TRATTATO → Puoi usare condensatore, audio perfetto garantito"

    # CONSIDERAZIONI PER CONTENUTO
    content_notes = ""
    if "social" in tipo_contenuto.lower() or "tiktok" in tipo_contenuto.lower() or "reels" in tipo_contenuto.lower():
        content_notes = "\n📱 SOCIAL MEDIA → Priorità: video in movimento (gimbal). Audio secondario ma importante per engagement."
    elif "podcast audio" in tipo_contenuto.lower():
        content_notes = "\n🎙️ PODCAST AUDIO PURO → Audio TUTTO. Investi nei microfoni e interfaccia, trascura video."
    elif "youtube" in tipo_contenuto.lower():
        content_notes = "\n📺 YOUTUBE → Audio professionale + video decente + editing pulito. Setup equilibrato."

    result = "🎬 RACCOMANDAZIONI EQUIPAGGIAMENTO\n" + "="*50 + "\n"
    result += f"Budget: {budget_euro}€ | Tipo: {tipo_contenuto} | Luogo: {luogo_registrazione}\n\n"
    result += "\n".join(setups)
    result += location_notes + content_notes
    result += "\n\n💡 PROSSIMI STEP:\n1. Scegli una configurazione\n2. Fammi le prenotazioni\n3. Procediamo con test audio/video"

    return result


def cerca_su_internet(query: str) -> str:
    """
    Cerca informazioni su internet usando DuckDuckGo.
    Utile per trovare professionisti freelance, agenzie, prezzi di mercato,
    nuove figure professionali o tecnologie non presenti nel database locale.
    Usa questo strumento quando il cliente chiede cose che non sono nel database
    (es. "Trovami un fotografo specializzato in food a Roma", "Quali sono i prezzi
    attuali di un drone 4K?", "Chi è il miglior studio di registrazione a Berlino?").

    Args:
        query: La domanda o ricerca da fare su internet in italiano.
               Es. "fotografo food Roma", "prezzi studio registrazione Milano",
                   "miglior colorist freelance".

    Returns:
        Un riassunto dei risultati trovati con link e informazioni utili.
    """
    if DDGS is None:
        return "❌ Ricerca internet non disponibile. Installa duckduckgo-search con: pip install duckduckgo-search"

    try:
        results = DDGS().text(query, max_results=5)
        if not results:
            return f"❌ Nessun risultato trovato per: {query}"

        linee = [f"🔍 Risultati di ricerca per: '{query}'"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Senza titolo")
            body = r.get("body", "")[:150]  # Limita a 150 caratteri
            href = r.get("href", "")
            linee.append(f"\n{i}. **{title}**")
            if body:
                linee.append(f"   {body}...")
            if href:
                linee.append(f"   🔗 {href}")

        return "\n".join(linee)

    except Exception as e:
        logger.error("Errore ricerca internet: %s", e)
        return f"⚠️ Errore durante la ricerca: {e}\n(Assicurati di avere una connessione internet)"


# ---------------------------------------------------------------------------
# Mappa tool → funzione Python  (usata da agent.py)
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS: dict[str, callable] = {
    "cerca_collaboratore": cerca_collaboratore,
    "cerca_tariffe":       cerca_tariffe,
    "calcola_attrezzatura": calcola_attrezzatura,
    "verifica_disponibilita_studio": verifica_disponibilita_studio,
    "prenota_sala_studio": prenota_sala_studio,
    "cerca_inventario": cerca_attrezzatura,
    "conta_attrezzatura_per_tipo": conta_attrezzatura_per_tipo,
    "riepilogo_inventario": riepilogo_inventario,
    "verifica_disponibilita": verifica_disponibilita,
    "prenota_attrezzatura": prenota_attrezzatura,
    "prenota_piu_articoli": prenota_piu_articoli,
    "mostra_prenotazioni": mostra_prenotazioni,
    "cancella_prenotazione": cancella_prenotazione,
    "raccomanda_equipaggiamento_podcast": raccomanda_equipaggiamento_podcast,
    "cerca_su_internet": cerca_su_internet,
}

# Schema JSON per Ollama tool calling
TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "cerca_collaboratore",
            "description": (
                "Cerca nel database i collaboratori di Flatmates disponibili per un ruolo: "
                "video editor, camera operator, fonico, videomaker, fotografo, "
                "motion designer, producer, studio audio. "
                "Restituisce contatti, attrezzatura e livello di affidabilità (FIDAT+/TESTAT+/DA TESTARE)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ruolo": {
                        "type": "string",
                        "description": "Ruolo professionale da cercare (es. 'video editor', 'fonico').",
                    },
                    "domicilio": {
                        "type": "string",
                        "description": "Città opzionale per filtrare per prossimità (es. 'Milano').",
                    },
                },
                "required": ["ruolo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cerca_tariffe",
            "description": (
                "Cerca nel database le tariffe dei fornitori di Flatmates per un servizio: "
                "consulenza creativa, set design, 3D render, moodboard, planimetria, "
                "affitto sala studio, pack design, ricerca props, revisioni. "
                "Restituisce costi e dettagli del fornitore."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "servizio": {
                        "type": "string",
                        "description": "Tipo di servizio (es. 'set design', 'affitto sala', 'consulenza').",
                    }
                },
                "required": ["servizio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calcola_attrezzatura",
            "description": (
                "Calcola l'attrezzatura tecnica necessaria (camere, microfoni, mixer, luci) "
                "e la stima del noleggio giornaliero in base al numero di persone in video."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "numero_persone": {
                        "type": "integer",
                        "description": "Numero totale di persone in video (conduttore + ospiti).",
                    }
                },
                "required": ["numero_persone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conta_attrezzatura_per_tipo",
            "description": (
                "Conta QUANTI elementi di un tipo preciso ci sono nell'inventario e li elenca. "
                "Capisce i sinonimi (es. 'fotocamere'→Videocamera, 'mic'→Microfono). "
                "Distingue bene i tipi: una batteria NON è una videocamera, un cavo microfono "
                "NON è un microfono. Tipi: Videocamera, Obiettivo, Batteria, Microfono, Cuffie, "
                "Mixer audio, Luce, Softbox, Lampada, Pannello LED, Cavalletto videocamera, "
                "Stativo luce, Stativo fondale, Stativo microfono, SSD, Scheda SD, Scheda MicroSD, "
                "Hard Disk, Cavo HDMI, Cavo USB-C, Cavo XLR, Fondale, Tavolo, ecc. "
                "Usalo per domande di QUANTITÀ come 'quante fotocamere abbiamo?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "description": "Tipo o sinonimo da contare (es. 'fotocamere', 'microfoni', 'batterie').",
                    }
                },
                "required": ["tipo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "riepilogo_inventario",
            "description": (
                "Restituisce un riepilogo completo dell'inventario: tutti i tipi di attrezzatura "
                "raggruppati per macro-categoria con i conteggi. Usalo per panoramiche generali "
                "come 'cosa abbiamo in magazzino?', 'fammi l'inventario', 'che attrezzatura c'è?'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verifica_disponibilita",
            "description": (
                "Verifica quanti pezzi di un tipo di attrezzatura sono liberi in un periodo "
                "e quanti già prenotati. Usalo PRIMA di prenotare o per domande come "
                "'è libera la Lumix dal 10 al 12?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "description": "Tipo (es. 'Videocamera', 'Scheda SD')."},
                    "data_inizio": {"type": "string", "description": "Data inizio in formato ISO AAAA-MM-GG (es. 2026-08-03). MAI formato americano."},
                    "data_fine": {"type": "string", "description": "Data fine in formato ISO AAAA-MM-GG (vuota = stesso giorno)."},
                    "ora_inizio": {"type": "string", "description": "Opzionale, ora inizio HH:MM."},
                    "ora_fine": {"type": "string", "description": "Opzionale, ora fine HH:MM."},
                },
                "required": ["tipo", "data_inizio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prenota_attrezzatura",
            "description": (
                "Prenota una o più unità di un tipo di attrezzatura per un periodo. Il sistema "
                "assegna automaticamente i pezzi liberi e blocca se non bastano. Chiedi nome di "
                "chi prenota e progetto se mancano."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "description": "Tipo (es. 'Videocamera', 'Scheda SD')."},
                    "quantita": {"type": "integer", "description": "Quante unità (>=1)."},
                    "data_inizio": {"type": "string", "description": "Data inizio in formato ISO AAAA-MM-GG (es. 2026-08-03). MAI formato americano."},
                    "data_fine": {"type": "string", "description": "Data fine in formato ISO AAAA-MM-GG (vuota = stesso giorno)."},
                    "prenotato_da": {"type": "string", "description": "Nome di chi prenota."},
                    "progetto": {"type": "string", "description": "Nome del progetto/produzione."},
                    "ora_inizio": {"type": "string", "description": "Opzionale, ora inizio HH:MM."},
                    "ora_fine": {"type": "string", "description": "Opzionale, ora fine HH:MM."},
                },
                "required": ["tipo", "quantita", "data_inizio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prenota_piu_articoli",
            "description": (
                "Prenota PIÙ articoli diversi insieme nello stesso periodo (lista della spesa), "
                "es. '2 fotocamere, 4 schede SD, 1 microfono'. È atomica: se uno non è disponibile "
                "non prenota nulla. Usa questo (NON prenota_attrezzatura) quando il cliente chiede "
                "più tipi di attrezzatura in una sola prenotazione."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "articoli": {
                        "type": "string",
                        "description": "Voci separate da virgola 'QUANTITÀ TIPO' (es. '2 fotocamere, 4 SD, 1 microfono').",
                    },
                    "data_inizio": {"type": "string", "description": "Data inizio in formato ISO AAAA-MM-GG (es. 2026-08-03). MAI formato americano."},
                    "data_fine": {"type": "string", "description": "Data fine in formato ISO AAAA-MM-GG (vuota = stesso giorno)."},
                    "prenotato_da": {"type": "string", "description": "Nome di chi prenota."},
                    "progetto": {"type": "string", "description": "Nome del progetto/produzione."},
                    "ora_inizio": {"type": "string", "description": "Opzionale, ora inizio HH:MM."},
                    "ora_fine": {"type": "string", "description": "Opzionale, ora fine HH:MM."},
                },
                "required": ["articoli", "data_inizio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mostra_prenotazioni",
            "description": (
                "Elenca le prenotazioni di attrezzatura esistenti, opzionalmente filtrate per "
                "periodo. Usalo per 'cosa è prenotato?', 'che prenotazioni ci sono a luglio?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dal": {"type": "string", "description": "Opzionale, da (ISO AAAA-MM-GG)."},
                    "al": {"type": "string", "description": "Opzionale, a (ISO AAAA-MM-GG)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancella_prenotazione",
            "description": (
                "Cancella una prenotazione dato il suo id (gruppo_id), liberando i pezzi. "
                "Usalo quando il cliente vuole annullare una prenotazione."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gruppo_id": {"type": "string", "description": "Id della prenotazione da cancellare."},
                },
                "required": ["gruppo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cerca_inventario",
            "description": (
                "Cerca uno SPECIFICO oggetto nell'inventario per parola chiave (codice, nome, "
                "categoria). Restituisce codice, nome, descrizione, posizione e stato. "
                "Esempi: 'luce godox', 'SC-GDX-001', 'categoria:Luci'. "
                "NON usare per contare quantità o rispondere a 'quante/quanti X abbiamo?': "
                "per quello usa conta_attrezzatura_per_tipo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Parola chiave per cercare (codice, nome, categoria, ecc.).",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verifica_disponibilita_studio",
            "description": (
                "Verifica se la Sala Studio Flatmates è disponibile in un dato periodo. "
                "DEVI chiamare questo tool PRIMA di prenota_sala_studio. "
                "Se la sala è occupata, informa l'utente e non procedere con la prenotazione."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data_inizio": {"type": "string", "description": "Data inizio formato AAAA-MM-GG (es. '2025-07-20')."},
                    "data_fine":   {"type": "string", "description": "Data fine formato AAAA-MM-GG (opzionale, default = stesso giorno)."},
                    "ora_inizio":  {"type": "string", "description": "Ora inizio HH:MM (es. '09:00')."},
                    "ora_fine":    {"type": "string", "description": "Ora fine HH:MM (es. '18:00')."},
                },
                "required": ["data_inizio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prenota_sala_studio",
            "description": (
                "Prenota la Sala Studio Flatmates nel database (prenotazione reale). "
                "Chiama SEMPRE verifica_disponibilita_studio prima. "
                "Richiedi all'utente: prenotato_da e progetto se non forniti."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data_inizio":  {"type": "string", "description": "Data inizio AAAA-MM-GG."},
                    "data_fine":    {"type": "string", "description": "Data fine AAAA-MM-GG (opzionale)."},
                    "ora_inizio":   {"type": "string", "description": "Ora inizio HH:MM."},
                    "ora_fine":     {"type": "string", "description": "Ora fine HH:MM."},
                    "prenotato_da": {"type": "string", "description": "Nome di chi prenota (obbligatorio)."},
                    "progetto":     {"type": "string", "description": "Nome del progetto (obbligatorio)."},
                },
                "required": ["data_inizio", "prenotato_da", "progetto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "raccomanda_equipaggiamento_podcast",
            "description": (
                "Usa SOLO se l'utente chiede ESPLICITAMENTE un consiglio su quale equipaggiamento "
                "comprare o usare (es. 'che setup mi consigli per un podcast?', 'che attrezzatura serve "
                "con 500€?'). Propone configurazioni per budget. "
                "NON usare durante una prenotazione, NON usare se l'utente sta solo prenotando o nominando "
                "un progetto chiamato 'Podcast'. Un nome di progetto NON è una richiesta di consigli."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_euro": {
                        "type": "integer",
                        "description": "Budget totale in euro. Esempi: 150, 500, 1500, 3000."
                    },
                    "tipo_contenuto": {
                        "type": "string",
                        "description": "Tipo di produzione. Esempi: 'podcast audio', 'video podcast', 'YouTube', 'TikTok', 'Reels', 'video intervista', 'social media'."
                    },
                    "luogo_registrazione": {
                        "type": "string",
                        "description": "Ambiente di registrazione. Esempi: 'stanza rumorosa', 'casa normale', 'studio trattato', 'esterno'."
                    }
                },
                "required": ["budget_euro", "tipo_contenuto", "luogo_registrazione"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cerca_su_internet",
            "description": (
                "Cerca informazioni su internet usando DuckDuckGo. "
                "Usa questo per trovare professionisti freelance, agenzie, prezzi di mercato, "
                "tecnologie o servizi che non sono nel database locale di Flatmates. "
                "Esempi: 'fotografo specializzato in food a Roma', 'prezzi studio registrazione Milano', "
                "'miglior colorist freelance Italia'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "La domanda o ricerca da fare su internet (in italiano).",
                    }
                },
                "required": ["query"],
            },
        },
    },
]
