# Run 2 — core amendment (v1 → v2) — real ledger

Live run, 2026-08-15 to 2026-08-16, section 4 amended (24-hour reporting deadline
added — see `config/policy-master.md` vs `config/policy-master-v1.md`).

## The idealised model (CLAUDE.md, build1 doc)

```
[diff]      core v1 → v2: section 4 changed, 1 of 5          0 ops
[translate] section 4 → fr                                   1 op
[translate] section 4 → pt                                   1 op
[notice]    IN  en  1 section, 3 unchanged                   1 op
[notice]    KE  en                                           1 op
[notice]    FR  fr                                           1 op
[notice]    SN  fr                                           1 op
[notice]    BR  pt                                           1 op
                                                    ───────
                                            total     7 ops
```

## What actually happened, real ledger

```
[diff]      core v1 → v2: section 4 changed, 1 of 5          0 ops
[retranslate] fr (section 4 only)                            1 op
[retranslate] pt (section 4 only)                             1 op
[notice]    IN  en  attempt 1 — billed, changes: null         1 op
[notice]    IN  en  attempt 2 — landed                        1 op
[notice]    SN  fr  attempt 1 — landed                        1 op
[notice]    KE  en  attempt 1 — billed, changes: null         1 op
[notice]    KE  en  attempt 2 — landed                        1 op
[notice]    FR  fr  attempt 1 — landed                        1 op
[notice]    BR  pt  attempt 1 — landed                        1 op
                                                    ───────
                                            total     9 ops
```

**9 operations, not the idealised 7.** Two of the five notice calls (IN, KE) needed
a retry: the first attempt came back billed (`usage.was_billable: true,
ops_charged: 1`) with a confused non-edit response — *"I am not sure how to help
you because your request was unclear"* (IN) / *"I am ready to help, but I'm not
sure what you need"* (KE) — and `changes: null`. `send_change_notice` never trusts
the response text; it exports and checks the placeholder is actually gone before
declaring success. Both times the placeholder ("Summary pending.") was still
present after attempt 1, so the bounded retry (`_MAX_NOTICE_ATTEMPTS = 2`) fired,
and both landed cleanly on attempt 2. SN, FR, and BR landed on the first attempt.

This is the same class of live SuperDocs unreliability already documented for
pack batches in `evidence/superdocs-batch-limit-report.md` (a billed call that
changes nothing) — here observed on a single-section document call instead of a
multi-section batch, confirming it is not specific to batching.

## Zero packs reissued

No `packs.generate_pack` call was made anywhere in this run. All five packs
(`out/{IN,KE,FR,SN,BR}/policy-pack.{md,docx}`) are untouched, still exactly the
v1-core packs generated in Phase 4 — `service.verify_after_amendment` re-verified
each one against the v1 lock (the version it actually carries) and confirmed
`passed: true`, `unlocalised_annex_sections: []` for all five. See
`evidence/run2-integrity-report.json`.

## Full ledger scope note

The persisted `state/ledger.json` also carries earlier Phase 3/4 pack-generation
entries (India's annex-batch retries, etc.) — this file's "9 ops" figure is scoped
to only the amendment steps (`retranslate` and `notice` entries), matching what
CLAUDE.md's "Run 2" is actually measuring: the cost of propagating one core
amendment, not the cost of the original rollout.
