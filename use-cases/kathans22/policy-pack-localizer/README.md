# Policy Pack Localizer

Built for the SuperDocs Round 2 hiring task.

One master safeguarding policy in, five country-specific packs out — each in the
office's working language, each carrying the identical, hash-locked protected core,
each with genuinely distinct local annexes. When the core is amended, every office
gets a short change notice naming exactly what moved, not a reissued document.

## What it does, in plain language

A safeguarding lead at an NGO ("Meridian Relief Trust", invented for this build) writes
one policy. Sections 1–5 are the non-negotiable core — the text legal has signed off.
Sections 6–9 are annex slots — reporting channels, applicable law, escalation path,
acknowledgement — and are genuinely different per country, because the underlying legal
reality is different in Mumbai, Nairobi, Lyon, Dakar, and Recife.

This tool:

1. **Locks the core.** Hashes each core section and their concatenation, per language.
   Zero SuperDocs operations — arithmetic, not intelligence.
2. **Generates a pack per country** — the locked core, verbatim, plus that country's
   own annex content, in that country's working language.
3. **Verifies every export**, not just its own claim. Re-extracts the core from the
   exported document, re-hashes it, compares against the lock. A mismatch quarantines
   the pack — it is not shipped, and the run does not report success.
4. **Produces an acknowledgement form** per office — built deterministically from known
   fields, no model call.
5. **Handles a core amendment as an update, not a reissue.** When a core section
   changes, only that section is re-translated (once per affected language, not once
   per country), and every office gets a short change notice — what changed, what
   didn't, what to do. No pack is regenerated.

The claim this build makes provable, not just assertable: **France and Senegal — two
countries, two entirely different annexes — carry byte-identical core text.** That is
the demonstration this whole design exists to produce. See
[`evidence/integrity-report.json`](evidence/integrity-report.json) for the real,
live-verified hashes.

## How to run it

Requires Python 3.12+, Node 18+, and a SuperDocs API key
(`SUPERDOCS_API_KEY=your-key-here` — see `.env.example`).

### Backend

```bash
cd use-cases/kathans22/policy-pack-localizer
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
cp .env.example .env   # fill in SUPERDOCS_API_KEY
```

Run the full pipeline for one or more countries from the command line:

```bash
python -m localizer run --countries IN,KE,FR,SN,BR
```

This locks the core (once), derives each language's core translation (once, cached),
and generates a pack per country, printing per-country OK/SKIPPED and the operations
ledger. Re-running it is free — already-produced packs are not re-bought.

Run the tests (no live API key needed — they run against recorded fixtures and fakes):

```bash
pytest
```

Serve the API (used by the React UI, and drives rollouts/amendments as background jobs):

```bash
uvicorn localizer.api.app:app --reload --port 8000
```

### Frontend

```bash
cd ui
npm install
npm run dev
```

Opens on `http://localhost:5173`, proxying `/api` to the backend on `:8000` (dev only —
see Limitations). Five screens: Countries, Generate, Packs, Integrity, Amend.

### Demo

- Video: `[demo link placeholder]`
- Screenshot: `[screenshot placeholder — Integrity screen, the hero shot]`

## Credit

Built by Kathan Shah (`kathans22`) for the SuperDocs Round 2 hiring task.

## License

MIT.
