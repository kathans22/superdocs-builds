"""Proves pack generation batches the annex edit per config, verifies each
batch actually landed rather than trusting the response, and quarantines
anything that still fails verification."""

from __future__ import annotations

import asyncio
import math

from localizer import config as config_module
from localizer import corelock
from localizer import packs
from localizer import sections as sections_module
from localizer.ledger import Ledger
from localizer.mcp_client import SuperDocsClientError


def _manifest_and_country():
    manifest = config_module.load_manifest()
    country = config_module.load_country(config_module.COUNTRIES_DIR / "IN.yaml")
    return manifest, country


def _valid_pack_markdown(manifest: dict, country: dict) -> str:
    """A correctly localised pack: real core sections, real rendered annex content."""
    master_sections = sections_module.parse_sections(packs.POLICY_MASTER_PATH.read_text(encoding="utf-8"))
    body_by_number = {s["number"]: s["body"] for s in master_sections}
    lines = []
    for section in manifest["sections"]:
        lines.append(f"## {section['number']} {section['heading']}")
        lines.append("")
        if section["role"] == "core":
            lines.append(body_by_number[section["number"]])
        else:
            lines.append(packs._SLOT_RENDERERS[section["slot"]](country))
        lines.append("")
    return "\n".join(lines)


def _lock_real_core(monkeypatch, tmp_path, manifest, language="en"):
    """Point corelock's state dir at a fresh tmp dir and lock the real core there."""
    monkeypatch.setattr(corelock, "STATE_DIR", tmp_path)
    master_sections = sections_module.parse_sections(packs.POLICY_MASTER_PATH.read_text(encoding="utf-8"))
    core_numbers = {s["number"] for s in manifest["sections"] if s["role"] == "core"}
    core_sections = [s for s in master_sections if s["number"] in core_numbers]
    lock_data = corelock.lock(core_sections, manifest["core_version"], language)
    corelock.save_lock(lock_data)
    return lock_data


class _MutatingFakeClient:
    """A fake SuperDocs client that tracks real document state, so a chat call
    either actually mutates the targeted sections or it doesn't — independent
    of what the response text claims.

    `lands_at_size` reproduces the live-observed boundary: a batch whose
    section count is <= lands_at_size mutates the document and reports
    success; a larger batch reports success text but changes nothing,
    exactly as SuperDocs did with a real 4-section batch.
    """

    def __init__(self, manifest: dict, country: dict, lands_at_size: int,
                 docx_url: str = "https://downloads.example/policy-pack.docx"):
        self.manifest = manifest
        self.country = country
        self.lands_at_size = lands_at_size
        self.docx_url = docx_url
        self.calls: list[tuple[str, dict]] = []
        master_sections = sections_module.parse_sections(packs.POLICY_MASTER_PATH.read_text(encoding="utf-8"))
        self.body_by_number = {s["number"]: s["body"] for s in master_sections}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return None

    async def upload(self, **kwargs):
        self.calls.append(("upload", kwargs))
        return {"session_id": kwargs.get("session_id")}

    async def chat(self, **kwargs):
        self.calls.append(("chat", kwargs))
        numbers = sorted({int(m) for m in packs._SECTION_MENTION_RE.findall(kwargs["message"])})
        if 0 < len(numbers) <= self.lands_at_size:
            for number in numbers:
                slot = next(s["slot"] for s in self.manifest["sections"] if s["number"] == number)
                self.body_by_number[number] = packs._SLOT_RENDERERS[slot](self.country)
            return {
                "response": f"Successfully updated all {len(numbers)} sections.",
                "usage": {"was_billable": True, "ops_charged": 1},
            }
        return {
            "response": f"I went through {len(numbers)} section(s) but nothing actually changed.",
            "usage": {"was_billable": True, "ops_charged": 1},
        }

    async def approve(self, **kwargs):
        self.calls.append(("approve", kwargs))
        raise SuperDocsClientError("approve_change is not exercised by the current batching design")

    def _current_markdown(self) -> str:
        lines = []
        for section in self.manifest["sections"]:
            lines.append(f"## {section['number']} {section['heading']}")
            lines.append("")
            lines.append(self.body_by_number[section["number"]])
            lines.append("")
        return "\n".join(lines)

    async def export(self, **kwargs):
        self.calls.append(("export", kwargs))
        if kwargs.get("format") == "docx":
            return {"download_url": self.docx_url}
        return {"text": self._current_markdown()}


async def _fake_downloader(url: str) -> bytes:
    return b"fake docx bytes"


def test_build_instruction_batches_every_annex_section_into_one_message():
    manifest, country = _manifest_and_country()

    instruction = packs.build_instruction(manifest, country)

    for number in (6, 7, 8, 9):
        assert f"Section {number} " in instruction
    assert "safeguarding.in@meridian-relief.example" in instruction
    assert "POCSO" in instruction
    assert "Regional Director, South Asia" in instruction
    assert country["office"] in instruction


def test_build_instruction_accepts_an_explicit_section_subset():
    manifest, country = _manifest_and_country()
    annex_by_number = {s["number"]: s for s in manifest["sections"] if s["role"] == "annex"}

    instruction = packs.build_instruction(manifest, country, sections=[annex_by_number[6]])

    assert "Section 6 " in instruction
    for number in (7, 8, 9):
        assert f"Section {number} " not in instruction


def test_assert_no_core_sections_named_passes_a_real_annex_instruction():
    manifest, country = _manifest_and_country()
    instruction = packs.build_instruction(manifest, country)

    packs.assert_no_core_sections_named(instruction, manifest)  # must not raise


def test_assert_no_core_sections_named_raises_when_a_core_section_is_named():
    manifest, _ = _manifest_and_country()
    violating_instruction = 'Also rewrite Section 4 "Prohibited Conduct" while you are at it.'

    try:
        packs.assert_no_core_sections_named(violating_instruction, manifest)
        raised = False
    except ValueError as exc:
        raised = True
        assert "4" in str(exc)
    assert raised


def test_generate_pack_never_sends_a_core_section_number_to_the_client(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    fake_client = _MutatingFakeClient(manifest, country, lands_at_size=manifest["annex_batch_size"])

    asyncio.run(
        packs.generate_pack(
            "IN",
            ledger=ledger,
            manifest=manifest,
            country=country,
            out_dir=tmp_path,
            client_factory=lambda: fake_client,
            downloader=_fake_downloader,
        )
    )

    core_numbers = {s["number"] for s in manifest["sections"] if s["role"] == "core"}
    for name, kwargs in fake_client.calls:
        if name != "chat":
            continue
        named = {int(m) for m in packs._SECTION_MENTION_RE.findall(kwargs["message"])}
        assert not (named & core_numbers)


def test_generate_pack_batches_the_annex_edit_per_manifest_batch_size(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    fake_client = _MutatingFakeClient(manifest, country, lands_at_size=manifest["annex_batch_size"])

    result = asyncio.run(
        packs.generate_pack(
            "IN", ledger=ledger, manifest=manifest, country=country, out_dir=tmp_path,
            client_factory=lambda: fake_client, downloader=_fake_downloader,
        )
    )

    annex_numbers = [s["number"] for s in manifest["sections"] if s["role"] == "annex"]
    expected_batches = math.ceil(len(annex_numbers) / manifest["annex_batch_size"])
    chat_calls = [kwargs for name, kwargs in fake_client.calls if name == "chat"]

    assert len(chat_calls) == expected_batches
    assert ledger.total_operations == expected_batches
    assert result["skipped"] is False


def test_generate_pack_detects_a_success_shaped_response_that_changed_nothing_and_retries(tmp_path, monkeypatch):
    """Reproduces the exact live bug: a batch chat call reports success and
    changes zero sections. generate_pack must not trust the response text —
    it detects this from the document itself, splits the failed batch, and
    retries at a smaller size until every section lands.
    """
    manifest, country = _manifest_and_country()
    manifest = dict(manifest, annex_batch_size=4)  # provoke the exact live failure mode
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    fake_client = _MutatingFakeClient(manifest, country, lands_at_size=2)  # 4 fails; <=2 lands

    result = asyncio.run(
        packs.generate_pack(
            "IN", ledger=ledger, manifest=manifest, country=country, out_dir=tmp_path,
            client_factory=lambda: fake_client, downloader=_fake_downloader,
        )
    )

    chat_batches = [
        sorted({int(m) for m in packs._SECTION_MENTION_RE.findall(kwargs["message"])})
        for name, kwargs in fake_client.calls if name == "chat"
    ]
    assert chat_batches[0] == [6, 7, 8, 9]  # the doomed first attempt, as batch_size=4 dictates
    assert len(chat_batches) > 1  # detection triggered a retry rather than stopping here
    assert result["skipped"] is False

    markdown = (tmp_path / "IN" / "policy-pack.md").read_text(encoding="utf-8")
    verification = packs.verify_pack(markdown, manifest, country["language"])
    assert verification["passed"] is True  # the pack that shipped is fully localised


def test_generate_pack_exports_markdown_and_docx_to_disk(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    fake_client = _MutatingFakeClient(manifest, country, lands_at_size=manifest["annex_batch_size"])

    async def fake_downloader(url: str) -> bytes:
        assert url == fake_client.docx_url
        return await _fake_downloader(url)

    result = asyncio.run(
        packs.generate_pack(
            "IN", ledger=ledger, manifest=manifest, country=country, out_dir=tmp_path / "out",
            client_factory=lambda: fake_client, downloader=fake_downloader,
        )
    )

    md_path = result["exports"]["markdown"]
    docx_path = result["exports"]["docx"]
    assert md_path == tmp_path / "out" / "IN" / "policy-pack.md"
    assert docx_path == tmp_path / "out" / "IN" / "policy-pack.docx"
    assert docx_path.read_bytes() == b"fake docx bytes"

    verification = packs.verify_pack(md_path.read_text(encoding="utf-8"), manifest, country["language"])
    assert verification["passed"] is True


def test_generate_pack_is_idempotent_for_the_same_country_and_core_version(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    fake_client = _MutatingFakeClient(manifest, country, lands_at_size=manifest["annex_batch_size"])
    kwargs = dict(
        ledger=ledger, manifest=manifest, country=country, out_dir=tmp_path,
        client_factory=lambda: fake_client, downloader=_fake_downloader,
    )

    first = asyncio.run(packs.generate_pack("IN", **kwargs))
    assert first["skipped"] is False
    calls_after_first_run = len(fake_client.calls)
    ops_after_first_run = ledger.total_operations

    second = asyncio.run(packs.generate_pack("IN", **kwargs))

    assert second["skipped"] is True
    assert len(fake_client.calls) == calls_after_first_run  # no new SuperDocs calls at all
    assert ledger.total_operations == ops_after_first_run  # nothing re-bought
    assert second["exports"]["markdown"] == first["exports"]["markdown"]


def test_generate_pack_re_runs_when_the_output_files_are_missing(tmp_path, monkeypatch):
    # Idempotency is keyed on the ledger entry AND the files still being on
    # disk; a stale ledger with no output present must not skip real work.
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    content_key = packs._content_key("IN", manifest["core_version"])
    ledger.record("pack", "IN", chat_calls=0, wall_time=0.0, content_key=content_key)
    fake_client = _MutatingFakeClient(manifest, country, lands_at_size=manifest["annex_batch_size"])

    result = asyncio.run(
        packs.generate_pack(
            "IN", ledger=ledger, manifest=manifest, country=country, out_dir=tmp_path,
            client_factory=lambda: fake_client, downloader=_fake_downloader,
        )
    )

    assert result["skipped"] is False
    assert len(fake_client.calls) > 0


def test_verify_pack_passes_for_a_correctly_localised_export(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path, manifest)
    markdown = _valid_pack_markdown(manifest, country)

    result = packs.verify_pack(markdown, manifest, country["language"])

    assert result["passed"] is True
    assert result["core"]["passed"] is True
    assert result["unlocalised_annex_sections"] == []


def test_verify_pack_fails_when_an_annex_section_still_has_placeholder_text(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path, manifest)
    master_sections = sections_module.parse_sections(packs.POLICY_MASTER_PATH.read_text(encoding="utf-8"))
    original_section_8_body = next(s["body"] for s in master_sections if s["number"] == 8)

    lines = []
    for section in manifest["sections"]:
        lines.append(f"## {section['number']} {section['heading']}")
        lines.append("")
        if section["role"] == "core":
            lines.append(next(s["body"] for s in master_sections if s["number"] == section["number"]))
        elif section["number"] == 8:
            # Simulates the live corruption: new content spliced next to the
            # unedited placeholder, rather than replacing it.
            lines.append(packs._SLOT_RENDERERS["escalation"](country) + "\n\n" + original_section_8_body)
        else:
            lines.append(packs._SLOT_RENDERERS[section["slot"]](country))
        lines.append("")
    corrupted_markdown = "\n".join(lines)

    result = packs.verify_pack(corrupted_markdown, manifest, country["language"])

    assert result["passed"] is False
    assert result["core"]["passed"] is True  # the corruption is annex-only
    assert result["unlocalised_annex_sections"] == [8]


def test_verify_pack_fails_when_a_core_section_diverges(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path, manifest)
    markdown = _valid_pack_markdown(manifest, country)
    markdown = markdown.replace(
        "Meridian Relief Trust (MRT) exists",
        "Meridian Relief Trust (MRT) no longer exists",
        1,
    )

    result = packs.verify_pack(markdown, manifest, country["language"])

    assert result["passed"] is False
    assert result["core"]["passed"] is False
    assert 1 in result["core"]["diverged_sections"]


def test_generate_pack_quarantines_a_pack_whose_annex_never_lands(tmp_path, monkeypatch):
    # lands_at_size=0: no batch, however small, ever actually mutates the
    # document — reproducing a total, unrecovered failure of the live bug,
    # where retries are exhausted and the annex is still all placeholder.
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    fake_client = _MutatingFakeClient(manifest, country, lands_at_size=0)
    out_dir = tmp_path / "out"

    raised = False
    try:
        asyncio.run(
            packs.generate_pack(
                "IN", ledger=ledger, manifest=manifest, country=country, out_dir=out_dir,
                client_factory=lambda: fake_client, downloader=_fake_downloader,
            )
        )
    except packs.PackIntegrityError as exc:
        raised = True
        assert "6" in str(exc) or "unlocalised" in str(exc).lower()

    assert raised
    assert not (out_dir / "IN" / "policy-pack.md").exists()
    assert not (out_dir / "IN" / "policy-pack.docx").exists()
    content_key = packs._content_key("IN", manifest["core_version"])
    assert not ledger.already_charged(content_key)  # never marked as a successfully bought pack
    assert (out_dir / "_quarantine" / "IN" / "policy-pack.md").exists()
