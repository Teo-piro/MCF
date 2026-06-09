"""
Inizializzazione del database SQLite locale.
Importa i dati reali dai CSV presenti in MCF/Materiale/:
  - FORNITORI (MOTTA Viviana + WILLOW Production): tariffe e servizi
  - Roster collaboratori: team video/audio/foto
"""

import csv
import re
import sqlite3
from pathlib import Path

BASE_DIR   = Path(__file__).parent
DB_PATH    = BASE_DIR / "assistente.db"

CSV_TARIFFE      = BASE_DIR / "Materiale/FORNITORI - costi e contatti - SET DESIGNER + STUDIO.csv"
CSV_COLLABORATORI = BASE_DIR / "Materiale/Roster collab. video-audio-foto_HACKATON - Francesco.csv"
CSV_ATTREZZATURA = BASE_DIR / "Materiale/invetario/Inventario 2025 67a864ef904c499c816f51188adc8d42.csv"


# ---------------------------------------------------------------------------
# Connessione
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Classificazione attrezzatura
# ---------------------------------------------------------------------------
# Il segnale più affidabile è il PREFISSO del CODICE, non il nome.
# (es. "Batteria fotocamera Lumix" NON è una videocamera, ma una batteria).
# Le regole sono ordinate dalla più specifica alla più generica: vince la prima.
# Ogni regola assegna una MICRO-categoria (tipo) e una MACRO-categoria (gruppo).

CLASSIFICAZIONE_REGOLE: list[tuple[str, str, str]] = [
    # prefisso codice           tipo (micro)            macro
    # --- Video / ottiche ---
    ("ST-",         "Sala Studio",            "Studio"),
    ("VC-",         "Videocamera",            "Video"),
    ("OB-",         "Obiettivo",              "Video"),
    ("BT-",         "Batteria",               "Video"),
    # --- Stativi/cavalletti specifici (PRIMA di SC- generico) ---
    ("SC-MIC-",     "Stativo microfono",      "Supporti"),
    ("SC-TFG-",     "Stativo fondale",        "Supporti"),
    ("SC-TFP-",     "Stativo fondale",        "Supporti"),
    ("SC-PFG-",     "Palo fondale",           "Supporti"),
    ("SC-PFP-",     "Palo fondale",           "Supporti"),
    ("SC-TPL-",     "Stativo teleprompter",   "Supporti"),
    ("SC-GDX-",     "Stativo luce",           "Supporti"),
    ("SC-LU-NWR-",  "Stativo luce",           "Supporti"),
    ("SC-NWR-",     "Stativo luce",           "Supporti"),
    ("SC-KF-",      "Cavalletto videocamera", "Supporti"),
    ("SC-MFT-",     "Cavalletto videocamera", "Supporti"),
    ("SC-RLE-",     "Cavalletto videocamera", "Supporti"),
    ("SC-ISY-",     "Cavalletto videocamera", "Supporti"),
    ("SC-",         "Stativo/Cavalletto",     "Supporti"),  # fallback SC
    # --- Cavi specifici (PRIMA di C- generico) ---
    ("C-MIC-",      "Cavo microfono",         "Cavi"),
    ("C-LU-",       "Cavo luce",              "Cavi"),
    ("C-RC-",       "Alimentatore",           "Cavi"),
    ("HDMI-",       "Cavo HDMI",              "Cavi"),
    ("USBC-",       "Cavo USB-C",             "Cavi"),
    ("XLR-",        "Cavo XLR",               "Cavi"),
    ("C-",          "Cavo",                   "Cavi"),       # fallback cavi
    # --- Audio ---
    ("MIC-",        "Microfono",              "Audio"),
    ("RC-",         "Mixer audio",            "Audio"),
    ("CF-",         "Cuffie",                 "Audio"),
    # --- Luci ---
    ("LU-",         "Luce",                   "Luci"),
    ("PL-",         "Pannello LED",           "Luci"),
    ("SB-",         "Softbox",                "Luci"),
    ("L-",          "Lampada",                "Luci"),
    # --- Storage ---
    ("MSD-",        "Scheda MicroSD",         "Storage"),
    ("SD-",         "Scheda SD",              "Storage"),
    ("SSD-",        "SSD",                    "Storage"),
    ("HSS-",        "Hard Disk",              "Storage"),
    # --- Accessori ---
    ("CRG-",        "Caricatore",             "Accessori"),
    ("TPL-",        "Teleprompter",           "Accessori"),
    ("TE-",         "Telecomando",            "Accessori"),
    ("TAB-",        "Tablet",                 "Accessori"),
    # --- Arredamento ---
    ("FD-",         "Fondale",                "Arredo"),
    ("TAV-",        "Tavolo",                 "Arredo"),
]


def classifica(codice: str) -> tuple[str, str]:
    """
    Classifica un elemento dal prefisso del suo codice.
    Ritorna (tipo, macro). Se nessuna regola corrisponde → ('Altro', 'Altro').
    """
    codice = (codice or "").upper().strip()
    for prefisso, tipo, macro in CLASSIFICAZIONE_REGOLE:
        if codice.startswith(prefisso):
            return tipo, macro
    return "Altro", "Altro"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_costo(testo: str) -> float | None:
    """Converte '€ 1.000,00' → 1000.0"""
    if not testo:
        return None
    clean = re.sub(r"[€\s.]", "", testo).replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def _importa_tariffe(cur: sqlite3.Cursor) -> int:
    """Legge il CSV fornitori e popola la tabella 'tariffe'. Ritorna il numero di righe inserite."""
    if not CSV_TARIFFE.exists():
        print(f"[WARN] CSV tariffe non trovato: {CSV_TARIFFE}")
        return 0

    righe_inserite = 0
    fornitore_corrente = ""
    email_corrente = ""

    with open(CSV_TARIFFE, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for riga in reader:
            if not any(c.strip() for c in riga):
                continue  # riga vuota

            prima = riga[0].strip()

            # Rileva intestazione di sezione fornitore (riga con nome proprio o "WILLOW")
            # Euristica: prima cella non è un servizio noto e contiene più di 3 caratteri
            servizi_noti = {
                "CONSULENZA","3D + RENDER","MOODBOARD","PLANIMETRIA","SET DESIGN",
                "RICERCA PROPS","PACK DESIGN","REVISIONI / MODIFICHE",
                "AFFITTO SALA intera giornata","AFFITTO SALA mezza giornata",
                "NOME","RUOLO",
            }
            if prima and prima not in servizi_noti and not prima.startswith("€"):
                # Potrebbe essere una riga header del fornitore
                fornitore_corrente = prima
                # Cerca l'email tra le celle
                email_corrente = next(
                    (c.strip() for c in riga if "@" in c), ""
                )
                continue

            # Riga di servizio: [SERVIZIO, DETTAGLI, COSTO, ...]
            servizio = prima
            dettagli = riga[1].strip() if len(riga) > 1 else ""
            costo_txt = riga[2].strip() if len(riga) > 2 else ""

            if not servizio or not costo_txt:
                continue

            costo_val = _parse_costo(costo_txt)
            cur.execute(
                "INSERT INTO tariffe (fornitore, servizio, dettagli, costo_testo, costo_valore, email) "
                "VALUES (?,?,?,?,?,?)",
                (fornitore_corrente, servizio, dettagli, costo_txt, costo_val, email_corrente),
            )
            righe_inserite += 1

    return righe_inserite


def _importa_collaboratori(cur: sqlite3.Cursor) -> int:
    """Legge il CSV roster e popola la tabella 'collaboratori'. Ritorna il numero di righe inserite."""
    if not CSV_COLLABORATORI.exists():
        print(f"[WARN] CSV collaboratori non trovato: {CSV_COLLABORATORI}")
        return 0

    righe_inserite = 0

    with open(CSV_COLLABORATORI, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header_trovato = False
        for riga in reader:
            if not any(c.strip() for c in riga):
                continue  # riga vuota

            # Salta finché non troviamo la riga header "NOME,RUOLO,..."
            if not header_trovato:
                if riga[0].strip().upper() == "NOME":
                    header_trovato = True
                continue

            nome     = riga[0].strip() if len(riga) > 0 else ""
            ruolo    = riga[1].strip() if len(riga) > 1 else ""
            domicilio = riga[2].strip() if len(riga) > 2 else ""
            email    = riga[3].strip() if len(riga) > 3 else ""
            telefono = riga[4].strip() if len(riga) > 4 else ""
            hw_sw    = riga[5].strip() if len(riga) > 5 else ""
            note     = riga[6].strip() if len(riga) > 6 else ""
            status   = riga[7].strip() if len(riga) > 7 else ""

            if not nome:
                continue

            cur.execute(
                "INSERT INTO collaboratori "
                "(nome, ruolo, domicilio, email, telefono, hardware_software, note, status) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (nome, ruolo, domicilio, email, telefono, hw_sw, note, status),
            )
            righe_inserite += 1

    return righe_inserite


def _importa_attrezzatura(cur: sqlite3.Cursor) -> int:
    """Legge il CSV inventario e popola la tabella 'attrezzatura'. Ritorna il numero di righe inserite."""
    if not CSV_ATTREZZATURA.exists():
        print(f"[WARN] CSV attrezzatura non trovato: {CSV_ATTREZZATURA}")
        return 0

    righe_inserite = 0

    with open(CSV_ATTREZZATURA, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = None
        for i, riga in enumerate(reader):
            # Prima riga = header
            if i == 0:
                header = riga
                continue

            if not any(c.strip() for c in riga):
                continue  # riga vuota

            # Mappa le colonne in base all'header (colonne potrebbero avere spazi)
            if header:
                data = {}
                for col, val in zip(header, riga):
                    data[col.strip()] = val.strip()

                codice      = data.get("Codice", "").strip()
                nome        = data.get("Articolo", "").strip()  # Colonna senza lo spazio iniziale
                descrizione = data.get("Descrizione", "").strip()
                categoria   = data.get("Categoria", "").strip()
                posizione   = data.get("Posizione Live", "").strip()  # Colonna senza lo spazio iniziale
                stato       = data.get("Stato", "").strip()
                appunti     = data.get("Appunti", "").strip()

                if not codice:
                    continue

                # Classifica automaticamente dal prefisso del codice
                tipo, macro = classifica(codice)

                try:
                    cur.execute(
                        "INSERT OR IGNORE INTO attrezzatura "
                        "(codice, nome, descrizione, categoria, posizione, stato, appunti, tipo, macro) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (codice, nome, descrizione, categoria, posizione, stato, appunti, tipo, macro),
                    )
                    righe_inserite += 1
                except sqlite3.IntegrityError:
                    pass  # Duplicato ignorato

    return righe_inserite


# ---------------------------------------------------------------------------
# Init pubblica
# ---------------------------------------------------------------------------

def init_db(forza_reimport: bool = False) -> None:
    """
    Crea le tabelle e importa i CSV se il DB non esiste o se forza_reimport=True.
    """
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tariffe (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fornitore     TEXT NOT NULL,
            servizio      TEXT NOT NULL,
            dettagli      TEXT,
            costo_testo   TEXT NOT NULL,
            costo_valore  REAL,
            email         TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS collaboratori (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            nome              TEXT NOT NULL,
            ruolo             TEXT NOT NULL,
            domicilio         TEXT,
            email             TEXT,
            telefono          TEXT,
            hardware_software TEXT,
            note              TEXT,
            status            TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attrezzatura (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            codice       TEXT NOT NULL UNIQUE,
            nome         TEXT NOT NULL,
            descrizione  TEXT,
            categoria    TEXT,
            posizione    TEXT,
            stato        TEXT,
            appunti      TEXT,
            tipo         TEXT,
            macro        TEXT
        )
    """)

    # Prenotazioni attrezzatura: una riga = un singolo pezzo impegnato.
    # Le prenotazioni multi-pezzo (es. "2 SD") condividono lo stesso gruppo_id.
    # Date in formato ISO (AAAA-MM-GG); orari opzionali (HH:MM) per il caso intra-giornata.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prenotazioni (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            gruppo_id     TEXT NOT NULL,
            codice        TEXT NOT NULL,
            prenotato_da  TEXT,
            progetto      TEXT,
            data_inizio   TEXT NOT NULL,
            data_fine     TEXT NOT NULL,
            ora_inizio    TEXT,
            ora_fine      TEXT,
            note          TEXT,
            creato_il     TEXT,
            FOREIGN KEY (codice) REFERENCES attrezzatura(codice)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pren_codice ON prenotazioni(codice)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pren_date ON prenotazioni(data_inizio, data_fine)")

    # Importa solo se le tabelle sono vuote o se richiesto
    cur.execute("SELECT COUNT(*) FROM tariffe")
    if forza_reimport or cur.fetchone()[0] == 0:
        cur.execute("DELETE FROM tariffe")
        n = _importa_tariffe(cur)
        print(f"  → Importate {n} tariffe da CSV.")

    cur.execute("SELECT COUNT(*) FROM collaboratori")
    if forza_reimport or cur.fetchone()[0] == 0:
        cur.execute("DELETE FROM collaboratori")
        n = _importa_collaboratori(cur)
        print(f"  → Importati {n} collaboratori da CSV.")

    # Assicura che la Sala Studio esista sempre
    cur.execute("SELECT COUNT(*) FROM attrezzatura WHERE codice='ST-STUDIO-001'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT OR IGNORE INTO attrezzatura (codice, nome, tipo, macro, stato) VALUES (?,?,?,?,?)",
            ("ST-STUDIO-001", "Sala Studio Flatmates", "Sala Studio", "Studio", "Disponibile"),
        )

    cur.execute("SELECT COUNT(*) FROM attrezzatura")
    if forza_reimport or cur.fetchone()[0] == 0:
        cur.execute("DELETE FROM attrezzatura")
        n = _importa_attrezzatura(cur)
        print(f"  → Importate {n} attrezzature da CSV.")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    print("Inizializzazione database...")
    init_db(forza_reimport=True)
    print("Fatto.")
