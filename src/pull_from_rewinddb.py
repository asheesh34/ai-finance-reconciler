"""
Reads transaction records directly out of RewindDB's own Postgres
database (the change_events table), instead of reading internal_records.csv.

This is the "real data source" half of the RewindDB integration: after
push_to_rewinddb.py has posted records through RewindDB's actual API,
they exist as real rows in change_events with the transaction fields
packed into the after_data JSONB column. This module unpacks that JSON
back into the same row shape reconcile.py already expects, so the rest
of the reconciliation pipeline (matching, agent verification, reporting)
needs no changes at all.

Requires the RewindDB backend's Postgres database to be reachable
(defaults match RewindDB's own application.yml defaults).
"""

import csv
import json
import os
import psycopg2

DB_HOST = os.environ.get("REWINDDB_HOST", "localhost")
DB_PORT = os.environ.get("REWINDDB_PORT", "5432")
DB_NAME = os.environ.get("REWINDDB_DATABASE", "rewinddb")
DB_USER = os.environ.get("REWINDDB_USER", "postgres")
DB_PASSWORD = os.environ.get("REWINDDB_PASSWORD", "postgres")

TABLE_NAME = "transactions"  # must match push_to_rewinddb.py's TABLE_NAME


def fetch_transactions_from_change_events(connection_id=None):
    """
    Queries change_events for INSERT rows against the 'transactions' table,
    unpacks after_data JSON, and returns rows shaped like
    internal_records.csv: transaction_id, date, amount, merchant.

    If connection_id is given, restricts to that specific connection
    (useful when RewindDB tracks more than one source).
    """
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )
    try:
        with conn.cursor() as cur:
            query = """
                SELECT after_data
                FROM change_events
                WHERE table_name = %s AND operation_type = 'INSERT'
            """
            params = [TABLE_NAME]
            if connection_id:
                query += " AND connection_id = %s"
                params.append(connection_id)
            query += " ORDER BY captured_at ASC"

            cur.execute(query, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    records = []
    for (after_data,) in rows:
        # psycopg2 returns jsonb columns already parsed as dict/str depending
        # on driver config - handle both.
        data = after_data if isinstance(after_data, dict) else json.loads(after_data)
        records.append({
            "transaction_id": data["transaction_id"],
            "date": data["date"],
            "amount": str(data["amount"]),
            "merchant": data["merchant"],
        })
    return records


def write_as_csv(records, path="data/internal_records_from_rewinddb.csv"):
    """Writes the fetched records out as a CSV, so reconcile.py can be
    pointed at it exactly like the original synthetic CSV."""
    fieldnames = ["transaction_id", "date", "amount", "merchant"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    return path


if __name__ == "__main__":
    records = fetch_transactions_from_change_events()
    print(f"Fetched {len(records)} transaction records from RewindDB's change_events table.")
    path = write_as_csv(records)
    print(f"Written to {path}")
