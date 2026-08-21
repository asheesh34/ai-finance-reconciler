# AI Finance Controller — Reconciliation Agent

Built for the Razorpay AI Buildathon — Track 04: AI Finance Controller.

## The problem

Every business has two versions of the truth for its money: what its own
system says happened, and what the bank / payment gateway says happened.
Someone has to manually compare these two lists, line by line, to catch
missing settlements, amount mismatches, and duplicate charges. This is
still done by hand at most companies.

## What this does

This is a reconciliation agent that:

1. Takes two transaction datasets — an internal record set and a bank
   statement (synthetic data, 50+ records, with realistic errors
   deliberately injected).
2. Matches records by transaction ID, then compares amount, date, and
   merchant name — not just a raw amount check.
3. Classifies every record as **matched**, or one of several distinct
   mismatch/exception types:
   - `AMOUNT_MISMATCH` — a small unexplained amount difference
   - `LIKELY_PARTIAL_REFUND` — bank amount meaningfully lower than internal
   - `MERCHANT_NAME_MISMATCH` — same transaction, bank uses a different
     label for the merchant
   - `MISSING_IN_BANK` / `MISSING_IN_INTERNAL` — present on only one side
   - `DUPLICATE_IN_BANK` — same transaction ID settled more than once

   A settlement delay of a few days (date differs, amount and merchant
   match) is still counted as **matched** with a note — that's normal
   behavior, not a real problem.
4. Uses Claude to generate a plain-English explanation for every
   mismatch and exception — not just a status code.
5. Reports an honest **match rate**, with the full list of what it could
   not resolve and why.

This system does not force a match or hide failures. A 100% match rate
on synthetic data with injected errors would mean something is wrong
with the matching logic, not that reconciliation is "solved."

## Example output

```
============================================================
  AI FINANCE CONTROLLER — RECONCILIATION REPORT
============================================================
Total transactions considered: 60
Matched cleanly:               47
Mismatched (amount differs):   4
Unresolved exceptions:         9
MATCH RATE: 78.3%
============================================================

AMOUNT MISMATCHES
------------------------------------------------------------
[TXN00007] diff=-16.19
  -> Likely a bank processing fee or gateway charge deducted
     before settlement.

UNRESOLVED EXCEPTIONS
------------------------------------------------------------
[TXN00027] MISSING_IN_BANK
  -> This transaction was recorded internally but has not yet
     appeared in the bank statement — likely a delayed
     settlement. Check again in the next settlement cycle.
```

## How it works

| File | Purpose |
|---|---|
| `src/generate_data.py` | Generates two synthetic CSVs (internal records + bank statement) with deliberately injected missing rows, amount mismatches, and duplicates. |
| `src/reconcile.py` | Core matching engine — compares the two datasets by transaction ID and amount, classifies every record. |
| `src/explain.py` | Calls the Claude API to explain each mismatch/exception in plain English. |
| `src/report.py` | Combines the above into one final report (console output + `data/report.json`). |

## Running it

```bash
pip install -r requirements.txt

export ANTHROPIC_API_KEY=your_key_here

# 1. Generate synthetic data
python3 src/generate_data.py

# 2. Run the full reconciliation + AI explanation report
python3 src/report.py
```

Output is printed to the console and saved to `data/report.json`.

## Design notes

- **Matching, not the AI, decides correctness.** The core matching logic
  (transaction ID + amount comparison) is deterministic code, not an LLM
  call — reconciliation numbers need to be exact and reproducible. The
  AI is used specifically where it adds value: explaining *why* something
  didn't match, in language a human can act on.
- **Tolerance for rounding, not for real mismatches.** A configurable
  tolerance (`AMOUNT_TOLERANCE` in `reconcile.py`) avoids flagging
  paise-level rounding as a false mismatch.
- **Exceptions are never silently dropped.** Every unresolved record is
  listed explicitly with a reason, so nothing gets lost between systems.

## What's next

- Plug in a real transaction source (e.g. a live Postgres outbox table)
  instead of synthetic CSVs.
- Add a lightweight dashboard for browsing exceptions instead of reading
  console/JSON output.
- Track match rate over time to catch systemic reconciliation issues
  early, not just per-batch.
