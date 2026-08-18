# ClarityDocs pitch-script narrative generator

A SuperDocs-backed generator that writes **vertical-specific sales speaking scripts** for one invented product — **ClarityDocs**, a document-AI assistant — across legal, fintech, healthcare, and edtech.

Each vertical gets a nine-section script: heading, talking point, full speaker notes, and an optional presenter visual. The deliverable is a **speaking script document** (markdown / DOCX). It is **not** a slide deck and is not meant to look like one.

Built **on** SuperDocs (MCP): upload → batched chat fill → approve → export. Divergence between verticals is **measured** (lexical overlap), not asserted.

## Setup

```text
# From this folder (use-cases/kathans22/pitch-deck-narrative)
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -e .

cp .env.example .env
# Put a real SuperDocs API key in .env (never commit .env)
```

Requires Python 3.12+. Optional UI: Node 20+ in `ui/`.

## Run

```text
# Generate one vertical (idempotent for the current manifest version)
python -m generator run --vertical legal
python -m generator run --vertical fintech
python -m generator run --vertical healthcare
python -m generator run --vertical edtech

# Force regenerate (costs ops again)
python -m generator run --vertical legal --force

# Score divergence across on-disk scripts (0 SuperDocs ops)
python -m generator score --from evidence/narratives

# API (non-blocking generate)
uvicorn generator.api.app:app --reload
# POST /generate?vertical=legal → 202 {run_id}; poll GET /runs/{run_id}

# Divergence UI
cd ui && npm install && npm run dev
# Optional: keep API on :8000 so Generate / Narratives can proxy /api
```

Exports land under `out/` (gitignored). Reviewable copies for this build live in `evidence/narratives/`.

## Demo / screenshots

Place demo captures here when recording the ship walkthrough (filenames are placeholders until screenshots exist):

| Asset | Intended capture |
|---|---|
| `docs/demo/divergence-pass.png` | Divergence screen: Pass, vertical mean vs shared mean, pair×section grid |
| `docs/demo/narratives-fintech.png` | Narratives screen: fintech speaker notes + presenter visual |
| `docs/demo/speaking-script-excerpt.png` | Markdown/DOCX export showing the “Speaking script — not a slide deck” line |

Until those files exist, open `ui/` (`npm run dev`) and the scripts under `evidence/narratives/`.

## Credit

Built for the SuperDocs Task 2 use-case track (Build 2 — industry pitch-deck narrative generator) against [superdocsapp/superdocs-builds](https://github.com/superdocsapp/superdocs-builds).

## SuperDocs features used

| Capability | How this build uses it |
|---|---|
| Document upload | Nine-section speaking-script skeleton (HTML) uploaded into a session |
| Chat edits | Batched section fill (default **2** sections per call) from vertical YAML knowledge |
| Approve / landed-check | Proposed changes double-parsed; section bodies compared pre/post; failed sections split-retried alone |
| Export | Markdown + DOCX speaking scripts (`pitch-script-<vertical>-claritydocs.*`) |
| Image generation (chat) | Presenter visuals only where `image_eligible` **and** the content heuristic says warranted — billed as normal chat ops, not a separate SKU |
| MCP | Generator drives SuperDocs over streamable HTTP MCP with bearer auth |

Surfaces not required for the bar (multi-doc sessions, templates library UI, etc.) stay unused on purpose.

## Divergence report (measured)

Source: `evidence/divergence-report.json` (rescored after the cleaned four-vertical scripts). Method: **word Jaccard** pairwise overlap. Gates: vertical mean **&lt; 0.40**; no vertical-tagged cell **≥ 0.55**. Shared sections are reported, not gated.

| Metric | Value |
|---|---|
| Verdict | **PASS** |
| Mean vertical overlap | **0.192** |
| Mean shared overlap | **0.219** |
| Vertical pair×section cells | 36 |
| Shared pair×section cells | 18 |
| Hot vertical cells (≥ 0.55) | none |

Per-pair mean overlap (vertical-tagged sections only):

| Pair | Mean vertical | Mean shared |
|---|---|---|
| edtech ↔ fintech | 0.192 | 0.234 |
| edtech ↔ healthcare | 0.191 | 0.216 |
| edtech ↔ legal | 0.195 | 0.227 |
| fintech ↔ healthcare | 0.202 | 0.218 |
| fintech ↔ legal | 0.188 | 0.227 |
| healthcare ↔ legal | 0.185 | 0.192 |

Highest vertical cells (still under the 0.55 gate): edtech↔legal §6 **0.293**; healthcare↔legal §6 **0.280**; edtech↔fintech §8 **0.279**.

Full pair×section matrix: open the Divergence screen (`ui/`, `#/divergence`) or the JSON report.

## Ledger total

| Run | Ops charged |
|---|---|
| Four-vertical narrative generation (`evidence/ledger-four-verticals.json`) | **39** |
| Live image insert (8 warranted figures × 1 chat op) | **+8** |
| CLAUDE.md happy-path estimate (4 × 5 batches) | ~20 |

Export, download, format guard, and divergence scoring are **0** ops. Actual generation ran ~2× the happy-path floor because landed-check split-retries billed extra chat calls. Still well inside the 10,000-op budget. See `evidence/ops-reconciliation.md`.

## License

MIT
