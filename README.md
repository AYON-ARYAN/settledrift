# SettleDrift

**Reconciles a merchant's internal sales ledger against a payment gateway's settlement report — resolves what it's certain of, hands a human exactly what it isn't, and never guesses on the rest.**

Built for the Razorpay AI Buildathon (Track 04: AI Finance Controller).

## The problem

Every merchant on a payment gateway runs two books that are supposed to agree: their own order ledger, and the gateway's settlement report. They rarely agree exactly — fees round differently, refunds land partially, payouts split across UTRs, settlements lag, duplicates creep in, and sometimes one side simply never gets a counterpart. Finance teams reconcile this by hand, in spreadsheets, every month.

SettleDrift automates the boring 80% with zero LLM calls, uses a bounded local model for the ambiguous remainder, and is explicit — down to a per-order audit trail — about exactly what it resolved itself versus what it's asking a human to look at.

## The R1-R6 drift taxonomy

Every ledger/settlement pair that isn't an exact match falls into exactly one of these:

| Class | Meaning | Resolution |
|---|---|---|
| R1 | Fee/GST rounding drift (sub-rupee gap) | Deterministic |
| R2 | Timing lag (amount fine, settlement arrived late) | Deterministic |
| R3 | Partial refund reflected in the ledger's status | Deterministic |
| R4 | Split settlement (one ledger row, 2+ settlement rows) | Agent |
| R5 | Duplicate entry on one side | Agent |
| R6 | Missing counterpart — a true exception | **Always human review** |

R6 is hard-coded as never auto-resolvable in the confidence gate, regardless of how confident the model claims to be — there's nothing on the other side to confirm a match against.

## Architecture

```
ledger.csv, settlement.csv
        │
        ▼
┌───────────────────┐   exact / within-tolerance match on order_id + amount
│ Deterministic      │──────────────────────────────────────────► CLEAN / R1
│ matcher            │   amount OK but settlement lagged >2 days ► R2
│ (matcher.py)       │   ledger status == partially_refunded     ► R3
└─────────┬──────────┘
          │ everything else is genuinely ambiguous
          ▼
┌───────────────────┐
│ Bounded agent      │  reads precomputed evidence (row counts, diff,
│ (agent/investigate)│  lag — never raw arithmetic) for ONE order_id,
│  local Ollama,     │  may request one extra read-only lookup,
│  read-only tools   │  returns {class, confidence, reasoning}.
└─────────┬──────────┘  cannot write back to ledger.csv or settlement.csv.
          ▼
┌───────────────────┐
│ Confidence gate    │  R6 → always needs_review.
│ (gate.py)          │  confidence ≥ threshold → auto_resolved.
└─────────┬──────────┘  else / unparseable output → needs_review.
          ▼
┌───────────────────┐
│ Append-only        │  one JSON line per decision — the run's audit trail.
│ journal (journal.py)│
└─────────┬──────────┘
          ▼
   Honest report.json — match rate, ₹ reconciled, per-class
   precision/recall against ground truth, exception list.
```

The deterministic-first shape is a deliberate echo of [DriftBench](https://github.com/AYON-ARYAN/driftbench), an earlier project of mine on AI agents silently breaking API contracts: **never ask a model to do what a check can already answer with certainty.** R1, R2, and R3 all turned out to be fully deterministic once the right fields (row counts, amount diff, settlement lag, ledger status) are precomputed — so the agent only ever sees the genuinely structural cases (R4 split, R5 duplicate) and the genuine exceptions (R6).

## What the agent actually is

Not a full ReAct loop — a single bounded LLM call per order_id, with evidence retrieval capped at one optional read-only tool call (`get_customer_orders`, for confirming a suspected duplicate). It receives **precomputed** evidence (`diff_rupees_expected_vs_actual`, `settlement_lag_days`, row counts) rather than raw rows to do arithmetic on — an early pilot run showed a 3B local model unreliably eyeballing rupee amounts and confidently mislabeling obvious R3/R2 cases, which is exactly why those two ended up deterministic instead of agent-owned. If the model's output isn't parseable JSON or names an invalid class, a rule-based fallback classifies it and marks it `needs_review` — a flaky model can degrade to "ask a human," never to a silently wrong answer.

Runs entirely on local Ollama (`qwen2.5-coder:3b`) by default — **$0 cost, no API key, nothing leaves the machine.** A Gemini free-tier provider is available as a drop-in alternative (`--provider gemini:gemini-2.5-flash`).

## Results (real run, not illustrative)

120 synthetic transactions, seeded and reproducible (`settledrift gen --seed 42`), run against local `qwen2.5-coder:3b` end to end:

| Metric | Value |
|---|---|
| Match rate (clean + auto-resolved) | **94.2%** (113/120) |
| Orders that needed the LLM at all | **15%** (18/120) — the rest resolved deterministically |
| Overall classification accuracy vs. ground truth | **100%** (120/120) |
| Per-class precision / recall (R1–R6, CLEAN) | **1.00 / 1.00 across every class** |
| Exceptions surfaced for human review | **7** — exactly the 7 true R6 (missing-counterpart) orders, 0 false negatives, 0 false positives |
| Rupees reconciled | ₹13,36,382.17 |
| Wall-clock, full pipeline, local CPU | ~30s |

Full report and per-decision journal for this exact run are checked in at [`examples/sample_run/`](examples/sample_run/) — nothing here is cherry-picked or hand-edited; it's the direct `report.json` and `journal.jsonl` output of one `settledrift reconcile` invocation.

**This did not work on the first try**, and the honest failure path is part of the design, not hidden from it: the first end-to-end run scored 63% overall accuracy, because (a) a reporting bug conflated tolerance-matched R1 orders with clean matches, and (b) the raw-arithmetic evidence bundle led the 3B model to confidently (confidence 1.0) mislabel obvious R3 partial-refunds and R2 timing-lags as R1 rounding drift. Fixing (a) was a straightforward bug fix. Fixing (b) meant recognizing those two classes didn't need a model at all — precomputing the same arithmetic the model was getting wrong and resolving it deterministically, which is what pushed accuracy to 100% and cut LLM calls by 85%. That's the "AI judgment" and "failure recovery" story in one repo: know when the model is the right tool, and know when it demonstrably isn't.

## Usage

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# generate a synthetic corpus (ledger.csv, settlement.csv, ground_truth.jsonl)
settledrift gen --out runs/data --n 120 --seed 42

# run the full pipeline
settledrift reconcile --data runs/data --out runs/out --provider ollama:qwen2.5-coder:3b

# re-print a previous run's report
settledrift report --out runs/out
```

```bash
pytest  # 25 tests: matcher correctness, generator invariants, gate policy,
        # agent tool-call/fallback paths (mocked provider, no Ollama needed),
        # deterministic-shortcut correctness, reporting correctness
```

## Design notes

- **Read-only, always.** The agent's tools (`agent/tools.py`) only ever return copies of in-memory DataFrame rows. Nothing in this codebase writes to `ledger.csv` or `settlement.csv`.
- **R6 can't be argued down.** `NEVER_AUTO_RESOLVABLE` in `taxonomy.py` is checked in the gate before confidence is even looked at.
- **No silent fallback to a wrong answer.** Unparseable model output routes to a rule-based classifier that's deliberately conservative (defaults toward R6/needs-review shapes) and is always marked `needs_review`, never `auto_resolved`.
- **The report is the product.** `report.py` scores predictions against `ground_truth.jsonl` when available and never suppresses a class with zero recall — a class the pipeline is bad at shows up as a bad number, not an omission.

## License

MIT
