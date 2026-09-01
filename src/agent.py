"""
The reconciliation agent.

Unlike explain.py (which narrates a label the deterministic code already
computed), this module has the AI independently look at a record pair and
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

Uses a free-tier AI API (via llm_client.py) - no billing
required to run this.
"""

import json
import os
import re
from llm_client import call_llm

_DEFAULT_CONFIDENCE_THRESHOLD = 0.6


def _load_confidence_threshold():
    """
    Reads CONFIDENCE_THRESHOLD from the environment, following the same
    override pattern as AI_MODEL in llm_client.py. Falls back to the
    default on any invalid value (unparseable, or outside 0.0-1.0) rather
    than raising - a misconfigured threshold should not crash the tool.

    0.60 is currently an UNVALIDATED default: it was not derived from
    a sweep against tests/eval_set.py or any other validation data. It
    is a conservative starting point, documented as such rather than
    presented as tuned.
    """
    raw = os.environ.get("CONFIDENCE_THRESHOLD")
    if raw is None:
        return _DEFAULT_CONFIDENCE_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_CONFIDENCE_THRESHOLD
    if not (0.0 <= value <= 1.0):
        return _DEFAULT_CONFIDENCE_THRESHOLD
    return value


# Below this confidence, the agent defers to a human instead of forcing
# a guess. See _load_confidence_threshold's docstring: this default is
# unvalidated, not calibrated against evaluation data. Override with the
# CONFIDENCE_THRESHOLD environment variable.
CONFIDENCE_THRESHOLD = _load_confidence_threshold()

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
    "NEEDS_HUMAN_REVIEW",  # not one of the LLM's raw choices - assigned
                           # by this code when confidence is too low to
                           # safely auto-resolve, regardless of which
                           # label the LLM leaned toward
}


def _record_str(label, record):
    if record is None:
        return f"{label}: (no record found)"
    return (f"{label}: id={record.get('transaction_id')} date={record.get('date')} "
            f"amount={record.get('amount')} merchant={record.get('merchant')}")


def _describe_bank(bank_record_or_list):
    """
    Formats the bank side of the comparison. bank_record_or_list may be
    None, a single dict (the normal case), or a list of dicts - which
    happens specifically for DUPLICATE_IN_BANK, where the same
    transaction ID appears more than once in the bank statement.

    When it's a list, every entry is shown explicitly, so the model can
    see the duplication itself from the raw data. Previously only the
    first entry was ever shown, which made it structurally impossible
    for the model to recognize a duplicate - it was being asked to spot
    something the data it received couldn't reveal.
    """
    if bank_record_or_list is None:
        return "Bank record: (no record found)"
    if isinstance(bank_record_or_list, list):
        if len(bank_record_or_list) == 1:
            return _record_str("Bank record", bank_record_or_list[0])
        lines = [f"Bank records: {len(bank_record_or_list)} separate entries found in the "
                 f"bank statement for this same transaction ID:"]
        for i, rec in enumerate(bank_record_or_list, 1):
            lines.append(f"  Entry {i}: date={rec.get('date')} amount={rec.get('amount')} merchant={rec.get('merchant')}")
        return "\n".join(lines)
    return _record_str("Bank record", bank_record_or_list)


def classify_pair(internal_record, bank_record):
    """
    Asks the AI to independently classify a record pair (or a one-sided
    record, for missing/duplicate cases) and return a structured decision.

    bank_record may be a single dict, None, or a list of dicts (for
    DUPLICATE_IN_BANK - see _describe_bank).

    If the model's own confidence is below CONFIDENCE_THRESHOLD, the
    final label is overridden to NEEDS_HUMAN_REVIEW - the agent deferring
    rather than forcing a low-confidence guess. The model's original
    lean is preserved as raw_label so a human reviewer still sees what
    the agent suspected, even when it chose not to act on it.

    Returns a dict: {label, raw_label, confidence, reasoning, deferred}
    """
    prompt = f"""You are a finance reconciliation agent. Look at this transaction record
pair (from an internal ledger vs. a bank statement) and independently decide
the correct classification. Do not assume a label has already been chosen -
reason from the raw data.

{_record_str("Internal record", internal_record)}
{_describe_bank(bank_record)}

Choose exactly one label from this list:
- MATCH: amount, merchant, and date are all consistent (allow a few days
  of settlement delay and minor merchant name formatting differences)
- SETTLEMENT_DELAY: amount and merchant match, but the date differs by
  more than a trivial amount - flag it, but it is not an error
- AMOUNT_MISMATCH: a small unexplained amount difference (likely a fee
  or rounding issue) - this covers differences roughly under 10%
- LIKELY_PARTIAL_REFUND: bank amount is meaningfully lower than internal
  - roughly 10% or more lower - suggesting a partial refund rather than
  a fee. Be careful near this boundary: a 2-5% difference is almost
  always AMOUNT_MISMATCH (a fee), not a refund. Only choose
  LIKELY_PARTIAL_REFUND when the gap is clearly large enough that a fee
  explanation would be implausible.
- MERCHANT_NAME_MISMATCH: amount and date match, but the merchant name
  looks meaningfully different (not just a formatting variant)
- MISSING_IN_BANK: internal record exists, no corresponding bank record
- MISSING_IN_INTERNAL: bank record exists, no corresponding internal record
- DUPLICATE_IN_BANK: more than one bank entry was shown above for this
  same transaction ID
- UNRESOLVED: none of the above cleanly applies - use this when TWO OR
  MORE things are wrong at once (e.g. both the date AND the amount are
  off), since that combination needs a human to untangle rather than
  being forced into one clean category

If amounts differ, calculate the percentage difference first:
abs(bank_amount - internal_amount) / internal_amount * 100. Your final
label MUST be consistent with that calculation - if the percentage you
calculate is 10% or higher, the label must be LIKELY_PARTIAL_REFUND, not
AMOUNT_MISMATCH. Never state a percentage in your reasoning that
contradicts the label you choose.

Give an honest confidence score (0.0-1.0). If the case is genuinely
ambiguous, sits near a category boundary, or has more than one thing
wrong with it, give a LOWER confidence rather than forcing a
clean-sounding label - do not inflate confidence just to sound decisive.

The "reasoning" field must be your final, clean, one-sentence
explanation only - never include intermediate deliberation, hedging
words like "wait" or "actually", or a description of your own
thought process.

Respond with ONLY a JSON object, no other text. Write "reasoning" first
so your label and confidence follow from it, in this exact format:
{{"reasoning": "one short sentence, including your percentage calculation if amounts differ", "label": "...", "confidence": 0.0}}"""

    raw = call_llm(prompt, max_tokens=200)

    # Be defensive - strip markdown fences if the model adds them anyway
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(raw)
        raw_label = parsed.get("label", "UNRESOLVED")
        if raw_label not in VALID_LABELS or raw_label == "NEEDS_HUMAN_REVIEW":
            raw_label = "UNRESOLVED"  # NEEDS_HUMAN_REVIEW is never the model's own choice
        confidence = float(parsed.get("confidence", 0.0))
        reasoning = parsed.get("reasoning", "")
    except (json.JSONDecodeError, ValueError):
        raw_label, confidence, reasoning = "UNRESOLVED", 0.0, "Could not parse agent response."

    deferred = confidence < CONFIDENCE_THRESHOLD
    final_label = "NEEDS_HUMAN_REVIEW" if deferred else raw_label

    return {
        "label": final_label,
        "raw_label": raw_label,
        "confidence": confidence,
        "reasoning": reasoning,
        "deferred": deferred,
    }


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

    A deferred case (NEEDS_HUMAN_REVIEW) is never counted as "agrees" -
    but it is tracked separately from a genuine wrong guess, since
    deferring on an uncertain case is the correct, safe behavior, not
    a mistake.
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
        all_items.append(e)

    agreements = 0
    deferrals = 0
    for item in all_items:
        decision = classify_pair(item.get("internal"), item.get("bank"))
        item["agent_label"] = decision["label"]
        item["agent_raw_label"] = decision["raw_label"]
        item["agent_confidence"] = decision["confidence"]
        item["agent_reasoning"] = decision["reasoning"]
        item["agent_deferred"] = decision["deferred"]
        item["agent_agrees"] = (decision["label"] == item["_ground_truth"])
        if decision["deferred"]:
            deferrals += 1
        elif item["agent_agrees"]:
            agreements += 1

    total = len(all_items)
    auto_resolved = total - deferrals
    agreement_rate = round((agreements / auto_resolved * 100), 1) if auto_resolved else 0.0
    deferral_rate = round((deferrals / total * 100), 1) if total else 0.0

    result["agent_agreement_rate"] = agreement_rate
    result["agent_total_reviewed"] = total
    result["agent_agreements"] = agreements
    result["agent_deferrals"] = deferrals
    result["agent_deferral_rate"] = deferral_rate
    return result
