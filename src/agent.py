"""
The reconciliation agent.

Unlike explain.py (which narrates a label the deterministic code already
computed), this module has Claude independently look at a record pair and
DECIDE the classification itself, with a confidence level and reasoning.

The deterministic logic in reconcile.py still runs, but here it is used as
a verification / ground-truth layer: we compare what the agent decided
against what the rules-based system computed, and report an agreement
rate. This is a second, honest accuracy metric - not just "the AI sounds
plausible," but "the AI's independent judgment matches verified logic on
measured percentage of cases."

Where the two disagree, both views are reported rather than silently
picking one - that disagreement is itself useful signal for a human
reviewer.
"""

import os
import json
import re
from anthropic import Anthropic

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-4-6"

VALID_LABELS = {
    "MATCH",
    "AMOUNT_MISMATCH",
    "LIKELY_PARTIAL_REFUND",
    "MERCHANT_NAME_MISMATCH",
    "SETTLEMENT_DELAY",
    "MISSING_IN_BANK",
    "MISSING_IN_INTERNAL",
    "DUPLICATE_IN_BANK",
    "UNRESOLVED",
}


def _record_str(label, record):
    if record is None:
        return f"{label}: (no record found)"
    return (f"{label}: id={record.get('transaction_id')} date={record.get('date')} "
            f"amount={record.get('amount')} merchant={record.get('merchant')}")


def classify_pair(internal_record, bank_record):
    """
    Asks Claude to independently classify a record pair (or a one-sided
    record, for missing/duplicate cases) and return a structured decision.

    Returns a dict: {label, confidence (0-1), reasoning}
    """
    prompt = f"""You are a finance reconciliation agent. Look at this transaction record
pair (from an internal ledger vs. a bank statement) and independently decide
the correct classification. Do not assume a label has already been chosen -
reason from the raw data.

{_record_str("Internal record", internal_record)}
{_record_str("Bank record", bank_record)}

Choose exactly one label from this list:
- MATCH: amount, merchant, and date are all consistent (allow a few days
  of settlement delay and minor merchant name formatting differences)
- SETTLEMENT_DELAY: amount and merchant match, but the date differs by
  more than a trivial amount - flag it, but it is not an error
- AMOUNT_MISMATCH: a small unexplained amount difference (likely a fee
  or rounding issue)
- LIKELY_PARTIAL_REFUND: bank amount is meaningfully lower than internal
  (10%+ lower), suggesting a partial refund rather than a fee
- MERCHANT_NAME_MISMATCH: amount and date match, but the merchant name
  looks meaningfully different (not just a formatting variant)
- MISSING_IN_BANK: internal record exists, no corresponding bank record
- MISSING_IN_INTERNAL: bank record exists, no corresponding internal record
- DUPLICATE_IN_BANK: the same transaction appears more than once in the
  bank statement
- UNRESOLVED: none of the above cleanly applies

Respond with ONLY a JSON object, no other text, in this exact format:
{{"label": "...", "confidence": 0.0, "reasoning": "one short sentence"}}"""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()

    # Be defensive - strip markdown fences if the model adds them anyway
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(raw)
        label = parsed.get("label", "UNRESOLVED")
        if label not in VALID_LABELS:
            label = "UNRESOLVED"
        return {
            "label": label,
            "confidence": float(parsed.get("confidence", 0.0)),
            "reasoning": parsed.get("reasoning", ""),
        }
    except (json.JSONDecodeError, ValueError):
        return {"label": "UNRESOLVED", "confidence": 0.0, "reasoning": "Could not parse agent response."}


def _ground_truth_label(deterministic_type, has_matched):
    """Maps reconcile.py's internal type strings onto the agent's label set."""
    if has_matched:
        return "MATCH"
    mapping = {
        "AMOUNT_MISMATCH": "AMOUNT_MISMATCH",
        "LIKELY_PARTIAL_REFUND": "LIKELY_PARTIAL_REFUND",
        "MERCHANT_NAME_MISMATCH": "MERCHANT_NAME_MISMATCH",
        "MISSING_IN_BANK": "MISSING_IN_BANK",
        "MISSING_IN_INTERNAL": "MISSING_IN_INTERNAL",
        "DUPLICATE_IN_BANK": "DUPLICATE_IN_BANK",
    }
    return mapping.get(deterministic_type, "UNRESOLVED")


def run_agent_verification(result):
    """
    For every matched, mismatched, and exception record, asks the agent to
    independently classify it, then compares against the deterministic
    ground truth. Adds 'agent_label', 'agent_confidence', 'agent_reasoning',
    and 'agent_agrees' fields to each record in-place, and returns an
    overall agreement rate.
    """
    all_items = []

    for m in result["matched"]:
        m["_ground_truth"] = "MATCH"
        all_items.append(m)

    for m in result["mismatched"]:
        m["_ground_truth"] = _ground_truth_label(m["type"], has_matched=False)
        all_items.append(m)

    for e in result["exceptions"]:
        e["_ground_truth"] = _ground_truth_label(e["type"], has_matched=False)
        # duplicates carry a list under 'bank' - use the first for the prompt
        e["_bank_for_prompt"] = e["bank"][0] if e["type"] == "DUPLICATE_IN_BANK" and e["bank"] else e["bank"]
        all_items.append(e)

    agreements = 0
    for item in all_items:
        bank_rec = item.get("_bank_for_prompt", item.get("bank"))
        decision = classify_pair(item.get("internal"), bank_rec)
        item["agent_label"] = decision["label"]
        item["agent_confidence"] = decision["confidence"]
        item["agent_reasoning"] = decision["reasoning"]
        item["agent_agrees"] = (decision["label"] == item["_ground_truth"])
        if item["agent_agrees"]:
            agreements += 1

    agreement_rate = round((agreements / len(all_items) * 100), 1) if all_items else 0.0
    result["agent_agreement_rate"] = agreement_rate
    result["agent_total_reviewed"] = len(all_items)
    result["agent_agreements"] = agreements
    return result
