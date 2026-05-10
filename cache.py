import sqlite3, time
from typing import Optional
from config import ReceiverInfo


DB_PATH = "receiver_cache.db"

# ── Init ───────────────────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS receiver_cache (
            company_key  TEXT PRIMARY KEY,
            company_name TEXT,
            receiver     TEXT,          -- ReceiverInfo serialized as JSON
            fetched_at   INTEGER
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_key ON receiver_cache(company_key)")
    con.commit()
    con.close()

# ── Read ───────────────────────────────────────────────────────────────────────
def get_receiver(company_name: str) -> Optional[ReceiverInfo]:
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT receiver FROM receiver_cache WHERE company_key = ?",
        (company_name.lower().strip(),)
    ).fetchone()
    con.close()

    if row:
        return ReceiverInfo.model_validate_json(row[0])   # JSON → ReceiverInfo ✅
    return None

# ── Write ──────────────────────────────────────────────────────────────────────
def save_receiver(receiver: ReceiverInfo):
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        INSERT OR REPLACE INTO receiver_cache
        (company_key, company_name, receiver, fetched_at)
        VALUES (?, ?, ?, ?)
    """, (
        receiver.company_name.lower().strip(),
        receiver.company_name,
        receiver.model_dump_json(),               # ReceiverInfo → JSON ✅
        int(time.time())
    ))
    con.commit()
    con.close()

# ── Save a list at once ────────────────────────────────────────────────────────
def save_receivers(receivers: list[ReceiverInfo]):
    con = sqlite3.connect(DB_PATH)
    con.executemany("""
        INSERT OR REPLACE INTO receiver_cache
        (company_key, company_name, receiver, fetched_at)
        VALUES (?, ?, ?, ?)
    """, [
        (
            r.company_name.lower().strip(),
            r.company_name,
            r.model_dump_json(),
            int(time.time())
        )
        for r in receivers
    ])
    con.commit()
    con.close()



