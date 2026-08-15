"""Proves pack generation batches the annex edit into one call and costs one operation."""

from __future__ import annotations

import asyncio

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


def test_build_instruction_batches_every_annex_section_into_one_message():
    manifest, country = _manifest_and_country()

    instruction = packs.build_instruction(manifest, country)

    for number in (6, 7, 8, 9):
        assert f"Section {number} " in instruction
    assert "safeguarding.in@meridian-relief.example" in instruction
    assert "POCSO" in instruction
    assert "Regional Director, South Asia" in instruction
    assert country["office"] in instruction


class _FakeSuperDocsClient:
    """Records every call made against it; mimics the documented API quirks:

    approve_change fails against a synchronous chat() preview, and — when
    constructed with `apply_responses` — a batch apply can come back partial
    ("Updated N of M sections") before a retry completes it, exactly as
    observed live.
    """

    def __init__(self, markdown_text: str = "exported markdown", apply_responses: list[dict] | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.markdown_text = markdown_text
        self._apply_responses = list(apply_responses) if apply_responses is not None else None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return None

    async def upload(self, **kwargs):
        self.calls.append(("upload", kwargs))
        return {"session_id": kwargs.get("session_id")}

    async def chat(self, **kwargs):
        self.calls.append(("chat", kwargs))
        if kwargs.get("approval_mode") == "ask_every_time":
            return {
                "usage": None,
                "metadata": {
                    "pending_changes": [
                        {
                            "change_id": "c1",
                            "operation": "edit",
                            "chunk_id": "chunk-1",
                            "old_html": "<p>old</p>",
                            "new_html": "<p>new</p>",
                        }
                    ]
                },
            }
        if self._apply_responses:
            return self._apply_responses.pop(0)
        return {"usage": {"was_billable": True, "ops_charged": 1}, "response": "Updated 4 of 4 sections."}

    async def approve(self, **kwargs):
        self.calls.append(("approve", kwargs))
        raise SuperDocsClientError("Job not found (documented fallback path)")

    async def export(self, **kwargs):
        self.calls.append(("export", kwargs))
        if kwargs.get("format") == "docx":
            return {"download_url": "https://downloads.example/policy-pack.docx"}
        return {"text": self.markdown_text}


async def _fake_downloader(url: str) -> bytes:
    return b"fake docx bytes"


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
    fake_client = _FakeSuperDocsClient(markdown_text=_valid_pack_markdown(manifest, country))

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


def test_generate_pack_sends_one_batched_chat_instruction_and_charges_one_operation(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    fake_client = _FakeSuperDocsClient(markdown_text=_valid_pack_markdown(manifest, country))

    result = asyncio.run(
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

    chat_calls = [kwargs for name, kwargs in fake_client.calls if name == "chat"]
    assert len(chat_calls) == 2  # free preview, then the billed fallback apply
    assert chat_calls[0]["message"] == chat_calls[1]["message"] == result["instruction"]
    assert ledger.total_operations == 1


def test_generate_pack_exports_markdown_and_docx_to_disk(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    valid_markdown = _valid_pack_markdown(manifest, country)
    fake_client = _FakeSuperDocsClient(markdown_text=valid_markdown)

    async def fake_downloader(url: str) -> bytes:
        assert url == "https://downloads.example/policy-pack.docx"
        return await _fake_downloader(url)

    result = asyncio.run(
        packs.generate_pack(
            "IN",
            ledger=ledger,
            manifest=manifest,
            country=country,
            out_dir=tmp_path / "out",
            client_factory=lambda: fake_client,
            downloader=fake_downloader,
        )
    )

    md_path = result["exports"]["markdown"]
    docx_path = result["exports"]["docx"]
    assert md_path == tmp_path / "out" / "IN" / "policy-pack.md"
    assert md_path.read_text(encoding="utf-8") == valid_markdown
    assert docx_path == tmp_path / "out" / "IN" / "policy-pack.docx"
    assert docx_path.read_bytes() == b"fake docx bytes"


def test_generate_pack_is_idempotent_for_the_same_country_and_core_version(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    fake_client = _FakeSuperDocsClient(markdown_text=_valid_pack_markdown(manifest, country))
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
    fake_client = _FakeSuperDocsClient(markdown_text=_valid_pack_markdown(manifest, country))

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
    markdown = markdown.replace("## 1 Purpose and Commitment", "## 1 Purpose and Commitment", 1)
    markdown = markdown.replace(
        "Meridian Relief Trust (MRT) exists",
        "Meridian Relief Trust (MRT) no longer exists",
        1,
    )

    result = packs.verify_pack(markdown, manifest, country["language"])

    assert result["passed"] is False
    assert result["core"]["passed"] is False
    assert 1 in result["core"]["diverged_sections"]


def test_generate_pack_retries_once_on_a_partial_apply_response(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    valid_markdown = _valid_pack_markdown(manifest, country)
    partial_then_complete = [
        {
            "usage": {"was_billable": True, "ops_charged": 1},
            "response": "Updated 3 of 4 sections. (1 section(s) couldn't be updated: retry them.)",
        },
        {
            "usage": {"was_billable": True, "ops_charged": 1},
            "response": "Updated 4 of 4 sections.",
        },
    ]
    fake_client = _FakeSuperDocsClient(markdown_text=valid_markdown, apply_responses=partial_then_complete)

    asyncio.run(
        packs.generate_pack(
            "IN", ledger=ledger, manifest=manifest, country=country, out_dir=tmp_path / "out",
            client_factory=lambda: fake_client, downloader=_fake_downloader,
        )
    )

    chat_calls = [kwargs for name, kwargs in fake_client.calls if name == "chat"]
    assert len(chat_calls) == 3  # preview, partial apply, retry
    assert ledger.total_operations == 2  # both apply attempts were billable


def test_generate_pack_quarantines_a_corrupted_pack_and_does_not_export(tmp_path, monkeypatch):
    manifest, country = _manifest_and_country()
    _lock_real_core(monkeypatch, tmp_path / "state", manifest)
    ledger = Ledger()
    # A markdown export with no numbered headings at all — the annex never
    # landed and every localisation is missing, the sharpest case of the bug
    # the live run surfaced.
    fake_client = _FakeSuperDocsClient(markdown_text="Not a policy document.")
    out_dir = tmp_path / "out"

    raised = False
    try:
        asyncio.run(
            packs.generate_pack(
                "IN", ledger=ledger, manifest=manifest, country=country, out_dir=out_dir,
                client_factory=lambda: fake_client, downloader=_fake_downloader,
            )
        )
    except (packs.PackIntegrityError, ValueError):
        raised = True

    assert raised
    assert not (out_dir / "IN" / "policy-pack.md").exists()
    assert not (out_dir / "IN" / "policy-pack.docx").exists()
    content_key = packs._content_key("IN", manifest["core_version"])
    assert not ledger.already_charged(content_key)  # never marked as a successfully bought pack
