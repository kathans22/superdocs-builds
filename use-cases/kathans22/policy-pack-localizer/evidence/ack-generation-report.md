# Acknowledgement form generation — zero-operation proof

Ran `ack.render_form` + a live upload/export round trip for all five countries
(IN, KE, FR, SN, BR), via the real SuperDocs MCP tools (`upload_document_base64`,
`export_document`), on 2026-08-15.

## What each form carries

Office name, country, pack version (`core_version`), the **protected core
hash** for that country's language (read from the persisted lock —
`state/core-lock-v1-{lang}.json` — never recomputed here), safeguarding lead,
and blank fields for recipient name, role, date, and signature. Labels and
the confirmation statement are in the office's working language (en/fr/pt),
selected from a small static dictionary — not a translation call.

## Why zero operations

- `render_form` is pure Python: string formatting over `country` (that
  country's YAML), `manifest` (`core_version`), and the already-locked core
  hash. No `chat` call is made — there is nothing for a model to decide.
- `upload_document_base64` and `export_document` never carry a `usage` field
  in their response (confirmed on all ten calls below), unlike a `chat` call
  that applies a change, which always returns `usage.was_billable: true` and
  a real `ops_charged` (see `ledger.ops_from_response`, `PROGRESS.md` Phase 2
  finding 2). Absence of `usage` is the same signal `ops_from_response`
  already treats as free.

## The live run

| Country | Upload | Export (docx) | docx size |
|---|---|---|---|
| IN | `session_id=ack-in`, 4 chunks | `usage`: absent | 37,054 bytes |
| KE | `session_id=ack-ke`, 4 chunks | `usage`: absent | 37,059 bytes |
| FR | `session_id=ack-fr`, 4 chunks | `usage`: absent | 37,104 bytes |
| SN | `session_id=ack-sn`, 4 chunks | `usage`: absent | 37,099 bytes |
| BR | `session_id=ack-br`, 4 chunks | `usage`: absent | 37,118 bytes |

Ledger total across all ten calls (5 uploads + 5 exports) plus the five `ack`
content-key entries: **0 operations.**

Every exported `.docx`/`.md` pair is saved at `out/{code}/acknowledgement.{md,docx}`
(gitignored, per CLAUDE.md — `out/` is never committed).

## Senegal's form (French), for reference

```
## 1 Accusé de réception

Je confirme avoir reçu et lu le dossier de la politique de protection Meridian
Relief Trust pour ce bureau, y compris ses annexes propres au pays, et que
l'empreinte du socle protégé ci-dessus correspond à la version publiée.

- **Bureau:** Bureau de Dakar
- **Pays:** Senegal
- **Version du dossier de politique:** v1
- **Empreinte du socle protégé:** `a240052d992b3f53af2332edd0ffe62172b87e6a963c3c8dd4dfef4d47dafa58`
- **Référent protection:** Awa Diallo
- **Nom du destinataire:** ________________________
- **Fonction du destinataire:** ________________________
- **Date:** ________________________
- **Signature:** ________________________

Retourner ce formulaire à: Bureau de Dakar, Senegal
```

The core hash matches the locked `fr` core (`state/core-lock-v1-fr.json`) —
the same hash France's pack carries, since the two share one translated core.
