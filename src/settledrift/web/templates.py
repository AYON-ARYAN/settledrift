"""The single-page frontend for the local web UI. One static HTML page with
inline CSS/JS, no build step, no CDN — same self-contained ethos as
dashboard.py. Talks to the FastAPI backend via fetch()/EventSource on the
same origin only."""

from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SettleDrift</title>
<style>
  :root {
    --bg: #0b0f14; --panel: #12181f; --border: #1f2833; --text: #e6edf3;
    --muted: #8b98a5; --accent: #4fd1c5; --danger: #e5534b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 2.5rem 1.5rem 4rem; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .wrap { max-width: 760px; margin: 0 auto; }
  h1 { font-size: 1.6rem; margin: 0 0 0.25rem; }
  .subtitle { color: var(--muted); margin: 0 0 2rem; font-size: 0.95rem; }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; }
  label { display: block; font-size: 0.78rem; color: var(--muted); text-transform: uppercase;
          letter-spacing: 0.04em; margin-bottom: 0.3rem; }
  .field { margin-bottom: 1rem; }
  input, select {
    width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    color: var(--text); padding: 0.55rem 0.7rem; font-size: 0.9rem; font-family: inherit;
  }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  button {
    background: var(--accent); color: #04211d; border: none; border-radius: 6px;
    padding: 0.7rem 1.4rem; font-size: 0.9rem; font-weight: 700; cursor: pointer;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .log { background: #060a0e; border: 1px solid var(--border); border-radius: 8px; padding: 1rem;
         font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.78rem; color: var(--muted);
         max-height: 320px; overflow-y: auto; white-space: pre-wrap; }
  .log-line { margin: 0.1rem 0; }
  .log-line.err { color: var(--danger); }
  .progress-track { height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; margin: 0.75rem 0; }
  .progress-fill { height: 100%; background: var(--accent); width: 0%; transition: width 0.2s; }
  .results { display: none; }
  .results.visible { display: block; }
  .result-links a {
    display: inline-block; margin: 0.3rem 0.6rem 0.3rem 0; padding: 0.5rem 1rem;
    border: 1px solid var(--border); border-radius: 6px; color: var(--accent); text-decoration: none; font-size: 0.85rem;
  }
  .result-links a:hover { border-color: var(--accent); }
  iframe { width: 100%; height: 900px; border: 1px solid var(--border); border-radius: 8px; margin-top: 1rem; background: var(--bg); }
  .hint { font-size: 0.78rem; color: var(--muted); margin-top: -0.5rem; margin-bottom: 1rem; }
</style>
</head>
<body>
<div class="wrap">
  <h1>SettleDrift</h1>
  <p class="subtitle">Reconciles a synthetic ledger against a settlement report, live. Deterministic where it can be certain, a bounded local LLM agent for the rest.</p>

  <div class="panel">
    <div class="row">
      <div class="field">
        <label for="n">Transactions</label>
        <input id="n" type="number" value="120" min="10" max="2000">
      </div>
      <div class="field">
        <label for="seed">Seed</label>
        <input id="seed" type="number" value="42">
      </div>
    </div>
    <div class="row">
      <div class="field">
        <label for="provider">Model provider</label>
        <select id="provider">
          <option value="ollama:qwen2.5-coder:3b">ollama:qwen2.5-coder:3b (local, $0)</option>
          <option value="gemini:gemini-2.5-flash">gemini:gemini-2.5-flash (needs GEMINI_API_KEY on the server)</option>
        </select>
      </div>
      <div class="field">
        <label for="threshold">Confidence threshold</label>
        <input id="threshold" type="number" value="0.75" min="0" max="1" step="0.05">
      </div>
    </div>
    <button id="runBtn" onclick="startRun()">Run reconciliation</button>
    <span class="hint" id="hint"></span>
  </div>

  <div class="panel" id="progressPanel" style="display:none">
    <div class="progress-track"><div class="progress-fill" id="progressFill"></div></div>
    <div class="log" id="log"></div>
  </div>

  <div class="panel results" id="results">
    <h2 style="margin-top:0;font-size:1rem;">Run complete</h2>
    <div class="result-links" id="resultLinks"></div>
    <iframe id="dashboardFrame"></iframe>
  </div>
</div>

<script>
let currentJobId = null;

function log(msg, isErr) {
  const el = document.getElementById('log');
  const line = document.createElement('div');
  line.className = 'log-line' + (isErr ? ' err' : '');
  line.textContent = msg;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

async function startRun() {
  const n = parseInt(document.getElementById('n').value, 10);
  const seed = parseInt(document.getElementById('seed').value, 10);
  const provider = document.getElementById('provider').value;
  const threshold = parseFloat(document.getElementById('threshold').value);

  document.getElementById('runBtn').disabled = true;
  document.getElementById('hint').textContent = 'Starting…';
  document.getElementById('progressPanel').style.display = 'block';
  document.getElementById('results').classList.remove('visible');
  document.getElementById('log').innerHTML = '';
  document.getElementById('progressFill').style.width = '0%';

  const resp = await fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({n, seed, provider, threshold}),
  });
  const data = await resp.json();
  currentJobId = data.job_id;
  document.getElementById('hint').textContent = 'Job ' + currentJobId.slice(0, 8) + '…';

  const source = new EventSource('/api/stream/' + currentJobId);
  source.onmessage = (e) => {
    const evt = JSON.parse(e.data);
    if (evt.type === 'status') {
      log('[' + evt.status + '] ' + evt.detail, evt.status === 'error');
      if (evt.status === 'done') {
        onDone();
      }
      if (evt.status === 'error') {
        document.getElementById('runBtn').disabled = false;
      }
    } else if (evt.type === 'progress') {
      const pct = (evt.current / evt.total) * 100;
      document.getElementById('progressFill').style.width = pct + '%';
      log(`[${evt.current}/${evt.total}] ${evt.order_id} -> ${evt.drift_class} (${evt.gate_status}, conf=${evt.confidence.toFixed(2)})`);
    } else if (evt.type === 'close') {
      source.close();
    }
  };
}

async function onDone() {
  document.getElementById('runBtn').disabled = false;
  document.getElementById('progressFill').style.width = '100%';
  const resp = await fetch('/api/report/' + currentJobId);
  const report = await resp.json();

  const links = document.getElementById('resultLinks');
  links.textContent = '';
  const linkSpecs = [
    ['/dashboard/' + currentJobId, 'Open dashboard ↗', '_blank'],
    ['/api/exceptions/' + currentJobId + '.csv', 'Download exceptions.csv', null],
    ['/api/report/' + currentJobId, 'Download report.json', null],
  ];
  for (const [href, text, target] of linkSpecs) {
    const a = document.createElement('a');
    a.href = href;
    a.textContent = text;
    if (target) a.target = target;
    else a.setAttribute('download', '');
    links.appendChild(a);
  }
  document.getElementById('dashboardFrame').src = '/dashboard/' + currentJobId;
  document.getElementById('results').classList.add('visible');
  document.getElementById('hint').textContent =
    `match rate ${(report.match_rate * 100).toFixed(1)}% · accuracy ${(report.overall_classification_accuracy * 100).toFixed(1)}% · ${report.exception_count} exceptions`;
}
</script>
</body>
</html>"""
