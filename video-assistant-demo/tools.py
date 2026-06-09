"""
Strumenti (tools) che l'agente AI può invocare.
Ogni funzione ha una docstring dettagliata: l'LLM la usa per capire
quando e come chiamare ogni strumento.
"""

from pathlib import Path
from database import get_connection

PRENOTAZIONI_FILE = Path(__file__).parent / "prenotazioni.txt"


# ---------------------------------------------------------------------------
# Tool 1 – Ricerca fornitori nel DB
# ---------------------------------------------------------------------------

def cerca_fornitori(ruolo: str) -> str:
    """
    Cerca nel database locale i fornitori disponibili in base al loro ruolo professionale.
    Usa questo strumento quando l'utente chiede informazioni su costi di personale,
    professionisti disponibili, montatori, fonici, operatori video o grafici.

    Args:
        ruolo: Il ruolo professionale da cercare (es. 'montatore video', 'fonico',
               'operatore video', 'grafica/motion'). Cerca per corrispondenza parziale.

    Returns:
        Una stringa formattata con l'elenco dei fornitori trovati, i loro costi
        e l'esperienza, oppure un messaggio se nessun fornitore è disponibile.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT nome, ruolo, costo_ora, costo_progetto, esperienza, contatto "
        "FROM fornitori WHERE ruolo LIKE ?",
        (f"%{ruolo}%",),
    )
    righe = cur.fetchall()
    conn.close()

    if not righe:
        return f"Nessun fornitore trovato per il ruolo '{ruolo}' nel database."

    risultati = [f"Fornitori disponibili per '{ruolo}':"]
    for r in righe:
        risultati.append(
            f"\n• {r['nome']} ({r['ruolo']})\n"
            f"  Costo orario: €{r['costo_ora']:.0f}/h | "
            f"Costo progetto stimato: €{r['costo_progetto']:.0f}\n"
            f"  Esperienza: {r['esperienza']}\n"
            f"  Contatto: {r['contatto']}"
        )
    return "\n".join(risultati)


# ---------------------------------------------------------------------------
# Tool 2 – Calcolo attrezzatura
# ---------------------------------------------------------------------------

def calcola_attrezzatura(numero_persone: int) -> str:
    """
    Calcola l'attrezzatura tecnica necessaria per registrare un podcast o video
    in base al numero di persone (host + ospiti) che partecipano alla ripresa.
    Usa questo strumento quando l'utente chiede quante telecamere, microfoni
    o apparecchiature servono per la sua produzione.

    Args:
        numero_persone: Il numero totale di persone che appariranno in video
                        (conduttore + ospiti). Deve essere un intero >= 1.

    Returns:
        Una stringa con la lista completa dell'attrezzatura consigliata
        e una stima del costo di noleggio giornaliero.
    """
    if numero_persone <= 0:
        return "Il numero di persone deve essere almeno 1."

    camere = numero_persone
    microfoni = numero_persone
    # Per 3+ persone serve un mixer audio
    mixer = 1 if numero_persone >= 3 else 0
    # Camera di ripresa totale aggiuntiva per shot d'insieme (>= 2 persone)
    camera_totale = 1 if numero_persone >= 2 else 0
    luci_set = max(2, numero_persone)  # almeno 2 luci, poi 1 per persona

    # Stime di noleggio giornaliero (€)
    costo_camera = 80
    costo_microfono = 20
    costo_mixer = 60
    costo_luce = 25

    totale_noleggio = (
        (camere + camera_totale) * costo_camera
        + microfoni * costo_microfono
        + mixer * costo_mixer
        + luci_set * costo_luce
    )

    righe = [
        f"Attrezzatura consigliata per {numero_persone} persona/e:",
        f"  📷 Camere soggetto:     {camere} (1 per persona)",
    ]
    if camera_totale:
        righe.append(f"  📷 Camera totale/wide:   {camera_totale} (shot d'insieme)")
    righe.append(f"  🎙️  Microfoni:            {microfoni} (1 per persona)")
    if mixer:
        righe.append(f"  🎚️  Mixer audio:          {mixer} (necessario con 3+ persone)")
    righe.append(f"  💡 Luci:                 {luci_set} pannelli LED")
    righe.append(f"\n  💰 Stima noleggio giornaliero: ~€{totale_noleggio:.0f}")
    righe.append(
        "  (I prezzi sono stime indicative; verificare con i fornitori locali.)"
    )

    return "\n".join(righe)


# ---------------------------------------------------------------------------
# Tool 3 – Prenotazione studio (mock)
# ---------------------------------------------------------------------------

def prenota_studio_mock(data: str, ora: str) -> str:
    """
    Prenota lo studio di registrazione per una data e un'ora specifiche.
    Simula la prenotazione salvando il record in un file locale (in futuro
    sarà collegato a Google Calendar). Usa questo strumento quando l'utente
    vuole riservare lo studio, pianificare una sessione di registrazione
    o bloccare un orario per le riprese.

    Args:
        data: La data della prenotazione nel formato GG/MM/AAAA (es. '15/07/2025').
        ora:  L'ora di inizio nel formato HH:MM (es. '10:00').

    Returns:
        Un messaggio di conferma con i dettagli della prenotazione effettuata,
        oppure un messaggio di errore se la prenotazione non è andata a buon fine.
    """
    try:
        riga = f"[PRENOTAZIONE] Studio — Data: {data} | Ora: {ora}\n"
        with open(PRENOTAZIONI_FILE, "a", encoding="utf-8") as f:
            f.write(riga)

        return (
            f"✅ Studio prenotato con successo!\n"
            f"   📅 Data: {data}\n"
            f"   🕐 Ora:  {ora}\n"
            f"   📋 La prenotazione è stata registrata nel sistema.\n"
            f"   (In produzione questa chiamata aggiornerebbe Google Calendar.)"
        )
    except Exception as e:
        return f"❌ Errore durante la prenotazione: {e}"


# ---------------------------------------------------------------------------
# Mappa dei tool – usata da agent.py per eseguire le chiamate
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS: dict[str, callable] = {
    "cerca_fornitori": cerca_fornitori,
    "calcola_attrezzatura": calcola_attrezzatura,
    "prenota_studio_mock": prenota_studio_mock,
}

# Definizione in formato Ollama (JSON Schema) dei tool disponibili
TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "cerca_fornitori",
            "description": (
                "Cerca nel database locale i fornitori disponibili in base al loro "
                "ruolo professionale (montatore video, fonico, operatore video, grafica/motion). "
                "Restituisce nomi, costi orari, costi per progetto ed esperienza."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ruolo": {
                        "type": "string",
                        "description": "Il ruolo professionale da cercare (es. 'montatore video', 'fonico').",
                    }
                },
                "required": ["ruolo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calcola_attrezzatura",
            "description": (
                "Calcola l'attrezzatura tecnica necessaria (camere, microfoni, mixer, luci) "
                "e la stima del costo di noleggio giornaliero in base al numero di persone "
                "che partecipano alla ripresa del podcast o video."
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
            "name": "prenota_studio_mock",
            "description": (
                "Prenota lo studio di registrazione per una data e un'ora specifiche. "
                "Simula la prenotazione (in futuro collegato a Google Calendar)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "description": "Data della prenotazione nel formato GG/MM/AAAA.",
                    },
                    "ora": {
                        "type": "string",
                        "description": "Ora di inizio nel formato HH:MM.",
                    },
                },
                "required": ["data", "ora"],
            },
        },
    },
]
