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

## The two ledgers — Run 1 (rollout) and Run 2 (amendment)

Both tables below are the real, live-measured totals, not the idealised model. The
idealised model (CLAUDE.md's worked example) prices a full 5-country rollout and a
core amendment reaching all 5 offices at the same 7 operations each — the equivalence
the build exists to demonstrate: **an update should cost like an update, not like a
reissue.** The real runs cost more than 7 in both directions, for the same root cause
in both directions: live SuperDocs `chat` edit calls do not reliably apply on the first
attempt, and a failed attempt can still be billed. Every extra operation below is a
retry recovering from that, not wasted or duplicate work — see
[`evidence/ledger-summary.md`](evidence/ledger-summary.md) and
[`evidence/run2-ledger.md`](evidence/run2-ledger.md) for the full detail.

### Run 1 — initial rollout (idealised model, corrected economics per CLAUDE.md)

The build's original design doc priced a pack at 1 operation (one batched call for all
4 annex sections). Live testing (`evidence/superdocs-batch-limit-report.md`) proved that
call is not reliable — a 4-section batch can report full success while changing nothing
— so the design was corrected to 2 batches of 2 sections, and the idealised per-pack
cost is **2 operations**, not 1:

```
[lock]      core v1 locked, 5 sections, hash aa3a7460          0 ops
[translate] fr ← en                                            1 op
[translate] pt ← en                                            1 op
[pack]      IN  en  annexes 6-9, 2 batches of 2                2 ops
[pack]      KE  en  annexes 6-9, 2 batches of 2                2 ops
[pack]      FR  fr  annexes 6-9, 2 batches of 2                2 ops
[pack]      SN  fr  annexes 6-9, 2 batches of 2                2 ops
[pack]      BR  pt  annexes 6-9, 2 batches of 2                2 ops
[ack]       5 acknowledgement forms                            0 ops
[verify]    core identity ......................... PASS
                                                        ───────
                                               total    12 ops
```

**Real Run 1 cost more, and was not cleanly isolated to a single figure** — see
`evidence/ledger-summary.md`. What was captured at full precision was the final
remediation round (fixing leftover placeholder text and wrong-chunk edits across
IN/KE/FR/SN/BR after the first annex pass):

| step | ops |
|---|---|
| pack-fr — fix §6/§8/§9 leftover placeholder text | 1 |
| pack-sn — fix §6/§7/§8 leftover placeholder text | 1 |
| pack-br — fix §6 body + §9 (partial: 2 of 5 landed) | 1 |
| pack-ke — dedupe §7, attempt 1 (did not land) | 1 |
| pack-ke — dedupe §7, attempt 2 (landed, concurrent-merge notice) | 1 |
| pack-br — heading-text fix via chat, natural language | 0 (not billable) |
| pack-br — heading + §8 fix via chat, chunk-id reference | 0 (not billable) |
| pack-br / pack-ke / svc-in-1 — verbatim `document_html` reload (final fix) | 0 (a document load, not an edit) |
| **remediation round total** | **5** |

The account's promo counter is the honest anchor for the true full Run 1 total: it
dropped from 10,000 to 9,964 across the working session that produced all five clean
packs — a 36-op spend, not all of which is cleanly attributable to this run alone (the
account also carries earlier, unrelated experiment sessions). The 5-op remediation
round above is what is stated with full confidence.

### Run 2 — core amendment, v1 → v2 (section 4 only)

Idealised model:

```
[diff]        core v1 → v2: section 4 changed, 1 of 5           0 ops
[translate]   section 4 → fr                                    1 op
[translate]   section 4 → pt                                    1 op
[notice]      IN  en  1 section, 3 unchanged                    1 op
[notice]      KE  en                                            1 op
[notice]      FR  fr                                            1 op
[notice]      SN  fr                                            1 op
[notice]      BR  pt                                            1 op
                                                        ───────
                                                total     7 ops
```

Real ledger, live, `evidence/run2-ledger.md`:

```
[diff]        core v1 → v2: section 4 changed, 1 of 5           0 ops
[retranslate] fr (section 4 only)                                1 op
[retranslate] pt (section 4 only)                                1 op
[notice]      IN  en  attempt 1 — billed, changes: null           1 op
[notice]      IN  en  attempt 2 — landed                          1 op
[notice]      SN  fr  attempt 1 — landed                          1 op
[notice]      KE  en  attempt 1 — billed, changes: null           1 op
[notice]      KE  en  attempt 2 — landed                          1 op
[notice]      FR  fr  attempt 1 — landed                          1 op
[notice]      BR  pt  attempt 1 — landed                          1 op
                                                        ───────
                                                total     9 ops
```

**9 operations, not 7.** Two of the five notices (IN, KE) needed a retry: attempt 1
came back billed (`usage.was_billable: true, ops_charged: 1`) with a confused
non-edit response and `changes: null`. `send_change_notice` never trusts the response
text — it exports and checks the placeholder is actually gone before declaring
success, and both retried cleanly on attempt 2. **Zero packs were reissued** — every
notice was generated against the existing v1 packs on disk, re-verified afterward
against the v1 lock, not the new v2 lock, because no pack changed.

### The comparison that matters

| | Run 1 — full rollout | Run 2 — core amendment |
|---|---|---|
| Scope | 5 countries, 3 languages, 5 packs produced | Same 5 countries, 3 languages, **0 packs reissued** |
| Idealised operations | 2 translations + 5 packs × 2 = **12** | 2 re-translations + 5 notices × 1 = **7** |
| Real operations | 36-op session total; 5 ops isolated at full precision (remediation round) | **9**, fully and cleanly isolated |
| What ships | 5 full policy packs | 5 short (2–3 page) change notices |

**A logged tension, not silently resolved:** an earlier version of this design priced a
pack at 1 batched operation, making Run 1 and Run 2 both 7 ops — a clean symmetry. Live
testing proved that 1-call batch unreliable and forced the correction above to 2 batches
per pack, which breaks that symmetry (12 vs. 7). What the correction does *not* change is
the actual point being demonstrated: a **notice** is a single-document call, not a
multi-section annex batch, so its own idealised cost stayed at 1 operation regardless —
the amendment path was never going to inherit the pack-batching cost, because it never
batches. The real, honestly-itemised comparison is 12 real-adjacent ops to stand up the
whole rollout once, versus **9 real ops to propagate one core change to all five offices
with zero reissues** — an update that costs a fraction of standing the system up, which
is the claim this build exists to prove.

## Credit

Built by Kathan Shah (`kathans22`) for the SuperDocs Round 2 hiring task.

## License

MIT.
