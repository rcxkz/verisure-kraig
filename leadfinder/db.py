import sqlite3
from .config import DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS crimes (
    id INTEGER PRIMARY KEY,           -- police.uk crime id
    category TEXT, month TEXT, lat REAL, lng REAL,
    street TEXT, town TEXT, outcome TEXT
);
CREATE TABLE IF NOT EXISTS crime_fetches (
    town TEXT, month TEXT, fetched_at TEXT, PRIMARY KEY (town, month)
);
CREATE TABLE IF NOT EXISTS sales (
    txid TEXT PRIMARY KEY, price INTEGER, date TEXT, postcode TEXT,
    ptype TEXT, new_build TEXT, tenure TEXT, paon TEXT, saon TEXT,
    street TEXT, lr_town TEXT, lat REAL, lng REAL, town TEXT
);
CREATE TABLE IF NOT EXISTS postcodes (
    postcode TEXT PRIMARY KEY, lat REAL, lng REAL
);
CREATE TABLE IF NOT EXISTS news (
    link TEXT PRIMARY KEY, title TEXT, source TEXT, published TEXT,
    town TEXT, street TEXT, fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS businesses (
    source TEXT, ext_id TEXT, name TEXT, btype TEXT, address TEXT,
    postcode TEXT, lat REAL, lng REAL, signal TEXT, signal_date TEXT,
    first_seen TEXT, last_seen TEXT,
    PRIMARY KEY (source, ext_id)
);
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT,        -- 'street' or 'business'
    key TEXT,         -- 'STREET|Town' or 'source:ext_id'
    outcome TEXT, note TEXT, ts TEXT
);
"""


def connect(path=None):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path or DATA_DIR / "leads.db")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for col in ("phone TEXT", "chain INTEGER"):
        try:
            conn.execute(f"ALTER TABLE businesses ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass  # already there
    return conn


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params)]
