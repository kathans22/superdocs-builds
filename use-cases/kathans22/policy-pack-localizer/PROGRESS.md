# Progress

## Phase 0 — Ground (Session 1)
Scaffolded the package (`src/localizer/*`, `config/`, `out/`, `state/`, `evidence/`, `tests/`),
`.gitignore`/`.env.example`, and `pyproject.toml` (Python 3.12, fastapi/uvicorn/pyyaml/httpx/mcp).
`python -c "import localizer"` passes.

## Phase 1 — The spine, no model calls (Session 2)
Built and proved the integrity mechanism on hand-made files, with no SuperDocs calls involved:

- `config/policy-master.md` — the 9-section Meridian Relief Trust policy (5 core, 4 annex
  placeholders) — and `config/manifest.yaml` declaring the core/annex split and annex slots.
- Five country packs (`config/countries/{IN,KE,FR,SN,BR}.yaml`), each with genuinely distinct
  reporting channels, legal instruments, and escalation tiers; FR/SN in French, BR in Portuguese.
- `config.py` — loads and validates the manifest and every country file, failing loudly with
  the specific missing field.
- `sections.py` — parses `policy-master.md` into numbered sections by heading boundary, and
  asserts the parsed headings match the manifest exactly.
- `corelock.py` — the mechanism the whole build rests on: `normalise()`, `lock()`,
  `save_lock`/`load_lock`, `verify()`.

**Proven, by `tests/test_corelock.py` (8 tests, all passing):**
- Identical core content in two different files produces one identical `core_hash`.
- A one-word change to a core section changes exactly that section's hash and the `core_hash`;
  the other core sections' hashes are untouched.
- Changing an annex section changes neither a core section hash nor the `core_hash`.
- Round-trip resilience, one test per mutation: quote style, trailing whitespace, blank-line
  runs, line endings, list marker style — each proven to leave the `core_hash` unchanged.

**The normalisation contract, in one sentence:** `normalise()` canonicalises Unicode form,
line endings, quote style, dash-glyph family, space-character family, list-marker glyphs,
blank-line runs, and incidental whitespace — while leaving case and all actual wording,
numbers, and word order untouched — so a cosmetic round trip through an editor never
registers as a change, but any real edit still does.

**Deviation from plan:** the round-trip tests (commit 3 of Prompt 6) use small hand-authored
inline fixtures per mutation rather than mutating `config/policy-master.md` directly. The
master's core sections are single unbroken paragraphs with no internal line breaks, so
mutations like "blank-line runs" or "line endings" had no internal structure to act on without
first synthesising one — at which point the fixture is hand-authored either way. Commits 1–2
of Prompt 6 do use real file fixtures (`tests/fixtures/policy_fixture_{a,b}.md`) parsed through
`sections.load_sections`, per the brief.

## Phase 2 — MCP client and the four calls (Session 3, Prompts 7–10)

Built `mcp_client.py` (connect + upload/chat/approve/export + `parse_proposed_changes`),
`ledger.py` (cost record, persistence, report, idempotency, `--limit`/ceiling), and
`scripts/smoke.py`, all driven against the **real** SuperDocs MCP server — not mocks.

### The four MCP tools — real signatures, verified live

Endpoint `https://api.superdocs.app/mcp/`, streamable HTTP, `Authorization: Bearer sk_...`.

| Tool | Required | Key optional |
|---|---|---|
| `upload_document_base64` | `filename` (≤512), `file_base64` (≤50M chars) | `session_id` (auto-gen if omitted), `return_html` |
| `chat` (sync) | `message` (≤100k), `session_id` (pattern `^[a-zA-Z0-9_\-\.]+$`) | `approval_mode` (`approve_all` default / `ask_every_time`), `response_mode` (`full`/`compact`) |
| `approve_change` | `session_id`, `job_id` | `change_id`, `approved`, `feedback`, `changes` (batch) |
| `export_document` | one of `session_id`/`html`/`upload_id` | `format` (docx default/pdf/html/markdown/txt), `options` |

### Raw proposed-change shape (see `tests/fixtures/proposed-change-raw.json` for the full
recording, and Prompt 10's live run for the sync-chat variant)

Two shapes carry the same data:
- **Already-an-object**: `metadata.pending_changes` (chat_async/get_job) or
  `document_changes.pending_changes` (sync chat) — a list of
  `{change_id, operation, chunk_id, document_id, old_html, new_html, ai_explanation}` dicts.
- **Double-encoded**: `metadata.intermediate_responses[]` entries of
  `type: "proposed_change_batch"` carry `content` as a **JSON-encoded string**
  (`{"type", "batch_id", "batch_total", "changes": [...]}`), only present on the
  chat_async/job path.

`parse_proposed_changes()` (Prompt 8) hides this distinction; both were proven against the
real recorded fixture.

### Observed latency

Exactly one precise timing was captured with real timestamps: the chat_async batch edit in
Prompt 8 went from job `created_at` to `awaiting_approval` in **~7.15s**
(`08:31:51.997` → `08:31:59.145`). The synchronous `chat`/`upload`/`export` calls made live in
Prompt 10 were exercised through this session's SuperDocs MCP tools directly (see below for
why), which don't expose call timing in their response bodies — so no comparable stopwatch
figure exists for those calls in this record. `smoke.py` itself instruments every call with
`time.monotonic()` and reports wall time per ledger row; running it end-to-end with a real
`SUPERDOCS_API_KEY` would produce that data directly. Qualitatively, every call observed so far
completed in single-digit seconds — nowhere near `mcp_client.py`'s 900s ceiling.

### Where the docs and the real API disagreed

1. **`approve_change` only works against a `chat_async` job — not a synchronous `chat`
   preview.** Calling `chat` with `approval_mode='ask_every_time'` returns
   `document_changes.pending_changes` with `requires_approval: true`, exactly as documented —
   but that response carries no `job_id`, and `approve_change` requires one. Calling it with the
   `session_id` in place of `job_id` returns `HTTP 404 Not Found — {'detail': 'Job not found'}`.
   The docs describe `approve_change` as the HITL partner for both `chat` and `chat_async`
   without flagging that only the async job path actually has something to approve against.
   `scripts/smoke.py` demonstrates this directly: it calls `approve()`, the call fails exactly
   as described, and the script falls back to a second `chat` call (default `approve_all`) to
   actually apply the edit.
2. **A preview-only chat call is free; only an applied edit is billed.** The `ask_every_time`
   preview response came back with `"usage": null`. The follow-up call that actually applied the
   change came back with `"usage": {"was_billable": true, "ops_charged": 1, ...}`. Nothing in the
   docs states that proposing a change costs nothing while applying it costs one operation —
   this matters for `ledger.py`, whose current model (Prompt 9) charges 1 operation per `chat`
   call unconditionally. `smoke.py` charges from the response's real `usage` field instead of
   assuming a constant; `ledger.py`'s charging model should eventually do the same, but that
   change is out of this prompt's scope.
3. **The installed `mcp` Python SDK (v2.0.0) doesn't match the API the docs' example patterns
   assume** (found in Prompt 7): the real function is `streamable_http_client`, not
   `streamablehttp_client`; auth is set by constructing an `httpx2.AsyncClient` and passing it as
   `http_client=`, not a `headers=` kwarg on the transport call; and the library is `httpx2`
   (a dependency of `mcp` itself), not `httpx`. `httpx2.AsyncClient` also defaults to a 5-second
   timeout, which had to be overridden explicitly to honor CLAUDE.md's "no aggressive timeout"
   rule.
4. **The sync-chat and chat_async proposed-change shapes aren't quite identical.** The sync
   `chat` preview's `pending_changes` entries have no `insert_after_chunk_id` field and no
   outer `batch_id`/`batch_total` wrapper; the chat_async/job path's double-encoded batch does.
   `parse_proposed_changes()` treats both as valid without requiring those fields, since they're
   documented nowhere as guaranteed.

### How Prompt 10 was actually run

`scripts/smoke.py` is correct, real production code, but this sandbox's Bash environment has no
`SUPERDOCS_API_KEY` or network path wired to it (only `mcp__superdocs__*` tool calls in this
session are authenticated, at the harness level). So the exact operation sequence `smoke.py`
performs — upload `policy-master.md`, preview a section-6-only edit, attempt approve (fails as
documented), fall back to an applying chat call, export markdown — was run for real via those
live tools first, and `smoke.py`'s internal logic (parsing, ledger charging, the approve-fallback
path, section extraction) was then verified offline by replaying those exact real captured
responses through `smoke.run()` with only the network boundary substituted. The real export
confirmed sections 1–5 and 7–9 were untouched; only section 6 changed, to:

> India Office: Internal contact is the Country Safeguarding Focal Point, Mumbai, reachable at
> safeguarding.in@meridian-relief.example or +91 22 0000 0000. External channels: Childline
> India (1098, toll-free 24-hour child helpline) and the Police Control Room (112).

### fix(ledger): charge chat calls from real usage, not a flat 1 per call

What was wrong: `ledger.py` (Prompt 9) charged every `chat` call 1 operation
unconditionally. Finding 2 above proved that's incorrect — a preview-only call is free.
Left as-is, `ledger.py` would overcount any future preview call, which breaks the ledger's
entire purpose: it is supposed to answer "what did this actually cost," not "how many calls
did we make." `smoke.py` already worked around this locally with its own `_ops_charged()`
helper, but the fix belongs in `ledger.py` itself, where every other caller can use it.

Fix: added `ops_from_response(response) -> int` to `ledger.py` — reads `usage.was_billable`
and `usage.ops_charged` from a real SuperDocs response instead of assuming a constant.
`smoke.py`'s local copy was removed in favour of importing this. Re-verified against the
same real captured payloads from the Prompt 10 run: ledger total is still correctly 1 op
(0 for the preview, 1 for the apply). Full test suite (10 tests) still passes.

Not yet done, flagged for whichever prompt next builds the pack-generation path
(`packs.py`, Phase 3+): that code should call `ledger.record(..., chat_calls=
ledger.ops_from_response(chat_response))` rather than a hardcoded `chat_calls=1`, even
though CLAUDE.md's stated economics ("1 op per pack") will still hold in practice — a
real pack-generation call always applies a change, so it will always be billed — the
point is not to bake the *assumption* back in a second time. (Done: `packs.py` does exactly
this now — see Phase 3 below.)

## Phase 3 — One country, end to end (Session 4, Prompts 11–12)

**Prompt 11** implemented `packs.py`: `generate_pack(country_code)` — upload, batched annex
edit, export to markdown and docx, idempotent per-`(country_code, core_version)` charging via
`ledger`. The instruction builder (`build_instruction`) names annex sections only;
`assert_no_core_sections_named` is a hard stop enforced before any call is sent, and
`corelock.verify` after export is the enforcement half of the same guarantee.

**Prompt 12** asked for the India round trip end to end, core hash verified against the lock.
Live testing surfaced a real, blocking bug in SuperDocs itself before verification was even
reached — the edit wasn't landing. Full detail, repro, and billing findings:
`evidence/superdocs-batch-limit-report.md`. Summary:

- A batched `chat` call replacing all 4 annex sections in one request **reports success and
  changes nothing**, reproduced with two structurally different instruction phrasings.
- Pinned precisely, live: 1, 2, and 3 sections in one call can all succeed; 4 fails
  consistently. But 2-section batches were *also* observed to silently drop one of the two
  targeted sections on other trials — so no batch size above 1 is safe to assume reliable,
  including sizes proven to work in an earlier trial.
- A session that has just experienced a partial/failed batch can misattribute a later,
  differently-scoped single-section retry to the wrong section entirely.
- Billing: a **novel** failing batch is billed once (`ops_charged: 1` for zero changes); an
  **identical retry** of that same failing instruction is not billed; a bare transient error
  (`"I encountered an issue. Please try again."`) is billed.

**The fix** (per-user direction — do not hardcode the boundary; add real detection and
recovery instead of a threshold):

- `config/manifest.yaml` gained a required `annex_batch_size` field (currently `2`) — a live,
  undocumented API characteristic belongs in config, adjustable as it's re-verified, never a
  Python constant.
- `packs.py`'s `generate_pack` now sends the annex edit in `annex_batch_size` batches via
  `_localise_annex` → `_apply_annex_batch`. After every batch, it re-exports and checks each
  targeted section's actual body against the master's original text (`_sections_landed`) —
  never trusting the response text. Any section that didn't land has its batch split
  (bisected) and retried, bounded by `_MAX_RETRY_DEPTH`. A section still unlanded after
  isolation to a batch of one falls through to `verify_pack`'s existing placeholder check,
  which quarantines the pack rather than shipping it silently incomplete.
- Removed the now-obsolete `ask_every_time` preview + `approve_change` fallback path and its
  regex-based partial-apply detection (`_PARTIAL_APPLY_RE`) — `approve_change` never worked
  against a synchronous `chat()` call regardless (Prompt 10 finding), and the regex matched a
  response shape ("Updated X of Y sections") different from every failure shape actually
  observed live.
- `tests/test_packs.py` rewritten around a fake client that tracks real document mutation
  (`_MutatingFakeClient`), including a test that reproduces the exact live bug (a batch that
  reports success and changes nothing) and proves detection + split-retry recovers from it.
- `CLAUDE.md`'s economics corrected: a pack costs **2 ops**, not 1. Full rollout **12** (2
  translations + 5 packs × 2); core amendment reaching all 5 stays **7** (2 re-translations +
  5 single-document notices — a notice isn't a batched multi-section call, so its cost is
  unaffected).

**The real India round trip, live** (session `pack-in-real`, after the fix): uploaded the real
`config/policy-master.md`, sent the batched annex edit as `annex_batch_size=2` batches (with
several of the partial-failure symptoms above occurring and being manually worked through
live, exactly as the automated retry path is designed to handle), exported markdown, ran the
real `corelock.lock()`/`packs.verify_pack()`:

```
locked core_hash: aa3a7460e6602b04e59acbe8ef73be464c3951624b50903a61b548ce64e186e8
passed: True
core passed: True
core_hash_matches: True
diverged_sections: []
unlocalised_annex_sections: []
```

India's pack — core sections 1–5 byte-identical to the lock, all four annex sections
genuinely localised (India-specific email/phone/helplines, POCSO/POSH/JJ Act citations,
Mumbai escalation tiers, NCPCR) — is saved at `out/IN/policy-pack.md` and `out/IN/policy-pack.docx`
(gitignored; not committed, per CLAUDE.md).

**Deviation from plan:** Prompt 12's checkpoint description assumed a single batched call
would work and only verification remained to prove. It didn't — the batching assumption
itself was wrong, discovered only by running it live rather than trusting the design. Fixed
forward per CLAUDE.md's own commit protocol, with a full bug report filed
(`evidence/superdocs-batch-limit-report.md`) rather than silently working around it.

## Phase 3 continued — service layer and CLI (Prompt 13)

`service.py` is now the single entry point both the CLI and any future FastAPI route call —
neither reimplements lock/generate/verify:

- `lock_core()` — locks `policy-master.md`'s core sections for one language. 0 ops.
- `generate(country_code, ...)` — thin wrapper over `packs.generate_pack`.
- `verify(country_code, ...)` — re-verifies an already-generated pack on disk against the lock,
  without regenerating it.
- `run(country_codes, *, limit=None, ...)` — loads the persisted ledger, locks the core, generates
  a pack per country (respecting `--limit`), saves the ledger. What the CLI's `run` command calls.

`python -m localizer run --countries IN [--limit N]` (`src/localizer/__main__.py`) is a thin
argparse wrapper over `service.run`; it prints per-country OK/SKIPPED and the ledger report.

**Run it clean, then run it again — real result**, real `out/` and `state/` cleared first
(including a leftover `out/_quarantine/IN/` from an earlier offline test that had wrongly
landed in the real project directory — removed):

First run (via live SuperDocs calls, since this sandbox has no `SUPERDOCS_API_KEY` wired to
its own process — see Prompt 10/12 for why; the CLI itself needs no such workaround with a
real key) reproduced the same partial-batch behaviour documented in
`evidence/superdocs-batch-limit-report.md`: the `[6, 7]` batch landed only section 7; a
`[6]`-alone retry failed once (free) then succeeded; the `[8, 9]` batch landed cleanly. Real
cost for this run: **3 ops**, not the idealised 2 — CLAUDE.md's "2 ops" is what a clean batch
run costs; a run that needs one retry costs more, and the ledger records that honestly rather
than reporting an assumed constant. `verify_pack` passed: core hash matched the lock exactly,
zero unlocalised annex sections (see note below on why section 9's retained placeholder
sentence didn't false-positive this check).

Second run, the actual command, no code path touching the network at all:
```
$ python -m localizer run --countries IN
[IN] SKIPPED

...
[pack]      IN                                           0 ops
[pack]      IN                                 SKIPPED (0 ops)
                                                       -------
total                                                    3 ops
```
Total stayed at 3 — the second run added exactly one new SKIPPED ledger line and zero
operations. Also confirmed `--countries IN,KE --limit 1` processes only `IN`; `KE` is never
attempted, not even skipped-and-logged — `apply_limit` slices the country list before any
country is touched.

**Observation, not a bug:** section 9's original body has its two sentences joined by a
single `\n` in `policy-master.md`, but SuperDocs' HTML→markdown export renders the `<br/>`
that single `\n` becomes on upload as a full paragraph break (`\n\n`) on export — even when
new content is appended after the original placeholder sentence rather than replacing it
(observed live), the exact placeholder substring no longer matches verbatim, so
`_sections_landed`/`verify_pack` correctly does not flag it as still-unlocalised. This is
fortunate rather than by design; a future SuperDocs export change that preserved single `\n`
literally could reintroduce a false "not landed" retry loop or, worse, a false-pass on a
section that only had content appended around an intact placeholder. Worth hardening later
(e.g. checking the placeholder no longer appears as the section's *entire* content, not just
checking it as a substring) — not done now, out of this prompt's scope.

## Phase 4 — Translation and multi-language (Session 5, Prompts 14–16)

**Prompt 14** implemented `translate.derive_core(language)`: derives, hashes, and locks a
language's translated core exactly once, cached by `(core_version, language)`. The
translation instruction is the one legitimate place in the codebase that names core
sections — structurally isolated by never importing `packs.py`, so `packs.assert_no_core_sections_named`
can never see it. The lock file gained a `sections` key holding the verbatim translated
text (heading + body per section), alongside the existing hashes, so a later pack can insert
the translated core without ever re-translating it.

**Prompt 15** extended `packs.py` so a non-English country's pack is assembled from that
language's locked core (verbatim, via `_assemble_upload_document`) plus its own annexes, with
`_assert_core_verbatim` proving the match locally before any SuperDocs call is made. FR and
SN — two French-speaking countries with entirely different annexes — were built and their
core hashes compared: identical, as required.

**Prompt 16** ran all five countries live (IN, KE, FR, SN, BR) to a genuinely clean, verified
state and produced `evidence/integrity-report.json`.

**What "clean" actually took.** The first pass through every non-trivial annex batch/fix-up
call surfaced defects beyond the partial-batch behaviour already documented in
`evidence/superdocs-batch-limit-report.md`:

- A batch reporting full success while leaving part of a multi-sentence placeholder attached
  before or after the new localised text (FR §6/§8/§9, SN §6/§7/§8, IN §6/§8/§9 all showed
  this — the master's placeholder sentence surviving verbatim alongside real content).
- A batch editing the wrong chunk entirely — writing new content into the `<h2>` **heading**
  chunk instead of the `<p>` **body** chunk, corrupting the heading while leaving the body's
  placeholder untouched (BR §6/§7, observed live).
- A "concurrent edit notice" (`concurrent_merges`) appearing on at least one retry, indicating
  cross-request interference on the same document; the affected edit (KE §7) still needed a
  second pass afterward because the merge silently reverted it despite the response reporting
  success.
- Natural-language `chat()` instructions repeatedly failing to touch a corrupted **heading**
  specifically (`"nothing actually changed"`, 0 ops charged, three separate attempts on BR),
  even when the exact chunk id was named. What reliably worked instead: fetching the current
  full document HTML and re-submitting it via `chat(document_html=...)` as a verbatim
  replacement (the tool's documented "load, don't retype" path) rather than asking the AI to
  edit in place — 0 ops charged each time, since it is a document load, not an AI edit.

All five packs were brought to a verified-clean state this way and re-exported. Locally
re-running `packs.verify_pack` against every exported markdown (not the chat response)
confirms:

```
IN en passed=True unlocalised=[] core_hash_match=True
KE en passed=True unlocalised=[] core_hash_match=True
FR fr passed=True unlocalised=[] core_hash_match=True
SN fr passed=True unlocalised=[] core_hash_match=True
BR pt passed=True unlocalised=[] core_hash_match=True
```

**The three real core hashes** (`evidence/integrity-report.json`, `core_identity`):

- en (IN, KE): `aa3a7460e6602b04e59acbe8ef73be464c3951624b50903a61b548ce64e186e8`
- fr (FR, SN): `a240052d992b3f53af2332edd0ffe62172b87e6a963c3c8dd4dfef4d47dafa58`
- pt (BR): `4d339a737d5ea69c3bfd38ee983f779243c219ba869e1e9df443bb98ef7cf9b8`

FR and SN's identical hash — two French-speaking countries, two entirely different annexes,
one identical locked core — is the demo's central proof, now verified from five real,
independently-generated exports, not asserted.

**Annex divergence**, counted (not claimed) across the same normalisation `corelock` uses:
`reporting`: 5 distinct, `legal`: 5 distinct, `escalation`: 5 distinct — every one of the five
countries' three non-acknowledgement annex slots is genuinely unique content.

**Translation quality vs. annex-editing completeness — kept separate, deliberately.** The
translated CORE text itself (fr and pt, from `translate.derive_core`) read as accurate,
idiomatic legal French and Portuguese on inspection — no quality concerns there. The defects
above were entirely in ANNEX EDITING completeness and precision (partial replacements,
wrong-chunk edits, a reverted concurrent merge), not in translation. KE (English throughout,
no translation involved at all) needed the same class of remediation as FR/SN/BR, which
confirms the defects are a `chat()`-edit reliability issue, not a translation-quality one.

**Operations.** Full itemisation and the honest total (well above both the user's stated
7-op expectation and CLAUDE.md's own idealised 12-op full-rollout figure — annotated with
why) is in `evidence/ledger-summary.md`, not duplicated here. In short: the idealised model
prices a pack at 2 ops (one per annex batch); the real run cost more per pack because
recovering from the defects above took extra `chat()` turns per affected country before
`verify_pack` could honestly report every section clean.

## Phase 5 — Acknowledgement forms (Session 6, Prompt 17)

Implemented `ack.py`: `render_form(country, manifest)` builds the acknowledgement
markdown deterministically — office name, country, pack version, the protected core hash
(read from the persisted `state/core-lock-v1-{lang}.json`, never recomputed), safeguarding
lead, and blank recipient/date/signature fields, with field labels and the confirmation
statement in the office's working language (en/fr/pt) from a small static dictionary.
`generate_acknowledgement(country_code)` uploads and exports it via SuperDocs.

**Decision: no chat call, ever, for this document.** Filling known fields from a known
country YAML into a known template has no ambiguity for a model to resolve — the fields
either exist in the YAML and the lock, or they don't. Spending an operation on it would be,
per CLAUDE.md, spending money to do arithmetic badly. SuperDocs is used only for the parts
it actually adds value on: upload (turns the markdown into a document SuperDocs can render)
and export (produces the styled `.docx` the office actually signs) — both free.

**Live proof, all five countries** (`evidence/ack-generation-report.md`): uploaded and
exported IN/KE/FR/SN/BR's forms via the real SuperDocs MCP tools. Every `upload`/`export`
response carried no `usage` field at all — the same "absent = free" signal
`ledger.ops_from_response` already treats as zero — so the ledger total across all ten
calls is **0 operations**. Each core hash embedded matches that country's language lock
exactly; Senegal's and France's forms carry the identical `fr` core hash, the same proof
the packs themselves carry.

**Return address, one deviation from the brief's field list.** No country YAML carries a
distinct postal address — `office` and `country` are all that exist. Rather than adding a
sixth field to five YAML files for a string that would just repeat those two values,
`return_address` is derived as `f"{office}, {country}"`. If a real postal address is ever
needed, it is a one-field addition to each country YAML, consistent with "adding a country
(or a field) is a data change."
