"""
A minimal web interface for the reconciliation engine.

Lets someone with no coding background use this project: upload two
CSV files (internal records + bank statement), click a button, see
the match rate and exception list rendered as a readable web page -
instead of needing to run Python scripts from a terminal.

AI explanations are included automatically if AI_API_KEY is set in
the environment; otherwise the report still works, just without the
plain-English explanation text (the deterministic numbers never
depend on the AI layer).

Usage:
    pip install -r requirements.txt
    python3 app.py
    Then open http://localhost:5000 in a browser.
"""

import os
import sys
import tempfile

from flask import Flask, request, render_template_string

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from reconcile import reconcile
from agent import classify_pair, _ground_truth_label

app = Flask(__name__)

REQUIRED_COLUMNS = {"transaction_id", "date", "amount", "merchant"}

BASE_STYLE = """
  * { box-sizing: border-box; }
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Serif:wght@500;600&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap');

  body {
    font-family: 'Inter', -apple-system, sans-serif;
    max-width: 760px;
    margin: 0 auto;
    padding: 56px 24px 80px;
    color: #1B1F1C;
    background: #EAF3EA;
    background-image: repeating-linear-gradient(
      to bottom, transparent, transparent 34px, #B9D6BE 35px
    );
    background-position: 0 100px;
  }
  .eyebrow {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #1F4D36;
    font-weight: 500;
  }
  h1 {
    font-family: 'IBM Plex Serif', serif;
    font-size: 32px;
    font-weight: 600;
    margin: 6px 0 2px;
    color: #1B1F1C;
  }
  p.subtitle {
    color: #3f4a43;
    margin: 0 0 28px;
    font-size: 15px;
    max-width: 52ch;
  }
  .ledger-sheet {
    background: #F7FBF6;
    border: 1.5px solid #1F4D36;
    border-radius: 3px;
    padding: 8px 32px 32px;
    position: relative;
  }
  .ledger-sheet::before {
    content: "";
    position: absolute;
    left: 44px; top: 0; bottom: 0;
    width: 1px;
    background: #e0b3ae;
  }
  .entry {
    display: flex;
    align-items: flex-start;
    gap: 20px;
    padding: 22px 0 20px 8px;
    border-bottom: 1px solid #d4e6d6;
  }
  .entry:last-of-type { border-bottom: none; }
  .entry-no {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    color: #1F4D36;
    font-weight: 600;
    padding-top: 4px;
    width: 18px;
  }
  .entry-body { flex: 1; }
  label {
    display: block;
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 8px;
  }
  input[type=file] {
    display: block;
    width: 100%;
    padding: 10px 12px;
    border: 1.5px dashed #7fa789;
    border-radius: 4px;
    background: white;
    font-size: 13px;
    font-family: 'IBM Plex Mono', monospace;
  }
  input[type=file]:hover { border-color: #1F4D36; }
  .hint {
    font-family: 'IBM Plex Mono', monospace;
    color: #5c6b60;
    font-size: 11.5px;
    margin-top: 7px;
  }
  button {
    margin-top: 26px;
    background: #1F4D36;
    color: #EAF3EA;
    border: none;
    padding: 13px 26px;
    border-radius: 4px;
    font-size: 14.5px;
    font-weight: 600;
    font-family: 'IBM Plex Mono', monospace;
    letter-spacing: 0.4px;
    cursor: pointer;
    width: 100%;
  }
  button:hover { background: #163a28; }
  .error {
    background: #fdf1f0;
    color: #B3261E;
    border: 1px solid #eec6c3;
    padding: 12px 16px;
    border-radius: 4px;
    margin-bottom: 20px;
    font-size: 13.5px;
    font-family: 'IBM Plex Mono', monospace;
  }
  a.sample, a.back {
    font-size: 13px;
    color: #1F4D36;
    text-decoration: none;
    font-weight: 500;
  }
  a.sample:hover, a.back:hover { text-decoration: underline; }
  .footer-hint { text-align: center; margin-top: 22px; color: #5c6b60; font-size: 13.5px; }
"""

UPLOAD_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Reconciliation Ledger</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
""" + BASE_STYLE + """
</style>
</head>
<body>
  <div class="eyebrow">Reconciliation Ledger</div>
  <h1>Two records. One truth.</h1>
  <p class="subtitle">Enter an internal record set and a bank statement below. Every line that doesn't tie out is reported, not hidden.</p>

  {% if error %}
  <div class="error">{{ error }}</div>
  {% endif %}

  <div class="ledger-sheet">
    <form method="POST" action="/reconcile" enctype="multipart/form-data">
      <div class="entry">
        <div class="entry-no">01</div>
        <div class="entry-body">
          <label>Internal records</label>
          <input type="file" name="internal_file" accept=".csv" required>
          <p class="hint">transaction_id, date, amount, merchant</p>
        </div>
      </div>
      <div class="entry">
        <div class="entry-no">02</div>
        <div class="entry-body">
          <label>Bank statement</label>
          <input type="file" name="bank_file" accept=".csv" required>
          <p class="hint">same column format</p>
        </div>
      </div>
      <button type="submit">Reconcile the ledger &rarr;</button>
    </form>
  </div>

  <p class="footer-hint">
    No files handy? <a class="sample" href="/sample">Run the built-in sample</a>
  </p>
</body>
</html>
"""

RESULTS_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Reconciliation Results</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
""" + BASE_STYLE + """
  body { max-width: 920px; }
  .headline { display: flex; align-items: center; gap: 28px; margin: 8px 0 30px; flex-wrap: wrap; }
  .stamp {
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    font-size: 22px;
    letter-spacing: 1px;
    color: #2F7D4F;
    border: 3px double #2F7D4F;
    padding: 10px 18px;
    border-radius: 6px;
    transform: rotate(-4deg);
    display: inline-block;
    white-space: nowrap;
  }
  .stamp.low { color: #B3261E; border-color: #B3261E; }
  .stamp .stamp-label {
    display: block;
    font-size: 9.5px;
    letter-spacing: 2px;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    margin-top: 2px;
    text-align: center;
  }
  .counts { font-family: 'IBM Plex Mono', monospace; font-size: 13.5px; color: #3f4a43; line-height: 1.9; }
  .counts b { color: #1B1F1C; }
  h3 {
    font-family: 'IBM Plex Serif', serif;
    font-size: 16px;
    font-weight: 600;
    margin: 34px 0 10px;
    color: #1F4D36;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
    background: #F7FBF6;
    border: 1px solid #cfe3d2;
    font-family: 'IBM Plex Mono', monospace;
  }
  th, td { text-align: left; padding: 9px 14px; border-bottom: 1px solid #dcecdd; }
  th {
    font-family: 'Inter', sans-serif;
    background: #E3F0E4;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #1F4D36;
    font-weight: 600;
  }
  tr:last-child td { border-bottom: none; }
  td.amount { text-align: right; }
  .type-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 600;
    background: #fdf1f0;
    color: #B3261E;
    font-family: 'Inter', sans-serif;
  }
  .diff-neg { color: #B3261E; }
  .diff-pos { color: #2F7D4F; }
  .note {
    color: #3f4a43;
    font-size: 13px;
    margin: 28px 0 4px;
    padding: 14px 16px;
    background: #F7FBF6;
    border-left: 3px solid #1F4D36;
    border-radius: 2px;
  }
  .empty { color: #6b7a70; font-style: italic; font-size: 13.5px; font-family: 'Inter', sans-serif; }

  .ai-banner {
    font-family: 'Inter', sans-serif;
    font-size: 13.5px;
    color: #7a5c1f;
    background: #FBF3E3;
    border: 1px solid #e8d2a0;
    border-left: 3px solid #A66A00;
    padding: 12px 16px;
    border-radius: 2px;
    margin: 12px 0 4px;
  }
  .status-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 600;
    font-family: 'Inter', sans-serif;
    letter-spacing: 0.3px;
  }
  .status-auto { background: #eafaf0; color: #2F7D4F; }
  .status-review { background: #FBF3E3; color: #A66A00; }
  .status-disagree { background: #fdf1f0; color: #B3261E; }
  .status-unavailable { background: #f1f1f2; color: #6b7a70; }
  .ai-conf { font-family: 'IBM Plex Mono', monospace; color: #666; font-size: 12.5px; }
"""

RESULTS_PAGE += """
</style>
</head>
<body>
  <div class="eyebrow">Reconciliation Ledger — Result</div>
  <h1>The books, closed</h1>

  <div class="headline">
    <div class="stamp {{ 'low' if result.match_rate < 60 else '' }}">
      {{ result.match_rate }}% MATCHED
      <span class="stamp-label">VERIFIED ON RECORD</span>
    </div>
    <div class="counts">
      <b>{{ result.matched|length }}</b> matched &nbsp;·&nbsp;
      <b>{{ result.mismatched|length }}</b> mismatched &nbsp;·&nbsp;
      <b>{{ result.exceptions|length }}</b> exceptions
    </div>
  </div>

  <h3>Mismatches</h3>
  {% if result.mismatched %}
  <table>
    <tr><th>Transaction</th><th>Type</th><th class="amount">Internal</th><th class="amount">Bank</th><th class="amount">Difference</th></tr>
    {% for m in result.mismatched %}
    <tr>
      <td>{{ m.transaction_id }}</td>
      <td><span class="type-tag">{{ m.type }}</span></td>
      <td class="amount">{{ m.internal.amount }}</td>
      <td class="amount">{{ m.bank.amount }}</td>
      <td class="amount {{ 'diff-neg' if m.difference < 0 else 'diff-pos' }}">{{ m.difference }}</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <p class="empty">None — every shared transaction ties out exactly.</p>
  {% endif %}

  <h3>Exceptions (could not be resolved automatically)</h3>
  {% if result.exceptions %}
  <table>
    <tr><th>Transaction</th><th>Type</th></tr>
    {% for e in result.exceptions %}
    <tr><td>{{ e.transaction_id }}</td><td><span class="type-tag">{{ e.type }}</span></td></tr>
    {% endfor %}
  </table>
  {% else %}
  <p class="empty">None — every transaction appears on both sides.</p>
  {% endif %}

  <h3>AI Investigation</h3>
  {% set ai_items = result.mismatched + result.exceptions %}
  {% if not result.ai_available %}
  <div class="ai-banner">
    AI investigation unavailable — {{ result.ai_unavailable_reason or "no AI_API_KEY configured on the server." }}
    The deterministic results above are unaffected and complete on their own.
  </div>
  {% elif not ai_items %}
  <p class="empty">No mismatches or exceptions to investigate.</p>
  {% else %}
  <table>
    <tr>
      <th>Transaction</th>
      <th>Deterministic type</th>
      <th>AI assessment</th>
      <th>Confidence</th>
      <th>Status</th>
    </tr>
    {% for item in ai_items %}
    <tr>
      <td>{{ item.transaction_id }}</td>
      <td><span class="type-tag">{{ item.type }}</span></td>
      {% if item.ai_error %}
      <td colspan="2"><span class="status-pill status-unavailable">AI UNAVAILABLE FOR THIS RECORD</span></td>
      <td></td>
      {% else %}
      <td>{{ item.ai_raw_label }}{% if item.ai_deferred %} <span class="ai-conf">(leaning)</span>{% endif %}</td>
      <td class="ai-conf">{{ "%.2f"|format(item.ai_confidence) }}</td>
      <td>
        {% if item.ai_deferred %}
          <span class="status-pill status-review">NEEDS HUMAN REVIEW</span>
        {% elif item.ai_disagrees %}
          <span class="status-pill status-disagree">AI DISAGREES</span>
        {% else %}
          <span class="status-pill status-auto">AUTO-RESOLVED</span>
        {% endif %}
      </td>
      {% endif %}
    </tr>
    {% if item.ai_reasoning %}
    <tr><td></td><td colspan="4" style="color:#666; font-size:12.5px; padding-top:0;">{{ item.ai_reasoning }}</td></tr>
    {% endif %}
    {% endfor %}
  </table>
  <p class="note">
    "AI disagrees" means the model's independent judgment differed from the
    deterministic rules above — both are shown, neither is hidden or overwritten.
    "Needs human review" means the model's own confidence was too low to
    auto-resolve, regardless of which label it leaned toward.
  </p>
  {% endif %}

  <p class="note">
    Nothing above is forced or hidden. Every unresolved entry is left exactly as found, for a human to close.
  </p>

  <a class="back" href="/">&larr; Reconcile another pair</a>
</body>
</html>
"""


def _validate_csv_columns(path):
    with open(path, newline="") as f:
        header = f.readline().strip().split(",")
    missing = REQUIRED_COLUMNS - set(header)
    return missing


def investigate_exceptions(result):
    """
    Runs the AI agent (classify_pair) on every mismatched and exception
    record - never on matched records, to keep API calls and latency
    proportional to actual problems, not the whole batch.

    Sets result['ai_available'] and, on each investigated item, adds
    ai_label / ai_raw_label / ai_confidence / ai_reasoning / ai_deferred /
    ai_agrees / ai_disagrees / ai_error - kept as separate fields
    alongside the existing deterministic 'type' field, never overwriting
    it.

    Fails safe: if AI_API_KEY is not set, or the very first real call
    fails (signaling the API is unreachable, not just one bad record),
    AI investigation is skipped entirely and the deterministic results
    are returned unchanged with ai_available=False. If AI is reachable
    but an individual record's call fails partway through, that one
    record is marked ai_error and the rest continue normally - a
    partial AI outage never discards reconciliation results.
    """
    items = result["mismatched"] + result["exceptions"]

    if not os.environ.get("AI_API_KEY"):
        result["ai_available"] = False
        result["ai_unavailable_reason"] = "No AI_API_KEY configured on the server."
        return result

    if not items:
        result["ai_available"] = True  # nothing to investigate, but AI is configured
        return result

    api_confirmed_working = False

    for i, item in enumerate(items):
        bank_rec = item["bank"][0] if item["type"] == "DUPLICATE_IN_BANK" and isinstance(item["bank"], list) else item.get("bank")

        try:
            decision = classify_pair(item.get("internal"), bank_rec)
        except Exception:
            item["ai_error"] = "AI investigation unavailable for this record."
            if not api_confirmed_working:
                # The very first attempt failed - treat this as the API
                # being unreachable, not a one-off bad record, and stop
                # trying further calls rather than retrying N more times.
                result["ai_available"] = False
                result["ai_unavailable_reason"] = "AI API was unreachable when investigation started."
                for remaining in items[i + 1:]:
                    remaining["ai_error"] = "AI investigation unavailable for this record."
                return result
            continue  # AI was working before; treat this as an isolated failure and keep going

        api_confirmed_working = True
        ground_truth = _ground_truth_label(item["type"], has_matched=False)
        item["ai_label"] = decision["label"]
        item["ai_raw_label"] = decision["raw_label"]
        item["ai_confidence"] = decision["confidence"]
        item["ai_reasoning"] = decision["reasoning"]
        item["ai_deferred"] = decision["deferred"]
        item["ai_agrees"] = (not decision["deferred"]) and (decision["label"] == ground_truth)
        item["ai_disagrees"] = (not decision["deferred"]) and (decision["label"] != ground_truth)

    result["ai_available"] = True
    return result


@app.route("/")
def index():
    return render_template_string(UPLOAD_PAGE, error=None)


@app.route("/sample")
def sample():
    """Runs reconciliation on the project's own built-in sample data."""
    internal_path = os.path.join(os.path.dirname(__file__), "data", "internal_records.csv")
    bank_path = os.path.join(os.path.dirname(__file__), "data", "bank_statement.csv")

    if not os.path.exists(internal_path) or not os.path.exists(bank_path):
        return render_template_string(
            UPLOAD_PAGE,
            error="Sample data not found. Run 'python3 src/generate_data.py' first."
        )

    result = reconcile(internal_path, bank_path)
    result = investigate_exceptions(result)
    return render_template_string(RESULTS_PAGE, result=result)


@app.route("/reconcile", methods=["POST"])
def do_reconcile():
    internal_file = request.files.get("internal_file")
    bank_file = request.files.get("bank_file")

    if not internal_file or not bank_file:
        return render_template_string(UPLOAD_PAGE, error="Please choose both files.")

    with tempfile.TemporaryDirectory() as tmp:
        internal_path = os.path.join(tmp, "internal.csv")
        bank_path = os.path.join(tmp, "bank.csv")
        internal_file.save(internal_path)
        bank_file.save(bank_path)

        missing_internal = _validate_csv_columns(internal_path)
        missing_bank = _validate_csv_columns(bank_path)

        if missing_internal or missing_bank:
            error = "Missing required columns."
            if missing_internal:
                error += f" Internal file is missing: {', '.join(missing_internal)}."
            if missing_bank:
                error += f" Bank file is missing: {', '.join(missing_bank)}."
            return render_template_string(UPLOAD_PAGE, error=error)

        try:
            result = reconcile(internal_path, bank_path)
        except Exception as e:
            return render_template_string(UPLOAD_PAGE, error=f"Could not process files: {e}")

        result = investigate_exceptions(result)

    return render_template_string(RESULTS_PAGE, result=result)


if __name__ == "__main__":
    app.run(debug=False, port=5000)
