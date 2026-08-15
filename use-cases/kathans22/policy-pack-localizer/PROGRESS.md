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
