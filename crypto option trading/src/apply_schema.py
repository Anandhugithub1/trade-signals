"""
Apply (or update) the crypto_option_signals table in Supabase.

Supabase's REST client cannot run raw DDL (CREATE TABLE / ALTER). This script
connects straight to the underlying Postgres and executes schema/*.sql.

You need the DB connection string (Supabase Dashboard -> Project Settings ->
Database -> Connection string -> URI). Provide it as an env var:

    export SUPABASE_DB_URL="postgresql://postgres:[PASSWORD]@db.<ref>.supabase.co:5432/postgres"
    python src/apply_schema.py

If psycopg isn't installed or SUPABASE_DB_URL isn't set, the script prints the
SQL and tells you to paste it into the Supabase SQL editor -- so it is always
safe to run and never leaves you stuck.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema" / "crypto_option_signals.sql"


def _manual_instructions(sql: str) -> None:
    print("\n" + "=" * 70)
    print("Could not apply automatically. Paste this into the Supabase SQL")
    print("editor (Dashboard -> SQL Editor -> New query -> Run):")
    print("=" * 70)
    print(sql)


def main() -> int:
    if not SCHEMA_FILE.exists():
        print(f"Schema file not found: {SCHEMA_FILE}")
        return 1
    sql = SCHEMA_FILE.read_text(encoding="utf-8")

    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL is not set.")
        _manual_instructions(sql)
        return 0

    try:
        import psycopg  # psycopg 3
    except ImportError:
        try:
            import psycopg2 as psycopg  # type: ignore
        except ImportError:
            print("Neither psycopg nor psycopg2 is installed "
                  "(`pip install 'psycopg[binary]'`).")
            _manual_instructions(sql)
            return 0

    try:
        print(f"Connecting to Supabase Postgres and applying {SCHEMA_FILE.name} ...")
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        print("[OK] crypto_option_signals schema applied / up to date.")
        return 0
    except Exception as e:  # noqa: BLE001 -- surface any DB error clearly
        print(f"[ERROR] Applying schema failed: {e}")
        _manual_instructions(sql)
        return 1


if __name__ == "__main__":
    sys.exit(main())
