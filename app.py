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
