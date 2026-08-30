"""
Ties everything together: runs reconciliation, adds AI explanations to
every unresolved item, and prints/saves a final human-readable report.

Usage:
    python3 src/report.py
"""

import json
from reconcile import reconcile, load_csv
from explain import annotate_result
from agent import run_agent_verification


def build_report(internal_path, bank_path):
    result = reconcile(internal_path, bank_path)
    result = annotate_result(result)
    result = run_agent_verification(result)
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
    print("-" * 64)
    print(f"AI AGENT independently reviewed {result['agent_total_reviewed']} records")
    print(f"  Deferred to human (low confidence): {result['agent_deferrals']} ({result['agent_deferral_rate']}%)")
    print(f"  Auto-resolved and agreed with verified rules: {result['agent_agreements']}")
    print(f"AGENT AGREEMENT RATE (of auto-resolved cases): {result['agent_agreement_rate']}%")
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

    all_reviewed = result["matched"] + result["mismatched"] + result["exceptions"]

    deferred_items = [item for item in all_reviewed if item.get("agent_deferred")]
    if deferred_items:
        print("\nDEFERRED TO HUMAN REVIEW (agent confidence too low to auto-resolve)")
        print("-" * 64)
        for d in deferred_items:
            print(f"[{d['transaction_id']}] rules said {d['_ground_truth']}, "
                  f"agent leaned toward {d['agent_raw_label']} (confidence {d['agent_confidence']})")
            print(f"  agent reasoning: {d['agent_reasoning']}\n")

    disagreements = [item for item in all_reviewed
                     if not item.get("agent_deferred") and not item.get("agent_agrees", True)]
    if disagreements:
        print("\nAGENT DISAGREEMENTS (agent's independent view vs. verified rules)")
        print("-" * 64)
        for d in disagreements:
            print(f"[{d['transaction_id']}] rules said {d['_ground_truth']}, "
                  f"agent said {d['agent_label']} (confidence {d['agent_confidence']})")
            print(f"  agent reasoning: {d['agent_reasoning']}\n")

    print("=" * 64)
    print("This system does not guess or force a match. Every unresolved")
    print("item above is left as-is with its likely cause, for a human to")
    print("review and close.")
    print("=" * 64)


def save_report_json(result, path="data/report.json"):
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run reconciliation and generate the final report."
    )
    parser.add_argument(
        "--source", choices=["synthetic", "rewinddb"], default="synthetic",
        help=("Which internal_records source to use: 'synthetic' reads "
              "data/internal_records.csv (fake data), 'rewinddb' reads "
              "data/internal_records_from_rewinddb.csv (real data pulled "
              "from a running RewindDB instance via pull_from_rewinddb.py).")
    )
    args = parser.parse_args()

    internal_path = (
        "data/internal_records_from_rewinddb.csv" if args.source == "rewinddb"
        else "data/internal_records.csv"
    )

    print(f"Using internal records source: {internal_path}\n")
    result = build_report(internal_path, "data/bank_statement.csv")
    print_report(result)
    save_report_json(result)
    print(f"\nFull report saved to data/report.json")
