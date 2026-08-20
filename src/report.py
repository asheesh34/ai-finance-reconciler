"""
Ties everything together: runs reconciliation, adds AI explanations to
every unresolved item, and prints/saves a final human-readable report.

Usage:
    python3 src/report.py
"""

import json
from reconcile import reconcile, load_csv
from explain import annotate_result


def build_report(internal_path, bank_path):
    result = reconcile(internal_path, bank_path)
    result = annotate_result(result)
    return result


def print_report(result):
    print("=" * 64)
    print("  AI FINANCE CONTROLLER — RECONCILIATION REPORT")
    print("=" * 64)
    print(f"Total transactions considered: {result['total_considered']}")
    print(f"Matched cleanly:               {len(result['matched'])}")
    print(f"Mismatched (amount differs):   {len(result['mismatched'])}")
    print(f"Unresolved exceptions:         {len(result['exceptions'])}")
    print(f"MATCH RATE: {result['match_rate']}%")
    print("=" * 64)

    if result["mismatched"]:
        print("\nAMOUNT MISMATCHES")
        print("-" * 64)
        for m in result["mismatched"]:
            print(f"[{m['transaction_id']}] diff={m['difference']}")
            print(f"  -> {m['explanation']}\n")

    if result["exceptions"]:
        print("\nUNRESOLVED EXCEPTIONS")
        print("-" * 64)
        for e in result["exceptions"]:
            print(f"[{e['transaction_id']}] {e['type']}")
            print(f"  -> {e['explanation']}\n")

    print("=" * 64)
    print("This system does not guess or force a match. Every unresolved")
    print("item above is left as-is with its likely cause, for a human to")
    print("review and close.")
    print("=" * 64)


def save_report_json(result, path="data/report.json"):
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)


if __name__ == "__main__":
    result = build_report("data/internal_records.csv", "data/bank_statement.csv")
    print_report(result)
    save_report_json(result)
    print(f"\nFull report saved to data/report.json")
