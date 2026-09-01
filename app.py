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

# Shared design tokens for the fintech dashboard look. A restrained,
# professional palette: neutral light surface, navy/charcoal text,
# blue as the single primary accent, green reserved strictly for
# deterministic "matched" signals, amber for exceptions/attention,
# red reserved for the strongest disagreement signal (AI actively
# contradicting the deterministic result).
BASE_STYLE = """
  :root {
    --bg: #F8FAFC;
    --surface: #FFFFFF;
    --border: #E2E8F0;
    --border-strong: #CBD5E1;
    --text: #0F172A;
    --text-secondary: #475569;
    --text-tertiary: #94A3B8;
    --blue: #2563EB;
    --blue-bg: #EFF6FF;
    --blue-border: #BFDBFE;
    --green: #16A34A;
    --green-bg: #F0FDF4;
    --green-border: #BBF7D0;
    --amber: #B45309;
    --amber-bg: #FFFBEB;
    --amber-border: #FDE68A;
    --red: #DC2626;
    --red-bg: #FEF2F2;
    --red-border: #FECACA;
    --gray-bg: #F1F5F9;
  }
  * { box-sizing: border-box; }
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

  html { -webkit-font-smoothing: antialiased; }
  body {
    font-family: 'Inter', -apple-system, "Segoe UI", sans-serif;
    max-width: 880px;
    margin: 0 auto;
    padding: 40px 24px 72px;
    color: var(--text);
    background: var(--bg);
    line-height: 1.5;
  }
  .mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }

  /* --- Product identity header, shared --- */
  .product-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 28px; }
  .product-mark {
    width: 26px; height: 26px; border-radius: 7px;
    background: var(--text);
    display: flex; align-items: center; justify-content: center;
    color: white; font-family: 'IBM Plex Mono', monospace; font-weight: 600; font-size: 13px;
    flex-shrink: 0;
  }
  .product-name { font-size: 13.5px; font-weight: 600; color: var(--text); }
  .product-tag {
    font-size: 11px; font-weight: 600; color: var(--blue);
    background: var(--blue-bg); border: 1px solid var(--blue-border);
    padding: 2px 8px; border-radius: 20px; letter-spacing: 0.2px;
    margin-left: 2px;
  }

  h1 {
    font-size: 26px;
    font-weight: 700;
    letter-spacing: -0.3px;
    margin: 0 0 6px;
    color: var(--text);
  }
  p.subtitle {
    color: var(--text-secondary);
    margin: 0 0 30px;
    font-size: 14.5px;
    max-width: 58ch;
  }

  /* --- Cards, shared --- */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  }

  /* --- Upload form --- */
  .upload-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; padding: 20px; }
  @media (max-width: 620px) { .upload-grid { grid-template-columns: 1fr; } }
  .upload-field {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 16px 18px;
  }
  .upload-field-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .upload-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .upload-dot.internal { background: var(--blue); }
  .upload-dot.bank { background: var(--text-tertiary); }
  .upload-field label { font-weight: 600; font-size: 13.5px; color: var(--text); }
  input[type=file] {
    display: block;
    width: 100%;
    padding: 9px 10px;
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    background: var(--gray-bg);
    font-size: 12.5px;
    font-family: 'Inter', sans-serif;
    color: var(--text-secondary);
  }
  input[type=file]:hover { border-color: var(--blue); }
  .field-hint {
    font-family: 'IBM Plex Mono', monospace;
    color: var(--text-tertiary);
    font-size: 11px;
    margin-top: 7px;
  }
  .upload-actions { padding: 4px 20px 20px; }
  button {
    background: var(--text);
    color: white;
    border: none;
    padding: 11px 22px;
    border-radius: 7px;
    font-size: 14px;
    font-weight: 600;
    font-family: 'Inter', sans-serif;
    cursor: pointer;
    width: 100%;
    transition: background 0.12s ease;
  }
  button:hover { background: #1e293b; }
  button:disabled { background: var(--text-tertiary); cursor: not-allowed; }

  .notice {
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 18px;
    border: 1px solid;
  }
  .notice.error { background: var(--red-bg); border-color: var(--red-border); color: var(--red); }
  .notice.info { background: var(--blue-bg); border-color: var(--blue-border); color: #1D4ED8; }

  a.link { font-size: 13px; color: var(--blue); text-decoration: none; font-weight: 500; }
  a.link:hover { text-decoration: underline; }
  .footer-hint { text-align: center; margin-top: 18px; color: var(--text-tertiary); font-size: 13px; }
"""

UPLOAD_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>AI Finance Controller — Reconciliation</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
""" + BASE_STYLE + """
</style>
</head>
<body>
  <div class="product-bar">
    <div class="product-mark">FC</div>
    <div class="product-name">AI Finance Controller</div>
    <div class="product-tag">RECONCILIATION</div>
  </div>

  <h1>Reconcile two transaction sets</h1>
  <p class="subtitle">Upload your internal records and a bank statement. Every line that doesn't tie out is reported, with an AI second opinion on each exception — not hidden or auto-closed.</p>

  {% if error %}
  <div class="notice error">{{ error }}</div>
  {% endif %}

  <div class="card">
    <form id="reconcile-form" method="POST" action="/reconcile" enctype="multipart/form-data">
      <div class="upload-grid">
        <div class="upload-field">
          <div class="upload-field-head">
            <span class="upload-dot internal"></span>
            <label>Internal transactions</label>
          </div>
          <input type="file" name="internal_file" accept=".csv" required>
          <p class="field-hint">transaction_id, date, amount, merchant</p>
        </div>
        <div class="upload-field">
          <div class="upload-field-head">
            <span class="upload-dot bank"></span>
            <label>Bank / settlement records</label>
          </div>
          <input type="file" name="bank_file" accept=".csv" required>
          <p class="field-hint">same column format</p>
        </div>
      </div>
      <div class="upload-actions">
        <button type="submit" id="reconcile-btn">Run reconciliation</button>
      </div>
    </form>
  </div>

  <p class="footer-hint">
    No files handy? <a class="link" href="/sample">Run the built-in sample dataset</a>
  </p>

  <script>
    document.getElementById('reconcile-form').addEventListener('submit', function() {
      var btn = document.getElementById('reconcile-btn');
      btn.disabled = true;
      btn.textContent = 'Reconciling — this can take a minute if AI investigation runs…';
    });
  </script>
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
  body { max-width: 980px; }

  /* --- Metrics row --- */
  .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 4px 0 32px; }
  @media (max-width: 720px) { .metrics { grid-template-columns: repeat(2, 1fr); } }
  .metric {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 18px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  }
  .metric-label {
    font-size: 11px; font-weight: 600; letter-spacing: 0.4px; text-transform: uppercase;
    color: var(--text-tertiary); margin-bottom: 6px;
  }
  .metric-value { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; color: var(--text); }
  .metric.rate .metric-value { color: var(--green); }
  .metric.rate.mid .metric-value { color: var(--amber); }
  .metric.rate.low .metric-value { color: var(--red); }
  .rate-bar { height: 5px; background: var(--gray-bg); border-radius: 3px; margin-top: 10px; overflow: hidden; }
  .rate-bar-fill { height: 100%; background: var(--green); border-radius: 3px; }
  .rate-bar-fill.mid { background: var(--amber); }
  .rate-bar-fill.low { background: var(--red); }

  h2 {
    font-size: 15px; font-weight: 700; color: var(--text);
    margin: 34px 0 4px; letter-spacing: -0.1px;
  }
  p.section-sub { color: var(--text-tertiary); font-size: 12.5px; margin: 0 0 12px; }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }
  th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--border); }
  th {
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: var(--text-tertiary);
    font-weight: 600;
    background: var(--gray-bg);
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #FAFBFC; }
  td.amount, th.amount { text-align: right; }
  td.mono, td.amount { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }

  .badge {
    display: inline-block;
    padding: 3px 9px;
    border-radius: 5px;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.2px;
    border: 1px solid;
    white-space: nowrap;
  }
  .badge.exception { background: var(--amber-bg); color: var(--amber); border-color: var(--amber-border); }
  .badge.confirms { background: var(--blue-bg); color: #1D4ED8; border-color: var(--blue-border); }
  .badge.disagrees { background: var(--red-bg); color: var(--red); border-color: var(--red-border); }
  .badge.review { background: var(--amber-bg); color: var(--amber); border-color: var(--amber-border); }
  .badge.unavailable { background: var(--gray-bg); color: var(--text-tertiary); border-color: var(--border); }

  .diff-neg { color: var(--red); }
  .diff-pos { color: var(--green); }

  .ai-section-head {
    display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 8px;
    margin: 34px 0 4px;
  }
  .ai-disclaimer {
    font-size: 12px; color: var(--text-tertiary); font-style: italic;
  }
  .reasoning-row td { color: var(--text-secondary); font-size: 12px; padding-top: 0; border-bottom: 1px solid var(--border); }
  .reasoning-row:last-child td { border-bottom: none; }

  .note {
    color: var(--text-secondary);
    font-size: 13px;
    margin: 22px 0 4px;
    padding: 12px 16px;
    background: var(--gray-bg);
    border-left: 3px solid var(--text-tertiary);
    border-radius: 2px;
  }
  .empty { color: var(--text-tertiary); font-style: italic; font-size: 13px; }
  a.back { display: inline-block; margin-top: 30px; }
""" + """
</style>
</head>
<body>
  <div class="product-bar">
    <div class="product-mark">FC</div>
    <div class="product-name">AI Finance Controller</div>
    <div class="product-tag">RECONCILIATION</div>
  </div>

  <h1>Reconciliation results</h1>
  <p class="subtitle">Deterministic engine results below are the source of truth. The AI Investigation section is a second opinion on each exception — it never alters these numbers.</p>

  {% set total = result.matched|length + result.mismatched|length + result.exceptions|length %}
  {% set rate_class = 'low' if result.match_rate < 60 else ('mid' if result.match_rate < 80 else '') %}
  <div class="metrics">
    <div class="metric">
      <div class="metric-label">Records</div>
      <div class="metric-value mono">{{ total }}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Matched</div>
      <div class="metric-value mono">{{ result.matched|length }}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Exceptions</div>
      <div class="metric-value mono">{{ result.mismatched|length + result.exceptions|length }}</div>
    </div>
    <div class="metric rate {{ rate_class }}">
      <div class="metric-label">Match rate</div>
      <div class="metric-value mono">{{ result.match_rate }}%</div>
      <div class="rate-bar"><div class="rate-bar-fill {{ rate_class }}" style="width: {{ result.match_rate }}%;"></div></div>
    </div>
  </div>

  <h2>Mismatches</h2>
  <p class="section-sub">Same transaction ID on both sides, but a field doesn't line up.</p>
  {% if result.mismatched %}
  <table>
    <tr><th>Transaction</th><th>Type</th><th class="amount">Internal</th><th class="amount">Bank</th><th class="amount">Difference</th></tr>
    {% for m in result.mismatched %}
    <tr>
      <td class="mono">{{ m.transaction_id }}</td>
      <td><span class="badge exception">{{ m.type }}</span></td>
      <td class="amount">{{ m.internal.amount }}</td>
      <td class="amount">{{ m.bank.amount }}</td>
      <td class="amount {{ 'diff-neg' if m.difference < 0 else 'diff-pos' }}">{{ m.difference }}</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <p class="empty">None — every shared transaction ties out exactly.</p>
  {% endif %}

  <h2>Exceptions</h2>
  <p class="section-sub">The deterministic rules engine could not resolve these automatically.</p>
  {% if result.exceptions %}
  <table>
    <tr><th>Transaction</th><th>Type</th></tr>
    {% for e in result.exceptions %}
    <tr><td class="mono">{{ e.transaction_id }}</td><td><span class="badge exception">{{ e.type }}</span></td></tr>
    {% endfor %}
  </table>
  {% else %}
  <p class="empty">None — every transaction appears on both sides.</p>
  {% endif %}

  {% set ai_items = result.mismatched + result.exceptions %}
  <div class="ai-section-head">
    <h2 style="margin: 0;">AI Investigation</h2>
    <span class="ai-disclaimer">Second opinion on exceptions above — not the source of truth</span>
  </div>

  {% if not result.ai_available %}
  <div class="notice info">
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
      <td class="mono">{{ item.transaction_id }}</td>
      <td><span class="badge exception">{{ item.type }}</span></td>
      {% if item.ai_error %}
      <td colspan="2"><span class="badge unavailable">AI UNAVAILABLE FOR THIS RECORD</span></td>
      <td></td>
      {% else %}
      <td class="mono">{{ item.ai_raw_label }}{% if item.ai_deferred %} <span style="color:var(--text-tertiary);">(leaning)</span>{% endif %}</td>
      <td class="mono">{{ "%.2f"|format(item.ai_confidence) }}</td>
      <td>
        {% if item.ai_deferred %}
          <span class="badge review">NEEDS HUMAN REVIEW</span>
        {% elif item.ai_disagrees %}
          <span class="badge disagrees">AI DISAGREES</span>
        {% else %}
          <span class="badge confirms">AI CONFIRMS</span>
        {% endif %}
      </td>
      {% endif %}
    </tr>
    {% if item.ai_reasoning %}
    <tr class="reasoning-row"><td></td><td colspan="4">{{ item.ai_reasoning }}</td></tr>
    {% endif %}
    {% endfor %}
  </table>
  <p class="note">
    <strong>AI CONFIRMS</strong> — the model's independent read agrees with the rules engine.
    <strong>AI DISAGREES</strong> — the model's independent read differs; both are shown, neither is hidden or overwritten.
    <strong>NEEDS HUMAN REVIEW</strong> — the model's own confidence was too low to trust either way.
  </p>
  {% endif %}

  <p class="note">
    Nothing above is forced or hidden. Every unresolved entry is left exactly as found, for a human to close.
  </p>

  <a class="link back" href="/">&larr; Reconcile another pair</a>
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
        # classify_pair now accepts a list of bank records natively (see
        # agent.py's _describe_bank) and shows the model every duplicate
        # entry, rather than only the first one - previously the model
        # was structurally unable to detect a duplicate since it only
        # ever saw one of the two entries.
        bank_rec = item.get("bank")

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
