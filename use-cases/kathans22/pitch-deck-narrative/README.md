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

## License

MIT
