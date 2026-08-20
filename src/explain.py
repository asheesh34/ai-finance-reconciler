"""
Takes the structured output of reconcile.py and asks Claude to write a
short, plain-English explanation for each exception / mismatch, so a
human reading the report understands *why* something couldn't be
resolved automatically - not just a status code.

Requires ANTHROPIC_API_KEY to be set in the environment.
"""

import os
import json
from anthropic import Anthropic

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-4-6"


def _describe_record(label, record):
    if record is None:
        return f"{label}: (no record)"
    return f"{label}: id={record['transaction_id']} date={record['date']} amount={record['amount']} merchant={record['merchant']}"


def explain_mismatch(item):
    prompt = f"""A finance reconciliation system found an amount mismatch between an internal
transaction record and a bank statement record for the same transaction ID.

{_describe_record("Internal record", item['internal'])}
{_describe_record("Bank record", item['bank'])}
Difference (bank - internal): {item['difference']}

In 1-2 short sentences, explain the most likely real-world reason for this
mismatch (e.g. bank fee, partial refund, currency rounding, gateway charge).
Be concise and specific. Do not repeat the raw numbers back verbatim, just
explain the likely cause in plain English."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def explain_exception(item):
    prompt = f"""A finance reconciliation system found the following unresolved exception
while comparing internal transaction records against a bank statement.

Exception type: {item['type']}
{_describe_record("Internal record", item['internal'])}
{_describe_record("Bank record(s)", item['bank'])}

In 1-2 short sentences, explain in plain English what this exception type
usually means in a real payments/finance context, and what a human should
check next. Be concise and specific."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def annotate_result(result):
    """Adds an 'explanation' field to every mismatch and exception in-place."""
    for m in result["mismatched"]:
        m["explanation"] = explain_mismatch(m)

    for e in result["exceptions"]:
        # duplicate records have a list under 'bank', not a single dict
        e_copy = dict(e)
        if e["type"] == "DUPLICATE_IN_BANK":
            e_copy["bank"] = e["bank"][0]  # just describe one instance for the prompt
        e["explanation"] = explain_exception(e_copy)

    return result


if __name__ == "__main__":
    from reconcile import reconcile

    result = reconcile("data/internal_records.csv", "data/bank_statement.csv")
    result = annotate_result(result)

    print(json.dumps(
        {"mismatched": result["mismatched"], "exceptions": result["exceptions"]},
        indent=2, default=str
    ))
