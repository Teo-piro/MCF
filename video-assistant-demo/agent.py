"""
Logica dell'agente conversazionale.
Gestisce il ciclo: messaggio utente → LLM → (eventuale tool call) → risposta finale.
"""

import json
import logging
import ollama

from tools import TOOL_FUNCTIONS, TOOLS_SCHEMA

logger = logging.getLogger(__name__)

# Modello da usare – cambia con 'qwen2.5' se preferito
OLLAMA_MODEL = "llama3.1"

SYSTEM_PROMPT = """Sei un assistente esperto nella produzione di contenuti video e podcast.
Il tuo nome è VideoBot e lavori come produttore esecutivo freelance con 10 anni di esperienza.

Il tuo compito è aiutare i clienti a:
- Stimare i costi di produzione (podcast, video corporate, YouTube, ecc.)
- Calcolare l'attrezzatura tecnica necessaria
- Trovare professionisti qualificati (montatori, fonici, operatori)
- Prenotare lo studio di registrazione

REGOLE FONDAMENTALI:
1. Non inventare mai numeri o informazioni. Usa SEMPRE i tools disponibili per dati concreti.
2. Se l'utente fa una domanda generica (es. "quanto costa un podcast") e mancano dati
   essenziali, NON rispondere con stime vaghe. Fai UNA SOLA domanda di chiarimento
   alla volta, in modo naturale e conversazionale.
3. I dati essenziali per un preventivo podcast sono:
   - Numero di episodi (o se è una tantum)
   - Numero di persone nel podcast (host + ospiti fissi)
   - Durata stimata di ogni episodio
   - Se serve montaggio/post-produzione o solo riprese
4. Solo quando hai TUTTI i dati necessari, usa i tools per fornire informazioni precise.
5. Parla sempre in italiano, con tono professionale ma amichevole.
6. Quando usi i risultati di un tool, integrali in una risposta chiara e strutturata.
"""


def esegui_tool(nome: str, argomenti: dict) -> str:
    """Esegue la funzione Python corrispondente al tool richiesto dall'LLM."""
    funzione = TOOL_FUNCTIONS.get(nome)
    if funzione is None:
        return f"Errore: tool '{nome}' non trovato."
    try:
        return funzione(**argomenti)
    except TypeError as e:
        return f"Errore nei parametri del tool '{nome}': {e}"


def chat(cronologia: list[dict]) -> str:
    """
    Invia la cronologia dei messaggi all'LLM e gestisce il ciclo
    di tool calling fino ad ottenere la risposta testuale finale.

    Args:
        cronologia: Lista di messaggi nel formato [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        Il testo della risposta dell'assistente.
    """
    # Prepend del system prompt
    messaggi = [{"role": "system", "content": SYSTEM_PROMPT}] + cronologia

    # Ciclo: può servire più di un giro se l'LLM chiama tool in sequenza
    for _ in range(5):  # max 5 iterazioni per sicurezza
        risposta = ollama.chat(
            model=OLLAMA_MODEL,
            messages=messaggi,
            tools=TOOLS_SCHEMA,
        )

        messaggio = risposta.message

        # Se l'LLM non chiama nessun tool, restituiamo la risposta testuale
        if not messaggio.tool_calls:
            return messaggio.content or "Mi dispiace, non ho capito. Puoi ripetere?"

        # --- Gestione delle tool calls ---
        logger.info("Tool call richiesta: %s", [tc.function.name for tc in messaggio.tool_calls])

        # Aggiungiamo la risposta dell'assistente (con le tool calls) alla cronologia
        messaggi.append(messaggio.model_dump())

        # Eseguiamo ogni tool call e aggiungiamo il risultato alla cronologia
        for tool_call in messaggio.tool_calls:
            nome_tool = tool_call.function.name
            # Gli argomenti possono arrivare come stringa JSON o come dict
            argomenti = tool_call.function.arguments
            if isinstance(argomenti, str):
                try:
                    argomenti = json.loads(argomenti)
                except json.JSONDecodeError:
                    argomenti = {}

            risultato = esegui_tool(nome_tool, argomenti)
            logger.info("Risultato tool '%s': %s", nome_tool, risultato[:120])

            messaggi.append({
                "role": "tool",
                "content": risultato,
            })

    # Fallback se si superano le iterazioni massime
    return "Ho elaborato le informazioni ma non sono riuscito a formulare una risposta. Riprova."
