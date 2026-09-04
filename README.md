# AI Finance Controller — Reconciliation Agent

[![Tests](https://github.com/asheesh34/ai-finance-reconciler/actions/workflows/tests.yml/badge.svg)](https://github.com/asheesh34/ai-finance-reconciler/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)

An AI agent that reconciles transaction records against bank statements — flags mismatches and unresolved exceptions with plain-English explanations instead of raw error codes.

Built for the Razorpay AI Buildathon — Track 04: AI Finance Controller.

## Results

- **Deterministic match rate:** ~75-80% on 50+ synthetic transactions
  with deliberately injected errors (varies per run, since errors are
  randomly injected — see `data/report.json` after running).
- **Agent accuracy:** measured on a held-out, hand-labeled evaluation
  set of 20 transaction pairs — where a human decided the correct
  answer directly, independent of this project's own matching rules.
  Full precision/recall per label in `tests/eval_agent.py` output.
  **Caveat:** n=20 with only 1-3 examples per label is a diagnostic
  sample, not a statistically robust benchmark — a single case flips
  a category's precision/recall between 0% and 100%. Per-category
  metrics should be read as indicative, not proof. Expanding this
  set further is the natural next step (see What's next).
- **The agent supports confidence-based deferral to human review** —
  if its own stated confidence falls below `CONFIDENCE_THRESHOLD`
  (default 0.6, overridable via environment variable), it returns
  `NEEDS_HUMAN_REVIEW` instead of forcing a label. This default has
  **not been calibrated** against `eval_set.py` or any other validation
  data — it is an unvalidated starting point, not a tuned value. This
  is disclosed rather than hidden; calibrating the threshold against a
  larger evaluation set is on the roadmap.
- The misclassified cases in this evaluation were defensible edge
  cases, not random errors — every mistake is logged with the agent's
  reasoning alongside the human's original reasoning, visible in full
  when you run `tests/eval_agent.py` yourself.
- The internal-records side of the reconciliation is pulled from a
  real, running instance of [RewindDB](https://github.com/asheesh34/rewinddb-mini)
  (this author's own change-capture system) via its actual REST API,
  not a static file.

## The problem

Every business has two versions of the truth for its money: what its own
system says happened, and what the bank / payment gateway says happened.
Someone has to manually compare these two lists, line by line, to catch
missing settlements, amount mismatches, and duplicate charges. This is
still done by hand at most companies.

## What this does

This is a reconciliation **agent** that:

1. Takes two transaction datasets — an internal record set and a bank
   statement (synthetic data, 50+ records, with realistic errors
   deliberately injected).
2. Runs a deterministic matching engine that compares transaction ID,
   amount, date, and merchant name, classifying each record as
   **matched**, or one of several distinct mismatch/exception types
   (`AMOUNT_MISMATCH`, `LIKELY_PARTIAL_REFUND`, `MERCHANT_NAME_MISMATCH`,
   `MISSING_IN_BANK`/`MISSING_IN_INTERNAL`, `DUPLICATE_IN_BANK`). A
   settlement delay of a few days is still counted as matched, since
   that's normal behavior, not a real problem.
3. Separately, an AI agent independently looks at every record pair and
   decides its own classification, with a confidence score and plain
   reasoning — without being told the deterministic answer first.
4. Compares the agent's independent judgment against the verified
   deterministic result and reports an **agreement rate** — a second,
   honest accuracy metric, not just a plausible-sounding explanation.
5. Reports an overall **match rate**, the **agent agreement rate**, and
   every case the agent and the rules disagreed on — visible, not hidden.

This system does not force a match or hide failures. A 100% match rate
on synthetic data with injected errors would mean something is wrong
with the matching logic, not that reconciliation is "solved." Likewise,
100% agent agreement would be suspicious — disagreements are surfaced
so a human can review them.

## Example output

```
============================================================
  AI FINANCE CONTROLLER — RECONCILIATION REPORT
============================================================
Total transactions considered: 60
Matched cleanly:               45
Mismatched (amount differs):   6
Unresolved exceptions:         9
MATCH RATE: 75.0%
------------------------------------------------------------
AI AGENT independently reviewed 15 records
  Deferred to human (low confidence): 0 (0.0%)
  Auto-resolved and agreed with verified rules: 15
AGENT AGREEMENT RATE (of auto-resolved cases): 100.0%
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
| `src/llm_client.py` | Shared AI API client (currently Groq's free tier) — pacing, retries, and model fallback used by both `agent.py` and `explain.py`. |
| `src/explain.py` | Calls the AI API to explain each mismatch/exception in plain English. |
| `src/agent.py` | The agent layer — independently classifies each record pair and compares its judgment against verified ground truth. |
| `src/report.py` | Combines the above into one final report (console output + `data/report.json`). |
| `src/push_to_rewinddb.py` / `src/pull_from_rewinddb.py` | Push synthetic transactions into a real running RewindDB instance via its API, then read them back out of its actual database. |
| `app.py` | A web interface — upload two CSVs in a browser and see the full reconciliation + AI investigation workflow, no command line needed. |

## Running it

```bash
pip install -r requirements.txt

export AI_API_KEY=your_key_here   # get a free key: https://console.groq.com/keys

# 1. Generate synthetic data
python3 src/generate_data.py

# 2. Run the full reconciliation + AI explanation report
python3 src/report.py
```

Output is printed to the console and saved to `data/report.json`.

## Web interface

For anyone who doesn't want to use the command line, `app.py` provides
a simple browser-based version: upload two CSVs, click a button, see
the full workflow in one page — deterministic match rate, then an AI
investigation of every mismatch and exception.

```bash
pip install -r requirements.txt
python3 app.py
```

Then open `http://localhost:5000`. There's also a "use built-in sample
data" link for a no-setup demo. Required CSV columns: `transaction_id`,
`date`, `amount`, `merchant`.

If `AI_API_KEY` is set, the AI investigation section runs automatically
on every mismatch/exception (never on matches, keeping API calls
proportional to actual problems) and shows each one's AI classification,
confidence, and status — AI CONFIRMS, NEEDS HUMAN REVIEW, or AI
DISAGREES with the deterministic result. If the key isn't set, or the
API is unreachable, the page shows a clear banner and the deterministic
results are displayed exactly the same either way — the web UI never
depends on the AI layer to show reconciliation results.

## Using real data from RewindDB (optional)

This project can reconcile against genuine data instead of the synthetic
CSV, by pulling records from a running [RewindDB](https://github.com/asheesh34/rewinddb-mini)
instance — the change-capture / audit-trail system this was built to
extend.

```bash
# With RewindDB's backend running locally (localhost:8080):

# 1. Push the synthetic transactions into RewindDB's real API
python3 src/push_to_rewinddb.py

# 2. Pull them back out of RewindDB's own Postgres change_events table
python3 src/pull_from_rewinddb.py

# 3. Reconcile against the real data that came back
python3 src/report.py --source rewinddb
```

The bank statement side stays synthetic either way (no real bank data
is available), but the internal-records side now comes from a real
system with a real API and a real database, not a static file.

## Running the tests

```bash
python -m unittest discover -s tests -v
```

24 unit tests cover exact matches, every mismatch/exception type, and
edge cases like empty input files. These also run automatically via
GitHub Actions on every push (see the badge above).

## Evaluating the agent against human judgment

Beyond the unit tests, `tests/eval_set.py` is a small, hand-labeled
evaluation set: 20 transaction pairs where a human decided the correct
answer directly, independent of the code's own matching rules. This
lets us measure the agent's accuracy against real human judgment
rather than checking it against the same logic it might share blind
spots with.

```bash
export AI_API_KEY=your_key_here   # get a free key: https://console.groq.com/keys
python3 tests/eval_agent.py
```

This reports overall accuracy plus precision/recall per label, and
prints every case the agent got wrong alongside the human's original
reasoning - so mistakes are visible, not hidden behind a summary
number.

## Design notes

- **The deterministic engine is the ground truth; the agent is verified
  against it, not trusted blindly.** Reconciliation numbers need to be
  exact and reproducible, so the core matching logic (ID, amount, date,
  merchant) is plain code, not an LLM call. The agent's job is to reason
  independently and be *checked* against that ground truth — its
  agreement rate is a measured accuracy number, not an assumption.
- **Disagreements are surfaced, not resolved silently.** When the agent's
  independent judgment differs from the verified rules, both views are
  shown. A human reviewer decides which one to trust, rather than the
  system quietly picking one.
- **The agent supports deferring to a human, though the threshold is
  unproven.** Below `CONFIDENCE_THRESHOLD` (default 0.6, set via
  environment variable, unvalidated), the final label is overridden to
  `NEEDS_HUMAN_REVIEW` with the model's original lean preserved for the
  reviewer — this is tested end-to-end (`tests/test_agent.py`). What
  isn't yet proven is that 0.6 is the right cutoff — this hasn't been
  calibrated against real mistakes in the evaluation set. The mechanism
  is real and exercised by tests; its calibration is a roadmap item,
  not a finished claim.
- **Tolerance for rounding, not for real mismatches.** A configurable
  tolerance (`AMOUNT_TOLERANCE` in `reconcile.py`) avoids flagging
  paise-level rounding as a false mismatch.
- **Exceptions are never silently dropped.** Every unresolved record is
  listed explicitly with a reason, so nothing gets lost between systems.
- **The AI provider was switched once, deliberately, mid-project.**
  This started on Gemini's free tier, which repeatedly hit rate limits
  and connection failures during real testing. It was replaced with
  Groq's free tier (dedicated inference hardware, faster and more
  reliable in practice) — a one-file change, since `agent.py` and
  `explain.py` only ever call the shared `call_llm()` function in
  `llm_client.py` and never depend on a specific provider's request/
  response shape. Switching providers also surfaced a real, separate
  bug: the new model needed a larger `max_tokens` budget to finish its
  reasoning before writing the final JSON answer, which was found and
  fixed by inspecting an actual failed response, not by guessing.

## What's next

- Calibrate `CONFIDENCE_THRESHOLD` against a larger evaluation set
  (e.g. sweep values and pick the one that actually catches the most
  wrong-but-confident answers) instead of using the current unvalidated
  0.6 default.
- Expand the hand-labeled evaluation set beyond 20 cases (3+ per label
  for every category) for statistically meaningful precision/recall,
  not just a diagnostic signal.
- Track match rate over time to catch systemic reconciliation issues
  early, not just per-batch.
