"""
Generates two synthetic transaction datasets to simulate a real reconciliation
problem: a company's internal transaction records vs. a bank/PG statement.

On purpose, we inject:
  - a few missing records (present in one file, not the other)
  - a few amount mismatches (off by a small amount)
  - a couple of duplicate transaction IDs
so the reconciliation agent has real problems to solve, not a fake 100% match.
"""

import csv
import random
from datetime import datetime, timedelta

random.seed(42)  # reproducible output for demo purposes

NUM_RECORDS = 60
OUTPUT_DIR = "data"

MERCHANTS = ["Zomato", "Swiggy", "Amazon", "Flipkart", "Myntra", "BookMyShow", "Ola", "Uber"]


def make_base_records(n):
    records = []
    start_date = datetime(2026, 8, 1)
    for i in range(1, n + 1):
        txn_id = f"TXN{i:05d}"
        amount = round(random.uniform(100, 5000), 2)
        date = start_date + timedelta(days=random.randint(0, 15))
        merchant = random.choice(MERCHANTS)
        records.append({
            "transaction_id": txn_id,
            "date": date.strftime("%Y-%m-%d"),
            "amount": amount,
            "merchant": merchant,
        })
    return records


def build_internal_and_bank(records):
    internal = [dict(r) for r in records]
    bank = [dict(r) for r in records]

    # 1. Drop a few records from the bank file (payment recorded internally,
    #    but not yet settled / missing from bank statement)
    missing_from_bank = random.sample(bank, 4)
    for r in missing_from_bank:
        bank.remove(r)

    # 2. Drop a few records from the internal file (bank shows a transaction
    #    that was never logged internally — e.g. a manual/offline entry)
    missing_from_internal = random.sample(internal, 3)
    for r in missing_from_internal:
        internal.remove(r)

    # 3. Introduce amount mismatches in the bank file (e.g. bank fee deducted,
    #    partial refund, rounding difference)
    mismatch_candidates = [r for r in bank if r not in missing_from_bank]
    mismatched = random.sample(mismatch_candidates, 5)
    for r in mismatched:
        delta = round(random.choice([-1, 1]) * random.uniform(5, 50), 2)
        r["amount"] = round(r["amount"] + delta, 2)

    # 4. Introduce a couple of duplicate transaction IDs in the bank file
    #    (simulates a double-settlement / retry artifact)
    dup_candidates = [r for r in bank if r not in mismatched]
    dups = random.sample(dup_candidates, 2)
    for r in dups:
        bank.append(dict(r))  # exact duplicate row

    random.shuffle(internal)
    random.shuffle(bank)
    return internal, bank


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    base = make_base_records(NUM_RECORDS)
    internal, bank = build_internal_and_bank(base)

    fieldnames = ["transaction_id", "date", "amount", "merchant"]
    write_csv(f"{OUTPUT_DIR}/internal_records.csv", internal, fieldnames)
    write_csv(f"{OUTPUT_DIR}/bank_statement.csv", bank, fieldnames)

    print(f"Generated {len(internal)} internal records -> {OUTPUT_DIR}/internal_records.csv")
    print(f"Generated {len(bank)} bank records -> {OUTPUT_DIR}/bank_statement.csv")
    print("Injected: missing rows on both sides, amount mismatches, duplicate settlements.")


if __name__ == "__main__":
    main()
