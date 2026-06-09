"""
Configurazione e inizializzazione del database SQLite locale.
Contiene la tabella 'fornitori' con dati mockup per la demo.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "fornitori.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # restituisce righe come dizionari
    return conn


def init_db() -> None:
    """Crea la tabella e inserisce i dati di esempio se il DB non esiste ancora."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fornitori (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            ruolo       TEXT NOT NULL,
            costo_ora   REAL NOT NULL,
            costo_progetto REAL,
            esperienza  TEXT NOT NULL,
            contatto    TEXT
        )
    """)

    # Inserisce i dati solo se la tabella è vuota
    cur.execute("SELECT COUNT(*) FROM fornitori")
    if cur.fetchone()[0] == 0:
        fornitori_mockup = [
            ("Marco Rossi",    "montatore video",  35.0,  800.0,  "5 anni – specializzato in podcast e corporate video", "marco@example.com"),
            ("Giulia Ferretti","montatore video",  45.0, 1200.0,  "8 anni – post-produzione cinematografica e YouTube",   "giulia@example.com"),
            ("Luca Bianchi",   "fonico",           30.0,  600.0,  "4 anni – registrazione in studio e riprese esterne",   "luca@example.com"),
            ("Sara Conti",     "fonico",           50.0, 1500.0,  "10 anni – live sound engineering e post-produzione",   "sara@example.com"),
            ("Andrea Mori",    "operatore video",  28.0,  500.0,  "3 anni – riprese multi-camera e streaming live",       "andrea@example.com"),
            ("Chiara Neri",    "grafica/motion",   40.0,  900.0,  "6 anni – motion graphics e thumbnail per YouTube",    "chiara@example.com"),
        ]
        cur.executemany(
            "INSERT INTO fornitori (nome, ruolo, costo_ora, costo_progetto, esperienza, contatto) VALUES (?,?,?,?,?,?)",
            fornitori_mockup,
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database inizializzato correttamente.")
