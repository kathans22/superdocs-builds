# Ledger — five-country run (Phase 4, Prompts 15-16)

## What's verified precisely

Every number below comes from an actual SuperDocs response's `usage.ops_charged`
field, not an assumption. The remediation round captured in full in this
session (fixing leftover placeholder text and corrupted headings in IN, KE,
FR, SN, BR after the first pass) cost exactly:

| session   | step                                        | ops |
|-----------|----------------------------------------------|-----|
| pack-fr   | fix §6/§8/§9 leftover placeholder text        | 1   |
| pack-sn   | fix §6/§7/§8 leftover placeholder text        | 1   |
| pack-br   | fix §6 body + §9 (partial: 2 of 5 landed)     | 1   |
| pack-ke   | dedupe §7 (attempt 1, did not actually land)  | 1   |
| pack-ke   | dedupe §7 (attempt 2, landed, concurrent-merge notice) | 1 |
| pack-br   | heading-text-only fix attempt (chat, natural language) | 0 (not billable — "nothing changed") |
| pack-br   | heading + §8 fix via chat, chunk-id reference | 0 (not billable — "nothing changed") |
| pack-br   | verbatim `document_html` load (final fix)     | 0 (a document load, not an AI edit) |
| pack-ke   | verbatim `document_html` load (final fix)     | 0 |
| svc-in-1  | verbatim `document_html` load (final fix)     | 0 |
| **remediation round total** |                                 | **5** |

## Why the total is not 7

CLAUDE.md's own economics section prices a pack at **2 operations** (the
annex is replaced in two 2-section batches, not one call), so the idealised
full run is **12 ops** (2 translations + 5 × 2), not 7. The "7 operations"
figure named for this run does not match CLAUDE.md's own worked model, and
is flagged here rather than silently reconciled.

The real total is well above even that 12-op idealised figure. Two
translations (fr, pt) were each derived exactly once and cached — 2 ops,
as designed. Pack generation for IN, KE, FR, SN, BR each cost more than the
idealised 2 ops because of exactly the risk CLAUDE.md's own batch-limit
evidence file warned about: a batch reporting success while only partially
applying, or applying to the wrong chunk (a corrupted `<h2>` heading instead
of the `<p>` body, observed live in BR §6/§7). Recovering from this needed
one or more extra chat turns per affected country before `verify_pack`
could report every section genuinely clean — not claimed clean.

The 5 ops shown above are only the final remediation round, captured with
full per-call precision in this conversation. The original per-country pack
generation (the first annex batch pass for IN, KE, FR, SN, BR, plus the
first translation calls) happened earlier in the same live SuperDocs
session and is not re-itemised here at the same precision, because that
part of the working session was summarised before this report was written.
The account's own promo counter is the honest anchor for the *true* total:
operations remaining dropped from 10,000 granted to **9,964** by the time
every pack verified clean — a spend of **36 ops** against this promotion
grant. Not all of that 36 belongs to this run alone; the account also
carries earlier, unrelated experiment sessions from prior working days
(visible in `list_sessions`, e.g. `session_editor_client_*` from July, and
several early India-pack trial sessions from a prior prompt). Isolating
Phase 4's own share precisely would require reconstructing every chat call
across those, which this report does not claim to have done — the
remediation-round total above (5 ops, itemised) and the qualitative account
of what the extra ops bought (repeated retries against genuine, observed
SuperDocs edit flakiness, not wasted or duplicate work) are what can be
stated with confidence.

## What matters for the demo

Regardless of the exact op count, the two claims the run exists to prove
both hold, verified from the actual exported documents on disk, not
asserted:

- **Core identity is per-language, not per-pack.** FR and SN carry the
  identical locked French core hash (`a240052d99...`); IN and KE carry the
  identical locked English core hash (`aa3a7460e6...`); BR carries its own
  locked Portuguese core hash. See `evidence/integrity-report.json`.
- **Annexes are genuinely distinct, not templated.** All three non-acknowledgement
  annex slots (reporting, legal, escalation) show 5 distinct values across
  the 5 countries — measured by content hash after the same normalisation
  used to lock the core, not claimed from a country name.
