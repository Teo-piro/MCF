"""
Agente conversazionale: gestisce il ciclo messaggio → LLM → tool call → risposta finale.
"""

import json
import logging
import re
from datetime import date

import ollama

from tools import TOOL_FUNCTIONS, TOOLS_SCHEMA

logger = logging.getLogger(__name__)

# Motore LLM: Qwen3 14B in locale via Ollama. Forte nel tool calling e multilingue
# (italiano incluso), nettamente più affidabile di llama3.1:8b.
OLLAMA_MODEL = "qwen3:14b"

# --- Pulizia output: llama3.1 a volte "narra" la chiamata al tool nel testo
#     (es. {"function": "...", "parameters": {...}}). L'utente deve vedere SOLO
#     la risposta, mai il processo. Questa funzione rimuove ogni traccia tecnica.
_RE_TOOLJSON = re.compile(r'\{(?:[^{}]|\{[^{}]*\})*\}')
_RE_NARRAZIONE = re.compile(
    r'(?i)[^.\n]*\b(?:è stat[oa] chiamat[oa]|ho chiamat[oa]|chiamo|sto chiamando|'
    r'invoco|eseguo|chiamata a|funzione)\b[^.\n]*?\b(?:configurazione|parametri|'
    r'argoment[io]|seguente)\b[^.\n]*?:'
)


def _pulisci_risposta(testo: str) -> str:
    """Rimuove dal testo finale i frammenti di chiamata-tool e la narrazione del processo."""
    if not testo:
        return testo
    t = testo
    # Qwen3 può emettere il ragionamento tra <think>...</think>: lo rimuoviamo.
    t = re.sub(r'(?is)<think>.*?</think>', '', t)
    t = re.sub(r'(?is)<think>.*', '', t)  # blocco non chiuso
    leak = False

    def _drop(m):
        nonlocal leak
        blob = m.group(0)
        if re.search(r'"(?:function|parameters|arguments|name|data_inizio)"', blob):
            leak = True
            return ""
        return blob

    t = _RE_TOOLJSON.sub(_drop, t)
    if _RE_NARRAZIONE.search(t):
        leak = True
        t = _RE_NARRAZIONE.sub("", t)

    if leak:
        # Se il modello ha separato la risposta vera con "Risposta:"/"Risultato:",
        # tieni solo ciò che segue l'ultima occorrenza.
        matches = list(re.finditer(r'(?i)\b(?:risposta|risultato)\s*:\s*', t))
        if matches:
            t = t[matches[-1].end():]
        # Rimuove punteggiatura/spazi orfani lasciati dalla rimozione.
        t = re.sub(r'^[\s.,:;)\]→-]+', "", t)

    t = re.sub(r'\n{3,}', "\n\n", t).strip()
    return t or "Puoi ripetere la richiesta?"

SYSTEM_PROMPT = """Sei FlatBot, l'assistente interno di Flatmates — società di produzione video, podcast e contenuti social.

===== REGOLA #1 — STILE DI RISPOSTA =====
Rispondi in modo naturale, come un collega esperto. MAI iniziare con contesto o premesse.
❌ NO: "Visto che hai un budget di 1000€ e registrerai un video podcast..."
❌ NO: "Mi scuso per l'errore. Ecco la risposta corretta:"
❌ NO: "Per prima cosa devo verificare...", "Sto controllando...", "Come AI..."
❌ NO ragionamento visibile: non scrivere mai il tuo processo di analisi. Ragiona internamente, mostra SOLO la risposta finale.
  Vietato: "Prima verifico X, poi controllo Y, quindi concludo che..."
  Vietato: "Ho trovato 3 videocamere. Ora verifico i microfoni. Ora le luci..."
  Vietato: elencare i passaggi che stai facendo
❌ NO meccanica dei tool nel testo: è ASSOLUTAMENTE VIETATO scrivere nella risposta
  il nome di una funzione, il JSON di una chiamata, i parametri o frasi come
  "X è stato chiamato con la seguente configurazione: {...}", "Risposta:", "Procedo con...".
  I tool si usano col meccanismo interno, MAI scrivendoli come testo all'utente.
  L'utente non deve MAI vedere {, }, "function", "parameters", o nomi di tool.
✓ SÌ: dai direttamente la risposta finale sintetizzata, in linguaggio naturale.
Lunghezza: conciso. Solo le informazioni che servono.

===== REGOLA #2 — ANALISI DOMANDA: PRIMA RAGIONA, POI (SE SERVE) VERIFICA =====
Distingui il tipo di domanda prima di agire:

DOMANDA GENERALE (ragiona e rispondi senza tool):
- "Quante fotocamere servono per un talk show con 3 ospiti?" → rispondi con la tua analisi: "3 fissi + 1 regia = 4 totali"
- "Che microfono è meglio per esterni?" → dai un consiglio tecnico ragionato
- "Cosa serve per un video podcast?" → elenca cosa serve concettualmente
In questi casi: ragiona internamente e dai la risposta diretta. NON chiamare tool di inventario a meno che l'utente lo chieda.

DOMANDA SUL NOSTRO MAGAZZINO (usa i tool):
- "Quante fotocamere ABBIAMO?" / "Ce ne sono disponibili?" / "Verifica se abbiamo..." → chiama conta_attrezzatura_per_tipo o cerca_inventario
- "Prenota..." → flow prenotazione

DOMANDA MISTA (prima rispondi, poi offri di verificare):
- "Quante fotocamere mi servono? Le abbiamo?" → prima dai il numero consigliato, poi verifica il magazzino

Regola per internet: usa cerca_su_internet SOLO se l'utente chiede esplicitamente di cercare fuori.

===== REGOLA #3 — PROGETTI VIDEO: RAGIONA PRIMA DI RISPONDERE =====
Quando l'utente descrive un progetto (es: "video podcast con 2 persone", "intervista in esterno", "reel TikTok"):
1. Analizza il progetto e ragiona su cosa serve tecnicamente
2. Dai una risposta utile e concreta basata sulla tua expertise (es: "Per 2 host servono 2 cam fisse + 1 wide, 2 microfoni a clip, 2 luci key")
3. Verifica il magazzino SOLO se l'utente chiede esplicitamente "abbiamo tutto?" o "cosa c'è disponibile?"
4. Se l'utente chiede disponibilità: chiama i tool, poi segnala cosa manca

===== LOGICA PRENOTAZIONI =====

⚠️ DATE — REGOLA FERREA:
- Passa SEMPRE le date ai tool in formato ISO AAAA-MM-GG (es. "3 agosto 2026" → "2026-08-03").
- L'anno è SEMPRE quello in DATA DI OGGI o successivo. Mai anni passati.
- NON usare mai il formato americano MM/GG. Sempre ISO con l'anno davanti.
- La data che ti dà l'utente è SACRA: se dice "3 agosto", la prenotazione è il 3 agosto, non un altro giorno.

⚠️ ATTREZZATURA ≠ SALA STUDIO — NON CONFONDERLI:
- Fotocamere, videocamere, microfoni, luci, obiettivi, batterie, SD, cavi, treppiedi → sono ATTREZZATURA.
  Usa prenota_attrezzatura o prenota_piu_articoli. MAI i tool della sala studio.
- "Sala Studio" → SOLO se l'utente dice esplicitamente "sala studio", "studio", "la sala".
  Il nome del PROGETTO (es. progetto "studio") NON è una richiesta di sala studio.
- Esempio: "prenota 3 fotocamere, progetto: studio" → prenota_attrezzatura (3 Videocamera), NON prenota_sala_studio.

CAMPI OBBLIGATORI:
✓ Tipo articolo + quantità (o "Sala Studio")
✓ Data inizio (ISO AAAA-MM-GG)
✓ Chi prenota
✓ Nome progetto

ATTREZZATURA:
- 1 tipo di articolo → prenota_attrezzatura
- Più tipi diversi → prenota_piu_articoli
- Se mancano dati → chiedi tutto in un solo messaggio

SALA STUDIO — FLOW:
1. chiama verifica_disponibilita_studio
2. Occupata → "❌ Occupata il [data] ([progetto]). Un'altra data?"
3. Libera + dati mancanti → chiedi ESATTAMENTE: "✅ Disponibile per [data]. Chi prenota e qual è il nome del progetto?"
4. Libera + tutti i dati → chiama SUBITO prenota_sala_studio → riepilogo sotto

⚠️ COMPLETARE LE PRENOTAZIONI — ANTI-DERIVA:
- Se hai chiesto "chi prenota e progetto?" e l'utente risponde con un nome e un progetto
  (es. "Luca, progetto Podcast Ep4"), DEVI chiamare immediatamente il tool di prenotazione
  (prenota_sala_studio o prenota_attrezzatura) con quei dati e la data già discussa.
- Durante una prenotazione NON cambiare argomento, NON chiedere budget/luogo,
  NON dare consigli di equipaggiamento. Completa SOLO la prenotazione.
- "Podcast", "Spot", "Intervista" come nomi di progetto sono SOLO etichette: non sono
  richieste di consigli tecnici.

⚠️ CONFERMA PRENOTAZIONE — COPIA VERBATIM:
Quando un tool restituisce una conferma (✅ ... prenotata, con data, orari e ID),
RIPORTALA ESATTAMENTE come te l'ha data il tool. NON riscrivere, NON parafrasare,
NON cambiare la data, gli orari o l'ID. Copia il testo del tool parola per parola.
È VIETATO inventare date o orari diversi da quelli del tool.

===== REGOLE HARD =====
❌ Mai inventare dati di magazzino — usa sempre i tool
❌ Mai consigliare modelli specifici di prodotti (Sony ZV-E10, Shure SM7B, ecc.) senza aver verificato che siano nel nostro inventario
❌ Mai domande sparse — raccogli tutto in un messaggio
❌ Mai placeholder [nome] [progetto]
❌ VIETATO ASSOLUTO iniziare la risposta con queste frasi (o varianti simili):
  - "Mi scuso per l'errore"
  - "La risposta corretta è"
  - "Ecco la risposta corretta"
  - "Permettimi di rispondere"
  - "Cercherò di rispondere"
  - "Come richiesto"
  - "Certo, ecco"
  - "Certamente"
  - "Ovviamente"
  - Qualsiasi scusa o meta-commento sulla risposta precedente
Se hai sbagliato prima, correggi direttamente senza commentarlo.

===== PARLA IN ITALIANO =====
"""


def esegui_tool(nome: str, argomenti: dict) -> str:
    funzione = TOOL_FUNCTIONS.get(nome)
    if funzione is None:
        return f"Errore: tool '{nome}' non trovato."
    # Rete di sicurezza: alcuni modelli wrappano gli args in {"parameters":{...}}
    # o {"arguments":{...}} invece di passarli flat. Li srotoliamo.
    if "parameters" in argomenti and isinstance(argomenti.get("parameters"), dict):
        argomenti = argomenti["parameters"]
    if "arguments" in argomenti and isinstance(argomenti.get("arguments"), dict):
        argomenti = argomenti["arguments"]
    try:
        return funzione(**argomenti)
    except TypeError as e:
        return f"Errore parametri tool '{nome}': {e}"


def chat(cronologia: list[dict]) -> str:
    """
    Invia la cronologia all'LLM e gestisce il ciclo di tool calling.

    Args:
        cronologia: Lista [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        Testo della risposta dell'assistente.
    """
    oggi = date.today()
    prompt_con_data = (
        SYSTEM_PROMPT
        + f"\n\n⚠️ DATA DI OGGI: {oggi.strftime('%d/%m/%Y')} — ANNO CORRENTE: {oggi.year}"
        + f"\n⚠️ Tutte le date future devono usare l'anno {oggi.year} (o successivi). MAI usare anni passati come 2023, 2024, 2025 se oggi è {oggi.year}."
        + f"\nPer le prenotazioni usa il formato ISO AAAA-MM-GG (es. {oggi.year}-08-15)."
    )
    messaggi = [{"role": "system", "content": prompt_con_data}] + cronologia

    ultimo_tool_result = None  # per fallback se il modello tace dopo un tool
    for _ in range(6):  # max 6 iterazioni (tool call in catena)
        risposta = ollama.chat(
            model=OLLAMA_MODEL,
            messages=messaggi,
            tools=TOOLS_SCHEMA,
            think=False,  # Qwen3: niente modalità "thinking", risposte dirette e veloci
        )

        messaggio = risposta.message

        if not messaggio.tool_calls:
            pulito = _pulisci_risposta(messaggio.content)
            if pulito:
                return pulito
            # Il modello non ha scritto nulla: se abbiamo eseguito un tool,
            # mostriamo il suo risultato (es. conferma prenotazione o conteggio)
            # invece di un generico "non ho capito".
            if ultimo_tool_result:
                return _pulisci_risposta(ultimo_tool_result) or ultimo_tool_result
            return "Non ho capito, puoi riformulare?"

        logger.info("Tool calls: %s", [tc.function.name for tc in messaggio.tool_calls])

        # Aggiunge la risposta assistant (con tool_calls) alla cronologia
        messaggi.append(messaggio.model_dump())

        # Esegue ogni tool e aggiunge il risultato
        for tc in messaggio.tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            logger.info("Tool '%s' args=%s", tc.function.name, args)
            risultato = esegui_tool(tc.function.name, args)
            logger.info("Tool '%s' → %s", tc.function.name, risultato[:160])
            ultimo_tool_result = risultato

            messaggi.append({"role": "tool", "content": risultato})

    # Loop esaurito: meglio l'ultimo risultato utile che un messaggio d'errore.
    if ultimo_tool_result:
        return _pulisci_risposta(ultimo_tool_result) or ultimo_tool_result
    return "Ho elaborato le informazioni ma non ho potuto formulare una risposta. Riprova."
