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
from datetime import datetime
from collections import defaultdict

AMOUNT_TOLERANCE = 0.01     # paise-level rounding tolerance, not a real mismatch
SETTLEMENT_DELAY_DAYS = 5   # date differences within this window are normal settlement lag
PARTIAL_REFUND_THRESHOLD = 0.05  # bank amount this much lower suggests a refund, not a fee


def normalize_merchant(name):
    """Loosely normalize a merchant label so 'ZOMATO*ORDER' and 'Zomato'
    are recognized as the same merchant, without needing an exact string match."""
    return "".join(ch for ch in name.upper() if ch.isalnum())


def merchant_names_related(a, b):
    na, nb = normalize_merchant(a), normalize_merchant(b)
    return na in nb or nb in na


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

        # Present on both sides - compare amount, date, and merchant name
        internal_rec, bank_rec = in_recs[0], bank_recs[0]
        i_amt = float(internal_rec["amount"])
        b_amt = float(bank_rec["amount"])
        amt_diff = round(b_amt - i_amt, 2)

        i_date = datetime.strptime(internal_rec["date"], "%Y-%m-%d")
        b_date = datetime.strptime(bank_rec["date"], "%Y-%m-%d")
        date_gap = abs((b_date - i_date).days)

        merchant_ok = merchant_names_related(internal_rec["merchant"], bank_rec["merchant"])

        amount_ok = abs(amt_diff) <= AMOUNT_TOLERANCE
        date_ok = date_gap <= SETTLEMENT_DELAY_DAYS

        if amount_ok and date_ok and merchant_ok:
            matched.append({
                "transaction_id": txn_id,
                "internal": internal_rec,
                "bank": bank_rec,
            })
        elif amount_ok and not date_ok and merchant_ok:
            # Amount and merchant line up, only the date is off - this is a
            # normal settlement delay, not a real problem. Still matched,
            # but flagged for visibility.
            matched.append({
                "transaction_id": txn_id,
                "internal": internal_rec,
                "bank": bank_rec,
                "note": f"Matched with {date_gap}-day settlement delay",
            })
        elif not amount_ok and abs(amt_diff) / i_amt >= PARTIAL_REFUND_THRESHOLD and amt_diff < 0:
            # Bank amount meaningfully lower than internal - likely a
            # partial refund, distinct from a small fee/rounding mismatch.
            mismatched.append({
                "transaction_id": txn_id,
                "type": "LIKELY_PARTIAL_REFUND",
                "internal": internal_rec,
                "bank": bank_rec,
                "difference": amt_diff,
            })
        elif not amount_ok:
            mismatched.append({
                "transaction_id": txn_id,
                "type": "AMOUNT_MISMATCH",
                "internal": internal_rec,
                "bank": bank_rec,
                "difference": amt_diff,
            })
        elif not merchant_ok:
            mismatched.append({
                "transaction_id": txn_id,
                "type": "MERCHANT_NAME_MISMATCH",
                "internal": internal_rec,
                "bank": bank_rec,
                "difference": 0.0,
            })
        else:
            # Fallback - shouldn't normally hit this, but keep it visible
            # instead of silently dropping the record.
            mismatched.append({
                "transaction_id": txn_id,
                "type": "UNCLASSIFIED_MISMATCH",
                "internal": internal_rec,
                "bank": bank_rec,
                "difference": amt_diff,
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
        print("\n--- Mismatches ---")
        for m in result["mismatched"]:
            print(f"  {m['transaction_id']} [{m['type']}]: internal={m['internal']['amount']} "
                  f"bank={m['bank']['amount']} diff={m['difference']}")

    if result["exceptions"]:
        print("\n--- Exceptions ---")
        for e in result["exceptions"]:
            print(f"  {e['transaction_id']}: {e['type']}")


if __name__ == "__main__":
    result = reconcile("data/internal_records.csv", "data/bank_statement.csv")
    print_summary(result)
