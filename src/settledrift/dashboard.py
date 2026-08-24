"""Renders a self-contained HTML dashboard from a run's report.json +
journal.jsonl. No external assets, no JS framework, no network calls — opens
directly from disk, consistent with the pipeline's own $0-cost, nothing-
leaves-the-machine ethos."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

CLASS_ORDER = ["CLEAN", "R1", "R2", "R3", "R4", "R5", "R6"]
CLASS_LABELS = {
    "CLEAN": "Clean match",
    "R1": "R1 · Fee/GST rounding",
    "R2": "R2 · Timing lag",
    "R3": "R3 · Partial refund",
    "R4": "R4 · Split settlement",
    "R5": "R5 · Duplicate entry",
    "R6": "R6 · Missing counterpart",
}


def _bar(pct: float) -> str:
    pct = max(0.0, min(1.0, pct)) * 100
    return (
        f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>'
    )


def _fmt_pct(v: float | None) -> str:
    return f"{v * 100:.1f}%" if v is not None else "—"


def _metric_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="metric-sub">{html.escape(sub)}</div>' if sub else ""
    size_class = " metric-value-long" if len(value) > 9 else ""
    return f"""
    <div class="metric-card">
      <div class="metric-value{size_class}">{html.escape(value)}</div>
      <div class="metric-label">{html.escape(label)}</div>
      {sub_html}
    </div>"""


def _class_rows(per_class: dict[str, Any]) -> str:
    rows = []
    for cls in CLASS_ORDER:
        s = per_class.get(cls)
        if s is None:
            continue
        label = CLASS_LABELS.get(cls, cls)
        recall = s.get("recall")
        precision = s.get("precision")
        rows.append(f"""
        <tr>
          <td class="cls-name">{html.escape(label)}</td>
          <td class="num">{s['true_count']}</td>
          <td class="num">{s['predicted_count']}</td>
          <td class="num">{s['correct']}</td>
          <td>{_bar(precision or 0)}<span class="pct">{_fmt_pct(precision)}</span></td>
          <td>{_bar(recall or 0)}<span class="pct">{_fmt_pct(recall)}</span></td>
        </tr>""")
    return "\n".join(rows)


def _exception_rows(exceptions: list[dict]) -> str:
    if not exceptions:
        return '<tr><td colspan="4" class="empty">No exceptions in this run.</td></tr>'
    rows = []
    for e in exceptions:
        rows.append(f"""
        <tr>
          <td class="mono">{html.escape(e['order_id'])}</td>
          <td><span class="badge badge-{html.escape(e['predicted_class'])}">{html.escape(e['predicted_class'])}</span></td>
          <td class="num">{e['confidence']:.2f}</td>
          <td class="reason">{html.escape(e['reason'])}</td>
        </tr>""")
    return "\n".join(rows)


def render_dashboard(report: dict, journal: list[dict], title: str = "SettleDrift Run") -> str:
    total = report["total_orders"]
    clean_exact = report["clean_exact"]
    clean_tolerance = report["clean_tolerance"]
    auto = report["agent_auto_resolved"]
    review = report["agent_needs_review"]
    match_rate = report.get("match_rate")
    accuracy = report.get("overall_classification_accuracy")
    rupees = report.get("rupees_reconciled", 0)

    n_llm_calls = sum(1 for r in journal if r.get("event") == "investigated")
    n_deterministic = sum(1 for r in journal if r.get("event") == "deterministic_resolved")

    funnel_rows = [
        ("Total orders", total, total),
        ("Deterministic clean (exact + tolerance)", clean_exact + clean_tolerance, total),
        ("Deterministic drift-class shortcuts (R2/R3)", n_deterministic, total),
        (f"Agent-investigated ({n_llm_calls} LLM calls)", n_llm_calls, total),
        ("Auto-resolved by confidence gate", auto, total),
        ("Sent to human review", review, total),
    ]
    funnel_html = "\n".join(
        f"""
        <div class="funnel-row">
          <div class="funnel-label">{html.escape(label)}</div>
          {_bar(count / base if base else 0)}
          <div class="funnel-count">{count}</div>
        </div>"""
        for label, count, base in funnel_rows
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  :root {{
    --bg: #0b0f14; --panel: #12181f; --border: #1f2833; --text: #e6edf3;
    --muted: #8b98a5; --accent: #4fd1c5; --gold: #d4af37; --danger: #e5534b;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 2.5rem 1.5rem 4rem; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 0.25rem; }}
  .subtitle {{ color: var(--muted); margin: 0 0 2rem; font-size: 0.95rem; }}
  .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; margin-bottom: 2.5rem; }}
  .metric-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.1rem; }}
  .metric-value {{ font-size: 1.6rem; font-weight: 700; color: var(--accent);
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .metric-value-long {{ font-size: 1.15rem; }}
  .metric-label {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.2rem; }}
  .metric-sub {{ font-size: 0.72rem; color: var(--muted); margin-top: 0.35rem; }}
  h2 {{ font-size: 1.05rem; margin: 0 0 1rem; padding-top: 1.5rem; border-top: 1px solid var(--border); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{ text-align: left; color: var(--muted); font-weight: 600; font-size: 0.72rem;
        text-transform: uppercase; letter-spacing: 0.04em; padding: 0.4rem 0.6rem; }}
  td {{ padding: 0.55rem 0.6rem; border-top: 1px solid var(--border); vertical-align: middle; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.cls-name {{ white-space: nowrap; }}
  td.mono {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.78rem; color: var(--muted); }}
  td.reason {{ color: var(--muted); font-size: 0.8rem; }}
  td.empty {{ text-align: center; color: var(--muted); padding: 1.5rem; }}
  .bar-track {{ display: inline-block; width: 90px; height: 6px; background: var(--border);
                border-radius: 3px; overflow: hidden; vertical-align: middle; margin-right: 0.5rem; }}
  .bar-fill {{ height: 100%; background: var(--accent); }}
  .pct {{ font-size: 0.78rem; color: var(--muted); font-variant-numeric: tabular-nums; }}
  .badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.72rem;
            font-weight: 600; background: rgba(229,83,75,0.15); color: var(--danger); }}
  .funnel-row {{ display: grid; grid-template-columns: 260px 1fr 50px; align-items: center; gap: 0.75rem;
                 padding: 0.5rem 0; font-size: 0.85rem; }}
  .funnel-label {{ color: var(--muted); }}
  .funnel-count {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }}
  .funnel-row .bar-track {{ width: 100%; margin-right: 0; }}
  footer {{ margin-top: 3rem; color: var(--muted); font-size: 0.75rem; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{html.escape(title)}</h1>
  <p class="subtitle">Deterministic ledger/settlement reconciliation, with a bounded local-LLM agent for the genuinely ambiguous remainder.</p>

  <div class="metrics">
    {_metric_card("Match rate", _fmt_pct(match_rate), f"{clean_exact + clean_tolerance + auto}/{total} orders")}
    {_metric_card("Classification accuracy", _fmt_pct(accuracy), "vs. ground truth")}
    {_metric_card("₹ Reconciled", f"₹{rupees:,.2f}")}
    {_metric_card("LLM calls needed", str(n_llm_calls), f"{n_llm_calls/total*100:.0f}% of {total} orders")}
    {_metric_card("Sent to human review", str(review), "true exceptions only" if review else "")}
  </div>

  <h2>Resolution funnel</h2>
  {funnel_html}

  <h2>Per-class precision / recall (vs. ground truth)</h2>
  <table>
    <thead><tr><th>Class</th><th class="num">True</th><th class="num">Predicted</th><th class="num">Correct</th><th>Precision</th><th>Recall</th></tr></thead>
    <tbody>
      {_class_rows(report.get("per_class", {}))}
    </tbody>
  </table>

  <h2>Exceptions — sent to human review</h2>
  <table>
    <thead><tr><th>Order ID</th><th>Predicted class</th><th class="num">Confidence</th><th>Reason</th></tr></thead>
    <tbody>
      {_exception_rows(report.get("exceptions", []))}
    </tbody>
  </table>

  <footer>Generated by settledrift · {total} orders · {n_llm_calls} LLM calls · {n_deterministic} deterministic drift-class shortcuts</footer>
</div>
</body>
</html>"""


def write_dashboard(report: dict, journal: list[dict], out_path: Path, title: str = "SettleDrift Run") -> None:
    out_path.write_text(render_dashboard(report, journal, title=title))
