"""Pause commune Discord persistante dans PostgreSQL."""
import os, json, psycopg

def connection():
    return psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=8)

def setup(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS rptpfr_discord_pause (id INTEGER PRIMARY KEY, until_at TIMESTAMPTZ NOT NULL)")

def remaining():
    with connection() as conn:
        setup(conn)
        row=conn.execute("SELECT GREATEST(0, EXTRACT(EPOCH FROM (until_at-NOW()))) FROM rptpfr_discord_pause WHERE id=1").fetchone()
        return int(row[0]) if row else 0

def register_429(exc):
    header=exc.headers.get('Retry-After') or exc.headers.get('X-RateLimit-Reset-After')
    try: delay=float(header) if header else 60.0
    except (TypeError,ValueError): delay=60.0
    delay=max(2.,min(delay,86400.))
    with connection() as conn:
        setup(conn)
        conn.execute("INSERT INTO rptpfr_discord_pause (id,until_at) VALUES (1,NOW()+(%s*INTERVAL '1 second')) ON CONFLICT(id) DO UPDATE SET until_at=GREATEST(rptpfr_discord_pause.until_at,EXCLUDED.until_at)",(delay+3,))
    print(f'[DISCORD PROTECTION] 429 : pause persistante et commune {delay:.0f}s.',flush=True)
    return delay
