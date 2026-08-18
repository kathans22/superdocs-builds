"""Decide (then later generate) supporting images for image_eligible sections.

The card requires the system to decide from actual section content — never force
an image onto every eligible section, and never skip every section by policy.
Decisions are written to the narrative's sidecar metadata before any generation.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import load_deck_manifest, project_root
from .narrative import parse_script_sections

# Generic / unfilled bodies are not visualizable — do not invent a figure for them.
_PLACEHOLDER_RE = re.compile(
    r"PLACEHOLDER_|\[Insert speaker script here\]|Insert speaker script",
    re.IGNORECASE,
)
_FILLER_PHRASES = (
    "operational excellence",
    "strategic roadmap for the upcoming quarter",
    "strategic focus for the upcoming quarter",
    "aligned on the project timeline",
    "high-impact growth initiatives",
    "scaling our core service offerings",
)

_DIGIT_RE = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")
_SPELLED_COUNTS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
}
_SPELLED_RE = re.compile(
    r"\b(" + "|".join(sorted(_SPELLED_COUNTS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_TIME_UNIT_RE = re.compile(
    r"\b(hours?|weeks?|months?|days?|minutes?)\b",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*%|\bpercent(?:age)?\b", re.IGNORECASE)
_MONEY_RE = re.compile(r"\$\s*\d|\b(?:usd|dollars?)\b", re.IGNORECASE)
_COMPARE_RE = re.compile(
    r"\b(?:vs\.?|versus|compared with|compared to|before|after|"
    r"not weeks|not months|rather than|instead of|down from|up from)\b",
    re.IGNORECASE,
)
_PROCESS_RE = re.compile(
    r"\b(?:findings?|rejected|committed|reconcile[ds]?|staged|pilot|"
    r"campuses|sites|locations|control matrix)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ImageDecision:
    """Per-section eligibility decision recorded before any image is generated."""

    section_number: int
    title: str
    image_eligible: bool
    warranted: bool
    reason: str


@dataclass
class NarrativeImagePlan:
    """Decisions for one vertical's eligible sections, persisted as narrative metadata."""

    vertical: str
    source_path: str
    manifest_version: int
    decided_at: str
    sections: list[ImageDecision]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "vertical": self.vertical,
            "source_path": self.source_path,
            "manifest_version": self.manifest_version,
            "decided_at": self.decided_at,
            "note": (
                "Decisions recorded before image generation. "
                "warranted=false means no image will be requested."
            ),
            "sections": [asdict(s) for s in self.sections],
        }


def metadata_path_for(markdown_path: Path) -> Path:
    """pitch-script-legal-claritydocs.md → pitch-script-legal-claritydocs.meta.json"""
    path = Path(markdown_path)
    return path.with_name(path.stem + ".meta.json")


def image_eligible_sections(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return manifest sections tagged image_eligible (Proof/Case Study, ROI/Business Case)."""
    data = manifest if manifest is not None else load_deck_manifest()
    return [
        section
        for section in (data.get("sections") or [])
        if bool(section.get("image_eligible"))
    ]


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _is_unfilled(body: str) -> bool:
    text = _norm(body)
    if _PLACEHOLDER_RE.search(text):
        return True
    if len(text) < 40:
        return True
    lowered = text.lower()
    filler_hits = sum(1 for phrase in _FILLER_PHRASES if phrase in lowered)
    # Generic corporate filler with no vertical substance.
    if filler_hits >= 1 and not _DIGIT_RE.search(text) and not _PROCESS_RE.search(text):
        return True
    return False


def _quantities(body: str) -> list[str]:
    digits = _DIGIT_RE.findall(body or "")
    spelled = [m.group(0).lower() for m in _SPELLED_RE.finditer(body or "")]
    return digits + spelled


def decide_image_for_section(
    section: dict[str, Any],
    body: str,
) -> ImageDecision:
    """Decide from this section's actual content whether a supporting image is warranted.

    Examples the card cares about:
    - ROI that names numbers a chart would clarify → yes
    - Proof that names a single reference story with no comparative figures → no
    """
    number = int(section["number"])
    title = str(section.get("title") or "")
    eligible = bool(section.get("image_eligible"))
    if not eligible:
        return ImageDecision(
            section_number=number,
            title=title,
            image_eligible=False,
            warranted=False,
            reason="section is not image_eligible in the deck manifest",
        )

    text = body or ""
    title_l = title.lower()
    is_roi = "roi" in title_l or "business case" in title_l
    is_proof = "proof" in title_l or "case study" in title_l

    if _is_unfilled(text):
        return ImageDecision(
            section_number=number,
            title=title,
            image_eligible=True,
            warranted=False,
            reason="section body is placeholder or generic filler, not visualizable substance",
        )

    quantities = _quantities(text)
    has_compare = bool(_COMPARE_RE.search(text))
    has_time = bool(_TIME_UNIT_RE.search(text))
    has_percent = bool(_PERCENT_RE.search(text))
    has_money = bool(_MONEY_RE.search(text))
    has_process = bool(_PROCESS_RE.search(text))
    distinct_qty = {q.lower() if isinstance(q, str) else q for q in quantities}

    if is_roi:
        chartable = (
            (len(distinct_qty) >= 1 and (has_compare or has_time or has_percent or has_money))
            or (has_percent or has_money)
            or (len(distinct_qty) >= 2 and has_process)
        )
        if chartable:
            return ImageDecision(
                section_number=number,
                title=title,
                image_eligible=True,
                warranted=True,
                reason="ROI names quantities or time/cost comparisons a chart would clarify",
            )
        return ImageDecision(
            section_number=number,
            title=title,
            image_eligible=True,
            warranted=False,
            reason="ROI is qualitative; no figures a chart would clarify",
        )

    if is_proof:
        # A staged case with multiple counts (e.g. 12 findings / 4 rejected / 8 committed)
        # or a before/after with numbers is worth a figure. A single named story is not.
        multi_count = len(distinct_qty) >= 3 and has_process
        before_after = has_compare and len(distinct_qty) >= 1
        if multi_count or before_after:
            return ImageDecision(
                section_number=number,
                title=title,
                image_eligible=True,
                warranted=True,
                reason="proof names comparative counts a figure would make scanable",
            )
        return ImageDecision(
            section_number=number,
            title=title,
            image_eligible=True,
            warranted=False,
            reason="single reference story without comparative figures; a visual would not add",
        )

    # Other eligible titles (none today): require chartable quantities.
    if len(distinct_qty) >= 2 and (has_compare or has_time):
        return ImageDecision(
            section_number=number,
            title=title,
            image_eligible=True,
            warranted=True,
            reason="section names comparative quantities a supporting visual would clarify",
        )
    return ImageDecision(
        section_number=number,
        title=title,
        image_eligible=True,
        warranted=False,
        reason="eligible but content does not call for a supporting image",
    )


def decide_images_for_narrative(
    markdown: str,
    *,
    vertical: str,
    source_path: str | Path = "",
    manifest: dict[str, Any] | None = None,
) -> NarrativeImagePlan:
    """Decide for every image_eligible section in one exported speaking script."""
    data = manifest if manifest is not None else load_deck_manifest()
    bodies = parse_script_sections(markdown)
    decided_at = datetime.now(timezone.utc).isoformat()
    sections = [
        decide_image_for_section(section, bodies.get(int(section["number"]), ""))
        for section in image_eligible_sections(data)
    ]
    return NarrativeImagePlan(
        vertical=vertical,
        source_path=str(source_path),
        manifest_version=int(data.get("manifest_version") or 1),
        decided_at=decided_at,
        sections=sections,
    )


def write_narrative_metadata(markdown_path: Path, plan: NarrativeImagePlan) -> Path:
    """Persist decisions next to the narrative *before* any image is generated."""
    dest = metadata_path_for(Path(markdown_path))
    dest.write_text(json.dumps(plan.to_json_dict(), indent=2) + "\n", encoding="utf-8")
    return dest


def load_narrative_metadata(markdown_path: Path) -> dict[str, Any]:
    dest = metadata_path_for(Path(markdown_path))
    return json.loads(dest.read_text(encoding="utf-8"))


def decide_and_record(
    markdown_path: Path,
    *,
    vertical: str | None = None,
    manifest: dict[str, Any] | None = None,
) -> tuple[NarrativeImagePlan, Path]:
    """Load a script, decide, write sidecar metadata. Does not generate images."""
    path = Path(markdown_path)
    text = path.read_text(encoding="utf-8")
    code = vertical
    if code is None:
        parts = path.stem.split("-")
        # pitch-script-<vertical>-<product>
        code = parts[2] if len(parts) >= 4 else path.stem
    plan = decide_images_for_narrative(
        text,
        vertical=code,
        source_path=path,
        manifest=manifest,
    )
    meta_path = write_narrative_metadata(path, plan)
    return plan, meta_path


def default_narratives_dir() -> Path:
    evidence = project_root() / "evidence" / "narratives"
    if evidence.is_dir() and any(evidence.glob("pitch-script-*-*.md")):
        return evidence
    return project_root() / "out"


def decide_all_verticals(
    narratives_dir: Path | None = None,
    *,
    manifest: dict[str, Any] | None = None,
) -> list[tuple[NarrativeImagePlan, Path]]:
    """Run the decision pass on every pitch-script-*.md found (typically four verticals)."""
    dest = Path(narratives_dir) if narratives_dir is not None else default_narratives_dir()
    results: list[tuple[NarrativeImagePlan, Path]] = []
    for path in sorted(dest.glob("pitch-script-*-*.md")):
        parts = path.stem.split("-")
        if len(parts) < 4 or parts[0] != "pitch" or parts[1] != "script":
            continue
        results.append(decide_and_record(path, vertical=parts[2], manifest=manifest))
    return results
