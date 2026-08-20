"""
Core reconciliation engine.

Matches internal_records.csv against bank_statement.csv on transaction_id,
then classifies each pair as:

  MATCHED     - same transaction_id, amount matches exactly (within tolerance)
  MISMATCHED  - same transaction_id exists on both sides, but amount differs
  MISSING_IN_BANK      - present internally, not found in bank statement
  MISSING_IN_INTERNAL  - present in bank statement, not found internally
  DUPLICATE_IN_BANK    - transaction_id appears more than once in bank statement

Outputs a match-rate summary plus a structured exception list, which
explain.py then turns into plain-English reasons.
"""

import csv
from collections import defaultdict

AMOUNT_TOLERANCE = 0.01  # paise-level rounding tolerance, not a real mismatch


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def index_by_id(records):
    """Group records by transaction_id (a list, to catch duplicates)."""
    index = defaultdict(list)
    for r in records:
        index[r["transaction_id"]].append(r)
    return index


def reconcile(internal_path, bank_path):
    internal = load_csv(internal_path)
    bank = load_csv(bank_path)

    internal_idx = index_by_id(internal)
    bank_idx = index_by_id(bank)

    all_ids = set(internal_idx.keys()) | set(bank_idx.keys())

    matched = []
    mismatched = []
    exceptions = []  # missing / duplicate cases

    for txn_id in sorted(all_ids):
        in_recs = internal_idx.get(txn_id, [])
        bank_recs = bank_idx.get(txn_id, [])

        # Duplicate in bank statement
        if len(bank_recs) > 1:
            exceptions.append({
                "transaction_id": txn_id,
                "type": "DUPLICATE_IN_BANK",
                "internal": in_recs[0] if in_recs else None,
                "bank": bank_recs,
            })
            continue

        # Missing on one side
        if in_recs and not bank_recs:
            exceptions.append({
                "transaction_id": txn_id,
                "type": "MISSING_IN_BANK",
                "internal": in_recs[0],
                "bank": None,
            })
            continue

        if bank_recs and not in_recs:
            exceptions.append({
                "transaction_id": txn_id,
                "type": "MISSING_IN_INTERNAL",
                "internal": None,
                "bank": bank_recs[0],
            })
            continue

        # Present on both sides - compare amount
        i_amt = float(in_recs[0]["amount"])
        b_amt = float(bank_recs[0]["amount"])

        if abs(i_amt - b_amt) <= AMOUNT_TOLERANCE:
            matched.append({
                "transaction_id": txn_id,
                "internal": in_recs[0],
                "bank": bank_recs[0],
            })
        else:
            mismatched.append({
                "transaction_id": txn_id,
                "type": "AMOUNT_MISMATCH",
                "internal": in_recs[0],
                "bank": bank_recs[0],
                "difference": round(b_amt - i_amt, 2),
            })

    total_considered = len(matched) + len(mismatched) + len(exceptions)
    match_rate = (len(matched) / total_considered * 100) if total_considered else 0.0

    return {
        "matched": matched,
        "mismatched": mismatched,
        "exceptions": exceptions,
        "match_rate": round(match_rate, 1),
        "total_considered": total_considered,
    }


def print_summary(result):
    print("=" * 60)
    print("RECONCILIATION SUMMARY")
    print("=" * 60)
    print(f"Total unique transaction IDs considered: {result['total_considered']}")
    print(f"Matched:               {len(result['matched'])}")
    print(f"Mismatched (amount):   {len(result['mismatched'])}")
    print(f"Exceptions (unresolved): {len(result['exceptions'])}")
    print(f"Match rate: {result['match_rate']}%")
    print("=" * 60)

    if result["mismatched"]:
        print("\n--- Amount Mismatches ---")
        for m in result["mismatched"]:
            print(f"  {m['transaction_id']}: internal={m['internal']['amount']} "
                  f"bank={m['bank']['amount']} diff={m['difference']}")

    if result["exceptions"]:
        print("\n--- Exceptions ---")
        for e in result["exceptions"]:
            print(f"  {e['transaction_id']}: {e['type']}")


if __name__ == "__main__":
    result = reconcile("data/internal_records.csv", "data/bank_statement.csv")
    print_summary(result)
