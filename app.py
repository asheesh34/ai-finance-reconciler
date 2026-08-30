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
import json

from flask import Flask, request, render_template_string, send_file

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from reconcile import reconcile

app = Flask(__name__)

REQUIRED_COLUMNS = {"transaction_id", "date", "amount", "merchant"}

UPLOAD_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>AI Finance Controller — Reconciliation</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 720px;
         margin: 60px auto; padding: 0 20px; color: #1a1a1a; }
  h1 { font-size: 28px; margin-bottom: 4px; }
  p.subtitle { color: #666; margin-top: 0; }
  .card { border: 1px solid #ddd; border-radius: 10px; padding: 28px; margin-top: 24px; }
  label { display: block; font-weight: 600; margin-bottom: 6px; margin-top: 18px; }
  input[type=file] { display: block; width: 100%; padding: 10px; border: 1px dashed #bbb;
                      border-radius: 6px; }
  button { margin-top: 24px; background: #1a1a1a; color: white; border: none;
           padding: 12px 22px; border-radius: 6px; font-size: 15px; cursor: pointer; }
  button:hover { background: #333; }
  .hint { color: #888; font-size: 13px; margin-top: 6px; }
  .error { background: #fdecea; color: #a12820; padding: 12px 16px; border-radius: 6px;
           margin-top: 18px; }
  a.sample { font-size: 13px; }
</style>
</head>
<body>
  <h1>AI Finance Controller</h1>
  <p class="subtitle">Upload two transaction CSVs to reconcile them.</p>

  {% if error %}
  <div class="error">{{ error }}</div>
  {% endif %}

  <div class="card">
    <form method="POST" action="/reconcile" enctype="multipart/form-data">
      <label>Internal records (CSV)</label>
      <input type="file" name="internal_file" accept=".csv" required>
      <p class="hint">Columns required: transaction_id, date, amount, merchant</p>

      <label>Bank statement (CSV)</label>
      <input type="file" name="bank_file" accept=".csv" required>
      <p class="hint">Same column format as above.</p>

      <button type="submit">Reconcile</button>
    </form>
  </div>

  <p class="hint">
    No files handy? <a class="sample" href="/sample">Use the built-in sample data</a>
    to see how it works.
  </p>
</body>
</html>
"""

RESULTS_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Reconciliation Results</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px;
         margin: 40px auto; padding: 0 20px; color: #1a1a1a; }
  h1 { font-size: 26px; margin-bottom: 4px; }
  .summary { display: flex; gap: 16px; margin: 24px 0; flex-wrap: wrap; }
  .stat { border: 1px solid #ddd; border-radius: 10px; padding: 18px 24px; flex: 1; min-width: 140px; }
  .stat .num { font-size: 28px; font-weight: 700; }
  .stat .label { color: #666; font-size: 13px; margin-top: 4px; }
  .stat.rate .num { color: #1a7a3d; }
  table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #eee; }
  th { background: #fafafa; }
  .type-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px;
              background: #fdecea; color: #a12820; }
  .note { color: #666; font-size: 13px; margin: 4px 0 20px; }
  a.back { display: inline-block; margin-top: 30px; color: #444; }
  .empty { color: #888; font-style: italic; }
</style>
</head>
<body>
  <h1>Reconciliation Results</h1>

  <div class="summary">
    <div class="stat rate"><div class="num">{{ result.match_rate }}%</div><div class="label">Match rate</div></div>
    <div class="stat"><div class="num">{{ result.matched|length }}</div><div class="label">Matched</div></div>
    <div class="stat"><div class="num">{{ result.mismatched|length }}</div><div class="label">Mismatched</div></div>
    <div class="stat"><div class="num">{{ result.exceptions|length }}</div><div class="label">Exceptions</div></div>
  </div>

  <h3>Mismatches</h3>
  {% if result.mismatched %}
  <table>
    <tr><th>Transaction</th><th>Type</th><th>Internal amount</th><th>Bank amount</th><th>Difference</th></tr>
    {% for m in result.mismatched %}
    <tr>
      <td>{{ m.transaction_id }}</td>
      <td><span class="type-tag">{{ m.type }}</span></td>
      <td>{{ m.internal.amount }}</td>
      <td>{{ m.bank.amount }}</td>
      <td>{{ m.difference }}</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <p class="empty">None.</p>
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
  <p class="empty">None.</p>
  {% endif %}

  <p class="note">
    This report does not force a match or hide failures — every unresolved
    item above is left as-is for a human to review.
  </p>

  <a class="back" href="/">&larr; Reconcile another pair of files</a>
</body>
</html>
"""


def _validate_csv_columns(path):
    with open(path, newline="") as f:
        header = f.readline().strip().split(",")
    missing = REQUIRED_COLUMNS - set(header)
    return missing


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

    return render_template_string(RESULTS_PAGE, result=result)


if __name__ == "__main__":
    app.run(debug=False, port=5000)
