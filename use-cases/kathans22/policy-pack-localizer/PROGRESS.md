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
point is not to bake the *assumption* back in a second time.
