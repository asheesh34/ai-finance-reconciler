"""
Pushes our synthetic "internal transaction records" into RewindDB's real
running API as change events, instead of just writing a CSV.

This does the following, against your actual local RewindDB backend
(http://localhost:8080):
  1. Registers a demo user (or logs in if it already exists)
  2. Creates a DatabaseConnection representing a "transactions" source
  3. For each internal transaction record, POSTs a ChangeEvent (INSERT)
     with the transaction fields packed into afterData JSON

After running this, your RewindDB Postgres database's real change_events
table contains these records. reconcile_from_rewinddb.py then reads them
back directly from Postgres to use as the "internal records" side of the
reconciliation, instead of internal_records.csv.

Usage:
    python3 src/push_to_rewinddb.py
"""

import csv
import json
import requests

BASE_URL = "http://localhost:8080/api/v1"

DEMO_EMAIL = "reconciler-demo@example.com"
DEMO_PASSWORD = "ReconcilerDemo123!"
DEMO_DISPLAY_NAME = "Reconciler Demo"

CONNECTION_NAME = "Reconciliation Demo Source"
SCHEMA_NAME = "public"
TABLE_NAME = "transactions"


def register_or_login():
    """Registers the demo user; if it already exists, logs in instead."""
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
        "displayName": DEMO_DISPLAY_NAME,
    })

    if resp.status_code in (200, 201):
        data = resp.json()
        return _extract_token(data)

    # Already registered - log in instead
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
    })
    resp.raise_for_status()
    return _extract_token(resp.json())


def _extract_token(data):
    # Response may or may not be wrapped in a common envelope - handle both shapes
    payload = data.get("data", data) if isinstance(data, dict) else data
    token = payload.get("token") or payload.get("accessToken") or payload.get("jwt")
    if not token:
        raise RuntimeError(f"Could not find auth token in response: {data}")
    return token


def get_or_create_connection(headers):
    """Creates the demo DatabaseConnection, or reuses an existing one with the same name."""
    resp = requests.get(f"{BASE_URL}/connections", headers=headers)
    resp.raise_for_status()
    existing = resp.json()
    if isinstance(existing, dict):
        existing = existing.get("data", existing.get("content", []))
    for conn in existing:
        if conn.get("name") == CONNECTION_NAME:
            return conn["id"]

    resp = requests.post(f"{BASE_URL}/connections", headers=headers, json={
        "name": CONNECTION_NAME,
        "host": "localhost",
        "port": 5432,
        "databaseName": "demo_transactions_source",
        "username": "demo_user",
        "password": "demo_password",
    })
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    return data["id"]


def push_transaction_as_change_event(headers, connection_id, record):
    after_data = json.dumps({
        "transaction_id": record["transaction_id"],
        "date": record["date"],
        "amount": record["amount"],
        "merchant": record["merchant"],
    })

    resp = requests.post(f"{BASE_URL}/change-events", headers=headers, json={
        "connectionId": connection_id,
        "schemaName": SCHEMA_NAME,
        "tableName": TABLE_NAME,
        "primaryKeyValue": record["transaction_id"],
        "operationType": "INSERT",
        "beforeData": None,
        "afterData": after_data,
    })
    resp.raise_for_status()
    return resp.json()


def main():
    print("Authenticating with RewindDB...")
    token = register_or_login()
    headers = {"Authorization": f"Bearer {token}"}

    print("Getting/creating demo connection...")
    connection_id = get_or_create_connection(headers)
    print(f"Using connection: {connection_id}")

    with open("data/internal_records.csv", newline="") as f:
        records = list(csv.DictReader(f))

    print(f"Pushing {len(records)} transaction records as change events...")
    for i, record in enumerate(records, 1):
        push_transaction_as_change_event(headers, connection_id, record)
        if i % 10 == 0 or i == len(records):
            print(f"  {i}/{len(records)} pushed")

    print("Done. These records are now real rows in RewindDB's change_events table.")
    print(f"Connection ID (save this): {connection_id}")


if __name__ == "__main__":
    main()
