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

## SuperDocs features used

All four calls of the minimum contract, over MCP (`api.superdocs.app/mcp`, streamable HTTP,
Bearer auth) — never REST, and never a reimplementation of SuperDocs' own editing:

- **`upload_document_base64`** — loads `config/policy-master.md` (and, for a non-English
  pack, that language's locked core assembled with the country's own annexes) into a
  session. Loading a document is free.
- **`chat`** — the only billed step. Two distinct uses, deliberately kept separate:
  - *Annex localisation*: edit instructions name only annex sections (6–9), sent in
    `annex_batch_size`-sized batches per `config/manifest.yaml`. Core sections are never
    named in any instruction sent to SuperDocs.
  - *Core translation*: the one legitimate place in the codebase that names core sections
    — structurally isolated in `translate.py`, which never imports `packs.py`, so
    `packs.assert_no_core_sections_named` can never see it.
  - Also used, as a documented fallback (`chat(document_html=...)`), to load a verbatim
    corrected document back in when a natural-language edit repeatedly failed to land on
    a specific chunk — a document load, not an AI edit, so it is free.
- **`export_document`** — every pack, acknowledgement form, and change notice is exported
  to Markdown and DOCX. Exports never cost operations, so verification (re-extract,
  re-hash, compare) always runs against the real exported artifact, never the chat
  response's own claim.
- **Double-parse handling** — `mcp_client.parse_proposed_changes()` handles both the
  already-an-object shape (`document_changes.pending_changes` on a sync `chat` call) and
  the double-encoded shape (`intermediate_responses[].content` as a JSON string, on the
  `chat_async`/job path), so nothing downstream re-implements that parse.
- **Operations ledger** (`ledger.py`) — every call is charged from the response's real
  `usage.was_billable` / `usage.ops_charged` fields, never an assumed constant. A preview
  call is free; only an applied edit is billed — discovered live, not documented.

**Not used:** `chat_async` + `approve_change` for the pack/notice path. Live testing
(Prompt 10) found `approve_change` only works against a `chat_async` job, not a
synchronous `chat` preview — the docs describe it as the HITL partner for both without
flagging that only the async path has something to approve against. This build uses
synchronous `chat` with `approve_all` throughout instead, and enforces correctness by
re-verifying the export afterward rather than trusting an approval step that doesn't
actually gate anything on this path. Full detail:
[`PROGRESS.md`](PROGRESS.md#phase-2), [`evidence/superdocs-batch-limit-report.md`](evidence/superdocs-batch-limit-report.md).

## The per-language core derivation

"Identical across all packs" and "in the working language" are in tension: a translated
core cannot be byte-identical to the English source. The resolution is that core identity
is **per-language**, not per-document — each language's core is derived exactly once and
hash-locked, and every pack in that language carries that identical locked text.

```
                    English core (source, authoritative)
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                  ▼                  ▼
             EN core             FR core             PT core
          hash aa3a7460…       hash a240052d…      hash 4d339a73…
            (locked)              (locked)             (locked)
                 │                  │                     │
         ┌───────┴───────┐  ┌───────┴───────┐             │
         ▼               ▼  ▼               ▼             ▼
      India (IN)     Kenya (KE)      France (FR)   Senegal (SN)   Brazil (BR)
      hash aa3a…      hash aa3a…     hash a240…     hash a240…    hash 4d33…
```

**France and Senegal — two countries, two entirely different annexes — share one core
hash.** That equality is not asserted; it is read directly off five independently
generated, live-exported packs (`evidence/integrity-report.json`):

| Language | Packs | Core hash | Identical? |
|---|---|---|---|
| en | IN, KE | `aa3a7460e6602b04e59acbe8ef73be464c3951624b50903a61b548ce64e186e8` | ✅ |
| fr | FR, SN | `a240052d992b3f53af2332edd0ffe62172b87e6a963c3c8dd4dfef4d47dafa58` | ✅ |
| pt | BR | `4d339a737d5ea69c3bfd38ee983f779243c219ba869e1e9df443bb98ef7cf9b8` | ✅ (n=1) |

Annex divergence, counted the same way: `reporting` 5/5 distinct, `legal` 5/5 distinct,
`escalation` 5/5 distinct — five countries producing five genuinely different annexes,
not a name swapped into a shared paragraph.

## Credit

Built by Kathan Shah (`kathans22`) for the SuperDocs Round 2 hiring task.

## License

MIT.
