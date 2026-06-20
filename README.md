═══════════════════════════════════════════════════════════════════════════
  Aura — Assistente interno di Flatmates
═══════════════════════════════════════════════════════════════════════════

Aura è l'assistente che (per ora) gira IN LOCALE sul computer e aiuta
il team a:

  • Consultare il magazzino attrezzatura (fotocamere, microfoni, luci, ecc.)
  • Verificare la disponibilità di attrezzatura e della Sala Studio
  • Prenotare attrezzatura e Sala Studio (con invio email di conferma)
  • Consultare collaboratori/fornitori freelance e relative tariffe
  • Ricevere consigli tecnici su che attrezzatura serve per un progetto

Tutto il "cervello" del bot è un modello AI che gira in locale (Qwen3 14B
tramite Ollama): (sarebbe bello dargli un LLM più potente tipo quello di openAI o Antropic


───────────────────────────────────────────────────────────────────────────
  COME È FATTO (architettura in breve)
───────────────────────────────────────────────────────────────────────────

  Browser (frontend)  ──►  Backend FastAPI  ──►  Agente AI  ──►  Ollama (Qwen3)
   pagine HTML/CSS/JS        main.py             agent.py         modello locale
                                │
                                ├──►  tools.py        (le "azioni" che il bot può fare)
                                ├──►  prenotazioni.py (logica prenotazioni, atomica)
                                ├──►  database.py     (SQLite, importa i CSV)
                                └──►  email_service.py(notifiche via SendGrid)

  File principali:
    main.py            Server web: espone /api/chat e serve il sito.
    agent.py           Ciclo conversazione: parla col modello, esegue i tool.
    tools.py           Le funzioni che il bot può usare (cerca, conta, prenota…).
    prenotazioni.py    Motore prenotazioni: disponibilità e booking atomici.
    database.py        Crea il database SQLite e importa i dati dai CSV.
    email_service.py   Invia l'email di conferma quando si prenota.
    assistente.db      Il database (creato in automatico al primo avvio).
    frontend/          Le pagine del sito (chat, magazzino, studio, fornitori).
    Materiale/         I CSV di partenza (inventario, collaboratori, tariffe).


───────────────────────────────────────────────────────────────────────────
  COSA SERVE (prerequisiti — da installare UNA volta sola)
───────────────────────────────────────────────────────────────────────────

  1) Python 3.11 o superiore
       Verifica con:   python3 --version

  2) Ollama (il programma che fa girare l'AI in locale)
       Scaricalo da:   https://ollama.com/download
       Dopo l'installazione, scarica il modello (è grande, ~9 GB):
           ollama pull qwen3:14b

       NOTA: il modello qwen3:14b va bene su un Mac con almeno 16 GB di RAM
       (testato su Apple M4 Pro 24 GB). Su macchine più piccole si può usare
       un modello più leggero cambiando OLLAMA_MODEL in agent.py.


───────────────────────────────────────────────────────────────────────────
  COME AVVIARLO (modo più semplice)
───────────────────────────────────────────────────────────────────────────

  1) Apri il programma Ollama (deve restare aperto in background).
     Oppure da terminale:   ollama serve

  2) Apri il Terminale nella cartella MCF e lancia:

         ./start.sh

     Lo script fa tutto da solo:
       • controlla che Ollama risponda
       • crea l'ambiente Python (.venv) se non c'è
       • installa le librerie da requirements.txt
       • avvia il server

  3) Apri il browser su:

         http://localhost:8000

     (la documentazione tecnica delle API è su http://localhost:8000/docs)

  4) Per fermare il server: premi CTRL + C nel Terminale.


───────────────────────────────────────────────────────────────────────────
  AVVIO MANUALE (se start.sh non funziona)
───────────────────────────────────────────────────────────────────────────

  Dal Terminale, dentro la cartella MCF:

      python3 -m venv .venv
      source .venv/bin/activate
      pip install -r requirements.txt
      uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  Assicurati che Ollama sia attivo (ollama serve) e che il modello sia
  scaricato (ollama pull qwen3:14b).


───────────────────────────────────────────────────────────────────────────
  CONFIGURAZIONE EMAIL (file .env)
───────────────────────────────────────────────────────────────────────────

  Nella cartella c'è un file ".env" con due valori:

      SENDGRID_API_KEY=...        ← chiave del servizio SendGrid per le email
      NOTIFICA_EMAIL=...          ← indirizzo che riceve le conferme di prenotazione

  Le prenotazioni inviano una email di conferma a NOTIFICA_EMAIL.
  Se la chiave SendGrid non è valida la prenotazione viene comunque salvata,
  ma l'email non parte (compare un avviso nei log).

  ATTENZIONE: il file .env contiene credenziali. NON va condiviso né messo
  su GitHub (infatti è già escluso tramite .gitignore).


───────────────────────────────────────────────────────────────────────────
  I DATI (da dove vengono)
───────────────────────────────────────────────────────────────────────────

  Al primo avvio, database.py crea assistente.db e lo riempie leggendo i CSV
  dentro la cartella Materiale/:

      • Inventario attrezzatura
      • Roster collaboratori / freelance
      • Tariffe e contatti fornitori

  Se vuoi RICARICARE i dati da zero (perché hai aggiornato i CSV):
      1) chiudi il server
      2) cancella il file assistente.db
      3) riavvia: al prossimo avvio il database viene ricreato dai CSV

  Le prenotazioni invece vengono salvate dentro assistente.db: se cancelli
  il database perdi anche le prenotazioni fatte.


───────────────────────────────────────────────────────────────────────────
  LE PAGINE DEL SITO
───────────────────────────────────────────────────────────────────────────

      /                 Chat con Aura (pagina principale)
      /magazzino.html   Vista del magazzino / inventario
      /studio.html      Calendario e prenotazioni della Sala Studio
      /fornitori.html   Elenco collaboratori e fornitori



───────────────────────────────────────────────────────────────────────────
  In sintesi: apri Ollama → ./start.sh → vai su http://localhost:8000
═══════════════════════════════════════════════════════════════════════════
