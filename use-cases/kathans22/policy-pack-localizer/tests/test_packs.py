"""Proves pack generation batches the annex edit into one call and costs one operation."""

from __future__ import annotations

import asyncio

from localizer import config as config_module
from localizer import packs
from localizer.ledger import Ledger
from localizer.mcp_client import SuperDocsClientError


def _manifest_and_country():
    manifest = config_module.load_manifest()
    country = config_module.load_country(config_module.COUNTRIES_DIR / "IN.yaml")
    return manifest, country


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
    """Records every call made against it; mimics the documented API quirk

    that approve_change fails against a synchronous chat() preview.
    """

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

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
        return {"usage": {"was_billable": True, "ops_charged": 1}}

    async def approve(self, **kwargs):
        self.calls.append(("approve", kwargs))
        raise SuperDocsClientError("Job not found (documented fallback path)")

    async def export(self, **kwargs):
        self.calls.append(("export", kwargs))
        if kwargs.get("format") == "docx":
            return {"download_url": "https://downloads.example/policy-pack.docx"}
        return {"text": "exported markdown"}


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


def test_generate_pack_never_sends_a_core_section_number_to_the_client(tmp_path):
    manifest, country = _manifest_and_country()
    ledger = Ledger()
    fake_client = _FakeSuperDocsClient()

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


def test_generate_pack_sends_one_batched_chat_instruction_and_charges_one_operation(tmp_path):
    manifest, country = _manifest_and_country()
    ledger = Ledger()
    fake_client = _FakeSuperDocsClient()

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


def test_generate_pack_exports_markdown_and_docx_to_disk(tmp_path):
    manifest, country = _manifest_and_country()
    ledger = Ledger()
    fake_client = _FakeSuperDocsClient()

    async def fake_downloader(url: str) -> bytes:
        assert url == "https://downloads.example/policy-pack.docx"
        return await _fake_downloader(url)

    result = asyncio.run(
        packs.generate_pack(
            "IN",
            ledger=ledger,
            manifest=manifest,
            country=country,
            out_dir=tmp_path,
            client_factory=lambda: fake_client,
            downloader=fake_downloader,
        )
    )

    md_path = result["exports"]["markdown"]
    docx_path = result["exports"]["docx"]
    assert md_path == tmp_path / "IN" / "policy-pack.md"
    assert md_path.read_text(encoding="utf-8") == "exported markdown"
    assert docx_path == tmp_path / "IN" / "policy-pack.docx"
    assert docx_path.read_bytes() == b"fake docx bytes"
