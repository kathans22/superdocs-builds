# Image eligibility decisions — four verticals

**Date:** 18 August 2026  
**Pass:** Prompt 16 (decide from content, record metadata, generate only where yes)  
**Eligible sections (manifest):** 6 Proof / Case Study, 8 ROI / Business Case. All other sections are ineligible and were not considered.

Decisions are written to each narrative’s sidecar (`pitch-script-<vertical>-claritydocs.meta.json`) **before** any SuperDocs image chat. The system decides from the exported section body — it does not force an image onto every eligible section, and it does not skip every section by policy.

Machine-readable copy: `evidence/image-eligibility.json`.

## Eligibility table

| Vertical | §6 Proof / Case Study | Reason | §8 ROI / Business Case | Reason |
|---|---|---|---|---|
| legal | **no** | placeholder / generic filler, not visualizable substance | **no** | qualitative; no figures a chart would clarify |
| fintech | **yes** | comparative counts a figure would make scanable (HarborPay: hours vs weeks; 12 / 4 / 8 findings) | **yes** | time/cost language a chart would clarify (days digging vs hours; two-fold labour/risk) |
| healthcare | **no** | placeholder / generic filler, not visualizable substance | **yes** | quantities / time comparisons (weeks, months, Cedar Ward, two rejected claims) |
| edtech | **no** | placeholder / generic filler (`[Insert speaker script here]`) | **yes** | quantities a chart would clarify (four campuses; time-to-audit vs manual reconcile) |

**Warranted images this pass:** 4 of 8 eligible cells (fintech §6, fintech §8, healthcare §8, edtech §8).  
**Skipped (honest no):** legal §6, legal §8, healthcare §6, edtech §6.

That split is the point of the card: Proof that is a single unfilled or generic block does not get a figure; ROI that names time or counts does.

## Billing (not guessed)

Confirmed in Phase 2 against live SuperDocs docs (`docs/image-generation-billing.md`):

- Image generation is **not** a separate SKU.
- It rides a normal document-edit **`chat` operation** (typically **1 op** per generate/insert).
- Skipped (unwarranted) sections: **0 ops**.
- Export / download: **0 ops**.

`IMAGE_GENERATION_BILLING_CERTAIN = True` in `src/generator/imagegen.py`. Ledger step `image` uses `ops_from_response` when `usage` is present; if compact chat omits `usage`, it falls back to 1 chat op (same as narrative fill) and records `ops_source=chat_op_fallback_usage_omitted`.

## Live generation this session

**Not executed here.** This environment had no `SUPERDOCS_API_KEY` / local `.env`. Decisions and sidecar metadata were still recorded first, as required.

To generate only the yes cells (expected **~4 chat ops**, idempotent per `image:<vertical>:section:<n>:v1`):

```text
# set SUPERDOCS_API_KEY, then for each vertical whose metadata has warranted=true:
python -c "import asyncio; from pathlib import Path; from generator.imagegen import generate_images_for_markdown; from generator.ledger import Ledger; asyncio.run(generate_images_for_markdown(Path('evidence/narratives/pitch-script-fintech-claritydocs.md'), ledger=Ledger.load()))"
```

Prefer copying scripts to `out/` first so committed evidence markdown is not overwritten until the insert lands and format_guard still passes.

## Demo constraint vs honest skip

CLAUDE.md wants **≥1 image per vertical in the demo**. Legal currently warrants **zero** images because §6 is filler (BUG-001 class) and §8 has no chartable figures. That is recorded, not patched by forcing a picture onto empty proof. Rework legal Proof/ROI substance (same class as placeholder leftovers), then re-run `decide_and_record` — do not special-case legal to `yes`.
