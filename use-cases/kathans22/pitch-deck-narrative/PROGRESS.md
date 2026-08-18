# Progress

## Session 1 — Phase 0 / Prompt 1 (Scaffold)

- Branch `kathans22/pitch-deck-narrative` cut from `main`.
- Commits pushed:
  1. `549ce17` chore: add gitignore and env example with placeholder key
  2. `0787cb3` chore: scaffold src/generator package modules
  3. `a1a3275` chore: add config, output and evidence directory structure
  4. `01926e4` chore: add pyproject with dependencies and python 3.12 target
- Check: `python -c "import generator"` → **PASS** (editable install).
- Note: `.gitignore` adjusted so `out/.gitkeep` and `state/.gitkeep` are trackable while generated contents stay ignored.

## Session 1 continued — Phase 1 / Prompt 2 (Manifest + product)

- `fb23868` feat(config): declare the nine-section deck manifest with weight and image tags
- `69c4ae4` feat(config): define the ClarityDocs product being pitched
- Manifest: 9 sections; shared = 1,4,9; vertical = 2,3,5,6,7,8; image_eligible = 6,8.
- `product.yaml` frozen after this prompt (ClarityDocs constant across verticals).

## Session 1 continued — Phase 1 / Prompt 3 (Vertical knowledge)

- `1e8fe81` feat(config): add legal vertical knowledge
- `3d00cd1` feat(config): add fintech vertical knowledge
- `c389166` feat(config): add healthcare vertical knowledge
- `4b5a695` feat(config): add edtech vertical knowledge
- Four packs present; typical_objection strings distinct (find-and-replace bar).
- Regulatory refs framed as orientation, not certification claims.

## Session 1 continued — Phase 1 / Prompt 4 (Manifest load + validate)

- `fb3f79f` feat(manifest): load deck manifest, product and vertical files
- `aa36297` feat(manifest): validate required fields and fail with the specific gap
- `load_validated()` PASS on real config; missing-field errors name the gap.
- Fifth vertical = new YAML only (glob `*.yaml`).

## Session 1 continued — Phase 1 / Prompt 5 (Divergence scorer)

- `7a46a9e` feat(divergence): add pairwise lexical-overlap scoring for two texts
- `aaf4c03` feat(divergence): score all vertical pairs per section and aggregate by weight
- `6bae9c4` docs(divergence): define and justify the divergence threshold
- Metric: word Jaccard. Thresholds: vertical mean < 0.40; any vertical section < 0.55.
- Shared sections reported, not gated. Noun-swap fixtures fail; substance pairs pass.

## Session 1 continued — Phase 1 / Prompt 6 (Phase 1 proof)

- `d4aafed` test(divergence): identical text scores maximum overlap
- `09ffebf` test(divergence): template-and-swap fixture scores high and is caught
- `b1f15a8` test(divergence): genuinely distinct text scores low (+ weight aggregation assertions)
- `tests/test_divergence.py`: 4 passed, no SuperDocs, no network.

---

## Phase 1 — DONE

**What Phase 1 proved (before any SuperDocs call):**

1. Config spine exists: 9-section manifest with `shared`/`vertical` + `image_eligible`, frozen ClarityDocs product, four vertical knowledge packs that are not noun-swaps.
2. Loader/validator fails loudly naming the specific missing field; adding a vertical is data-only.
3. Divergence is **measured**, not claimed — Build 2’s counterpart to Build 1’s core-hash.

**Threshold chosen and why:**

| Gate | Value | Why |
|---|---|---|
| `VERTICAL_MEAN_MAX` | **0.40** | Between genuine substance (~0.03–0.25 with shared product words) and template-and-swap (~0.70+). Mean vertical overlap must stay **below** 0.40. |
| `VERTICAL_SECTION_MAX` | **0.55** | One hot section (often Objection/Proof) fails the run even if other sections dilute the mean. |
| Shared sections | **not gated** | Product is held constant; high Opening/Overview overlap is expected and reported only. |

Do **not** loosen thresholds to pass weak packs — fix YAML / narratives instead.

**Proven by hand-made fixtures:**

- Identical texts → Jaccard **1.0**
- `"legal team"` vs `"compliance team"` otherwise identical → high overlap (**≥0.7**) and `evaluate_divergence` **fails** (caught)
- Distinct pain points → low overlap (**&lt;0.25**) and evaluation **passes**
- Three-vertical synthetic set → shared mean **1.0**, vertical mean below threshold, cell counts 3 shared / 6 vertical

**Next:** Phase 2 — MCP client (2-section batch + landed-check ported from Build 1), still respecting CLAUDE.md.
