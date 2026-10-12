"""Database layer: schema + mock data ."""
import sqlite3

SCHEMA = """
CREATE TABLE containers (id TEXT PRIMARY KEY);
CREATE TABLE inventory (
    sku TEXT PRIMARY KEY, name TEXT NOT NULL,
    qty INTEGER NOT NULL CHECK (qty >= 0), threshold INTEGER NOT NULL);
CREATE TABLE staff (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE orders (
    id TEXT PRIMARY KEY, customer TEXT, sku TEXT, qty INTEGER, box TEXT,
    container_id TEXT, status TEXT NOT NULL
        CHECK (status IN ('Pending','Departed','Customs On Hold','Complete')),
    expected_departure TEXT NOT NULL);
CREATE TABLE exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('Low inventory','Delayed order','Data quality')),
    severity TEXT NOT NULL CHECK (severity IN ('Low','Medium','High')),
    status TEXT NOT NULL DEFAULT 'Open'
        CHECK (status IN ('Open','Assigned','In Progress','Resolved','Escalated')),
    detected_at TEXT NOT NULL,
    owner_id INTEGER REFERENCES staff(id),
    order_id TEXT, sku TEXT, impact TEXT NOT NULL, notes TEXT DEFAULT '');
CREATE TABLE exception_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exception_id INTEGER NOT NULL REFERENCES exceptions(id),
    at TEXT NOT NULL, text TEXT NOT NULL);
"""

CONTAINERS = ["C-1001", "C-1002", "C-1003"]
INVENTORY = [
    ("SKU-101", "Rice 5 kg", 140, 50), ("SKU-102", "Soy sauce 1 L", 18, 40),
    ("SKU-103", "Egg noodles", 22, 30), ("SKU-104", "Oolong tea", 200, 60),
    ("SKU-105", "Cooking oil 2 L", 75, 40), ("SKU-106", "Cane sugar", 9, 25)]
STAFF = [(1, "Kai Wong", "Inventory staff"), (2, "Mina Lau", "Customer service"),
         (3, "Raj Patel", "System administrator"), (4, "Dana Cho", "Operations manager")]
ORDERS = [
    ("O-2001", "Harbour Mart", "SKU-101", 120, "B-01", "C-1001", "Pending", "2026-10-09T10:00"),
    ("O-2002", "Kowloon Retail", "SKU-102", 80, "B-02", "C-1001", "Departed", "2026-10-10T10:00"),
    ("O-2003", "Lantau Foods", "SKU-103", 40, "B-03", "C-1002", "Customs On Hold", "2026-10-10T08:00"),
    ("O-2004", "Pearl Trading", "SKU-106", 60, "B-04", "C-1003", "Pending", "2026-10-11T16:00"),
    ("O-2005", "Sai Kung Goods", "SKU-104", 25, "B-05", "C-9999", "Pending", "2026-10-14T10:00"),
    ("O-2006", "", "SKU-105", 30, "B-06", "C-1002", "Pending", "2026-10-15T10:00"),
    ("O-2007", "Wan Chai Deli", "SKU-102", 30, "B-07", "C-1002", "Complete", "2026-10-05T10:00"),
    ("O-2008", "Central Pantry", "SKU-103", 70, "B-08", "C-1002", "Pending", "2026-10-14T09:00")]


def connect(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn, with_seed=True):
    conn.executescript(SCHEMA)
    if with_seed:
        conn.executemany("INSERT INTO containers VALUES (?)", [(c,) for c in CONTAINERS])
        conn.executemany("INSERT INTO inventory VALUES (?,?,?,?)", INVENTORY)
        conn.executemany("INSERT INTO staff VALUES (?,?,?)", STAFF)
        conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)", ORDERS)
    conn.commit()
    return conn
