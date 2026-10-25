import sqlite3

con = sqlite3.connect("opsiq_dev.db")
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)

for t in ["approval_actions", "system_settings", "audit_log", "agent_metrics"]:
    if t in tables:
        count = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"Table {t}: {count} rows")
