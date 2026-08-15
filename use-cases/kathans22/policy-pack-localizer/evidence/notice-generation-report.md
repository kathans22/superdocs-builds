# Change notice generation — live proof (Mumbai, Senegal)

Ran `amend.send_change_notice` for IN and SN, via the real SuperDocs MCP tools, on
2026-08-15, against the real core v1→v2 diff (section 4) from Prompts 18–19.

## What each notice carries

Header (office name and code, "core v1 → v2", date), the exact summary line
`"1 section changed of 5. Sections 1, 2, 3, 5 unchanged."`, Section 4 quoted verbatim
before and after (from the archived `policy-master-v1.md` / current `policy-master.md`
for English, from the locked `fr` translation for French), a plain-language "what
changed" paragraph, the action required with a return date (2026-08-29, 14 days out),
and the explicit annexes-6–9-unchanged line — all in the office's working language.

## Senegal (fr) — landed on the first attempt

```
[upload]                                                 0 ops
[chat] notice summary SN (attempt 1)                     1 op
[export-markdown]                                        0 ops
[export-docx]                                            0 ops
                                                        -------
total                                                     1 op
```

The model's response: *"J'ai remplacé l'espace réservé par le résumé des
modifications dans la section 4 (Conduite Interdite), précisant l'obligation de
signalement sous 24 heures."* — and it did: the exported document's "Ce qui a
changé" paragraph reads *"La politique de conduite interdite a été mise à jour
pour inclure une obligation formelle de signaler toute violation dans un délai de
24 heures..."*, with both quoted blocks (Auparavant/Désormais) byte-identical to
the locked `fr` core text.

## Mumbai (en) — needed one retry

```
[upload]                                                 0 ops
[chat] notice summary IN (attempt 1)                     1 op   <- billed, did not land
[export-markdown]                                        0 ops
[chat] notice summary IN (attempt 2)                     1 op   <- landed
[export-markdown]                                        0 ops
[export-docx]                                            0 ops
                                                        -------
total                                                     2 ops
```

The first call's response was `"I am not sure how to help you because your request
was unclear. Could you please let me know what you would like assistance with
today?"` with `changes: null` in the response body — yet `usage.was_billable: true,
ops_charged: 1`. This is the exact class of live SuperDocs unreliability already
documented for pack generation in `evidence/superdocs-batch-limit-report.md` (a
billed call that changes nothing), now observed on a single-section document
instead of a batch. Exporting after the first attempt confirmed the placeholder
("Summary pending.") was still present — so `send_change_notice` never trusted the
response text, retried once (`_MAX_NOTICE_ATTEMPTS = 2`), and the second attempt
landed cleanly.

**Fix landed in code, not worked around by hand**: `send_change_notice` now
retries up to `_MAX_NOTICE_ATTEMPTS` times, checking the exported document (never
the chat response) after each attempt, and charges every attempt honestly via the
ledger — a notice that needs a retry costs 2 operations, not the idealised 1.

## Combined cost for this pair

3 operations for 2 countries (1 + 2), not the idealised 2 — the ledger records
what actually happened. CLAUDE.md's "1 op per country" is the clean-run figure;
a run that needs a retry costs more, exactly as Phase 3/4's pack-generation
figures were corrected for the same reason.

## Integrity check

For both countries, after the summary landed: the placeholder no longer appears
anywhere in the export, and both the "Previously" and "Now" quoted section bodies
still match the locked/archived text verbatim (via `corelock.normalise`) — the
model touched only the one paragraph it was asked to touch.

Full notices saved at `out/{IN,SN}/change-notice-v1-v2.{md,docx}` (gitignored, per
CLAUDE.md — `out/` is never committed).
