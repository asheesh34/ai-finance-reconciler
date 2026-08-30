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
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 720px;
         margin: 0 auto; padding: 60px 24px; color: #1a1a1a; background: #fafafa; }
  .badge { display: inline-block; background: #eef6ff; color: #1959b8; font-size: 12px;
           font-weight: 600; padding: 4px 10px; border-radius: 20px; letter-spacing: 0.3px;
           text-transform: uppercase; margin-bottom: 14px; }
  h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: -0.5px; }
  p.subtitle { color: #666; margin: 0 0 8px; font-size: 15px; }
  .card { background: white; border: 1px solid #e4e4e7; border-radius: 14px; padding: 32px;
          margin-top: 28px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
  label { display: block; font-weight: 600; margin-bottom: 8px; margin-top: 22px; font-size: 14px; }
  label:first-of-type { margin-top: 0; }
  input[type=file] { display: block; width: 100%; padding: 12px; border: 1.5px dashed #c7c7cc;
                      border-radius: 8px; background: #fbfbfc; font-size: 14px; }
  input[type=file]:hover { border-color: #1959b8; }
  button { margin-top: 28px; background: #111827; color: white; border: none;
           padding: 13px 24px; border-radius: 8px; font-size: 15px; font-weight: 600;
           cursor: pointer; width: 100%; transition: background 0.15s; }
  button:hover { background: #000; }
  .hint { color: #999; font-size: 12.5px; margin-top: 6px; }
  .error { background: #fef2f2; color: #b42318; padding: 14px 16px; border-radius: 8px;
           margin-top: 20px; font-size: 14px; border: 1px solid #fecaca; }
  a.sample { font-size: 13px; color: #1959b8; text-decoration: none; }
  a.sample:hover { text-decoration: underline; }
  .footer-hint { text-align: center; margin-top: 20px; color: #999; }
</style>
</head>
<body>
  <span class="badge">Reconciliation Engine</span>
  <h1>AI Finance Controller</h1>
  <p class="subtitle">Upload two transaction datasets — see the match rate and every unresolved exception, honestly reported.</p>

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

  <p class="footer-hint">
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
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 900px;
         margin: 0 auto; padding: 50px 24px; color: #1a1a1a; background: #fafafa; }
  h1 { font-size: 28px; margin: 0 0 4px; letter-spacing: -0.5px; }
  h3 { font-size: 16px; margin: 32px 0 8px; color: #333; }
  .summary { display: flex; gap: 14px; margin: 26px 0; flex-wrap: wrap; }
  .stat { background: white; border: 1px solid #e4e4e7; border-radius: 12px; padding: 20px 24px;
          flex: 1; min-width: 140px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
  .stat .num { font-size: 30px; font-weight: 700; letter-spacing: -0.5px; }
  .stat .label { color: #777; font-size: 12.5px; margin-top: 4px; font-weight: 500; }
  .stat.rate .num { color: #15803d; }
  .stat.rate { border-color: #bbf7d0; background: #f0fdf4; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px;
          background: white; border-radius: 10px; overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04); border: 1px solid #e4e4e7; }
  th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid #eee; }
  th { background: #f7f7f8; font-size: 12.5px; text-transform: uppercase; color: #666;
       letter-spacing: 0.3px; font-weight: 600; }
  tr:last-child td { border-bottom: none; }
  .type-tag { display: inline-block; padding: 3px 9px; border-radius: 5px; font-size: 12px;
              font-weight: 600; background: #fef2f2; color: #b42318; }
  .note { color: #888; font-size: 13px; margin: 20px 0 4px; padding: 14px 16px;
          background: #f4f4f5; border-radius: 8px; }
  a.back { display: inline-block; margin-top: 34px; color: #444; text-decoration: none;
           font-size: 14px; font-weight: 500; }
  a.back:hover { text-decoration: underline; }
  .empty { color: #999; font-style: italic; font-size: 14px; }
</style>
</head>
<body>
  <h1>Reconciliation Results</h1>

  <div class="summary">
    <div class="stat rate"><div class="num">{{ result.match_rate }}%</div><div class="label">MATCH RATE</div></div>
    <div class="stat"><div class="num">{{ result.matched|length }}</div><div class="label">MATCHED</div></div>
    <div class="stat"><div class="num">{{ result.mismatched|length }}</div><div class="label">MISMATCHED</div></div>
    <div class="stat"><div class="num">{{ result.exceptions|length }}</div><div class="label">EXCEPTIONS</div></div>
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
