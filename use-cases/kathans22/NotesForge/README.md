# NotesForge

A zero-dependency Node 20+/TypeScript CLI agent that turns a folder of rough notes into a finished, exported report using the [SuperDocs](https://docs.superdocs.app) REST API.

This build also carries a specialisation on top of the same engine — **[RIA Compliance Packs](#ria-compliance-packs)** — that turns SEBI compliance notes into per-client compliance packs with an honest, evidence-based coverage report. See that section for what it adds and the one rule it never breaks.

## Quickstart

```bash
npm install
npm run dev -- --notes ./sample-notes --title "Q3 Report" --out ./out
```

First run self-signs up for a free SuperDocs agent account (500 ops/month) and saves the key to `~/.superdocs/agent_credentials.json`. Every run after that reuses it.

## Flags

| Flag | Purpose |
|---|---|
| `--notes <dir>` | Notes folder to ingest (default `./sample-notes`) |
| `--title <string>` | Report title (default: chosen by the AI) |
| `--out <dir>` | Export output folder (default `./out`) |
| `--formats <csv>` | Export formats: `docx,pdf,html,markdown,txt` (default `docx,pdf`) |
| `--no-page-breaks` | Skip page breaks before each top-level section |
| `--plan-only` | Run ingestion + planning only, print the outline, spend nothing else |
| `--whoami` | Resolve credentials and print account slug/tier/ops remaining |
| `--budget` | Print the ops ledger report for this run |
| `--handoff <email>` | Email a one-time adoption link + print/save a takeover code |
| `--ops-cap <n>` | Override the hard per-run ops cap (default 25) |

## Operation economics

A full run — plan, generate, verify, finish, export — costs on the order of **2-4 ops** against the 500/month free tier, not the naive 10+ a per-section, per-format, per-check implementation would rack up. Four choices keep it there:

1. **Batched edits.** Every multi-part instruction (finishing touches, section repairs) goes in a single chat call. A four-part finishing pass is one operation, not four; the docs are explicit that a large multi-section edit still only bills once.
2. **Free structure reads.** Checking whether an edit landed uses `GET /v1/documents/{id}`'s `structure` block (headings, section/block counts) — derived on read, never billed. Verification never spends an export just to look.
3. **`response_mode: 'compact'`.** Document-scale generation and polling use compact mode, which returns per-section `chunk_diffs` instead of the full document HTML — thousands of tokens saved per turn on anything beyond a page or two, and it doesn't change what's billed.
4. **Pre-signed transfers.** Anything over 100KB moves through pre-signed upload/download URLs — bytes go straight between the note/export file and SuperDocs' storage, never through the agent's own context window.

## Design decisions

**Reuse-first signup.** `resolveCredentials()` checks `SUPERDOCS_API_KEY`, then `~/.superdocs/agent_credentials.json` (validated live via `whoami`), and only calls `POST /v1/agents/signup` if both come up empty or dead. Most agent integrations skip this and mint a new account every run; NotesForge treats a live account as something to preserve, not throw away.

**Async + polling over sync.** Document-scale generation goes through `POST /v1/chat/async` and polls `GET /v1/jobs/{job_id}`, because synchronous `/v1/chat` hits a ~300s gateway timeout on long turns. Polling also surfaces two distinct pause types: a `continue_prompt` pause (a large edit asking for a fresh budget — resumed automatically) versus a genuine human-in-the-loop approval pause (surfaced, not resolved silently).

**Named error taxonomy.** `SuperDocsClient` never throws a bare `Error` for a known failure mode — `AuthError` (401), `DocumentInUseError`/`TurnRevertedError` (409, distinguished by the response's `code`), `QuotaError` (429, no blind auto-retry), `ServerError` (5xx, retried twice with backoff), `NetworkError`. Each name is a different thing to do about it, not just a status code to log.

## RIA Compliance Packs

An extension of the same engine, specialised for a narrower and higher-stakes job: turning a folder of SEBI Registered Investment Adviser compliance notes into per-client compliance packs, traceable to the specific regulatory requirement each section evidences.

> **This produces drafts for a compliance professional to review. It does not produce compliance, does not certify anything, and does not imply it does.**

Every generated pack opens with, verbatim:

> DRAFT FOR PROFESSIONAL REVIEW — this document is generated from source notes and does not constitute compliance advice or certification.

**Everything invented, one thing real.** The firm (Meridian Advisory Services), its people, clients and figures are all fictional — see [`corpus/MANIFEST.md`](corpus/MANIFEST.md). The seven requirements in [`config/requirements.yaml`](config/requirements.yaml) are real SEBI (Investment Advisers) Regulations, 2013 obligations, citation-checked against actual regulation numbers (including the 2024 amendment inserting Regulation 15(14)/18(9) for AI-tool usage) rather than invented — fabricating the regulation would make the exercise meaningless. Nothing here is legal advice, and no certification is claimed anywhere in the tool or this document.

### Quickstart

```bash
npm run dev -- compliance --list-requirements   # the SEBI requirements register, with citations
npm run dev -- compliance --list-clients        # the invented advisory client roster
npm run dev -- compliance --coverage            # EVIDENCED / STALE / MISSING / INCONSISTENT per requirement
npm run dev -- compliance --generate --clients CL-04   # plan, draft and verify one client's pack
```

### Flags

| Flag | Purpose |
|---|---|
| `compliance --list-requirements` | Print the requirements register (id, frequency, scope, citation) |
| `compliance --list-clients` | Print the client roster (AI-assisted flag, agreement version, last risk review) |
| `compliance --coverage` | Run the coverage engine and print a status line per (requirement, client) |
| `compliance --generate` | Plan outlines, assess coverage, draft and verify one pack per client |
| `--notes <dir>` | Notes folder for compliance mode (default `./corpus/ria-compliance`) |
| `--clients <csv>` | Restrict `--generate` to specific client ids, e.g. `CL-01,CL-04` (default: every client) |
| `--today <YYYY-MM-DD>` | Override "today" for staleness arithmetic — useful for reproducible runs (default: now) |
| `--ops-cap <n>` | Same hard per-run cap as the base pipeline (default 25) |

### The requirements and client registers are config, not code

[`config/requirements.yaml`](config/requirements.yaml) and [`config/clients.yaml`](config/clients.yaml) are plain YAML — adding a requirement or a client is a config edit, not a code change. Since NotesForge is zero-dependency by design, [`src/domain/yaml.ts`](src/domain/yaml.ts) is a small hand-rolled parser for exactly the one shape these files use (a top-level list of flat records), not a general YAML engine — anything outside that shape is a parse error naming the file, record id and line, not a silent guess. [`src/domain/requirements.ts`](src/domain/requirements.ts) and [`src/domain/clients.ts`](src/domain/clients.ts) reject unknown fields and missing fields the same way: a typo in a config file is an error, never a silent omission.

### The corpus

[`corpus/ria-compliance/`](corpus/ria-compliance/) is nine files of invented but realistically messy compliance notes for Meridian Advisory Services — abbreviations, half-sentences, someone's shorthand — with five behaviours planted deliberately and documented file-by-file in [`corpus/MANIFEST.md`](corpus/MANIFEST.md): a firm-level requirement with no evidence anywhere, a client whose risk review is years stale, a client marked AI-assisted with no entry in the AI usage register, a fee figure that disagrees between two documents, and one client with clean, complete evidence across every applicable requirement.

### Coverage engine — deterministic first, one narrow escalation

[`src/compliance/coverage.ts`](src/compliance/coverage.ts) is the authority on `EVIDENCED | STALE | MISSING | INCONSISTENT`, and it resolves almost everything without a model call:

- **Firm-level requirements** (net worth, records) — keyword presence or absence across the whole corpus. Zero hits is zero hits; no model is needed to notice nothing is there.
- **Risk profiling staleness** — `client.risk_profile_reviewed_on` is structured config, not free text, so freshness is a date subtraction, not a judgment call.
- **Fee consistency** — the figure in the client's onboarding notes and the figure in the fee-change notes are both regex-extracted percentages; disagreement is a numeric comparison, not an opinion.
- **Agreement and AI-disclosure evidence** — presence or absence of that client's block in the relevant file.

Exactly one case escalates to the model, and only when it actually arises: a suitability note that itself says the underlying risk profile is stale or overdue. Whether that still counts as a clean pass is a genuine judgment call, so the code declines to hard-code an opinion — every such case (there are at most a handful) is batched into a single chat call, because judging three clients costs the same one operation as judging one. **A requirement with no supporting evidence is MISSING. It is never inferred, never softened, and never filled in** — this is true throughout, model call or not.

### Generation and verification

[`src/compliance/generate.ts`](src/compliance/generate.ts) turns each coverage finding into the literal section heading the model is instructed to reproduce — `{requirement title} — {Status} (source-file.md)`, with no parenthetical at all when there's no evidence, so a MISSING section can never carry a citation it didn't earn. All of a client's sections are batched into one `chat/async` request — one pack, one operation, the same batching discipline as the base pipeline's finishing pass. [`src/compliance/verify.ts`](src/compliance/verify.ts) then reuses the same free, unbilled structure read as the base pipeline to confirm every planned section landed *and* that every EVIDENCED/STALE/INCONSISTENT section still carries its citation — a live test run caught a real case of this: a heading got silently truncated past a platform length limit and lost its citation mid-generation, and verification correctly failed it. The fix was citing one representative source file instead of joining several into one long parenthetical, not loosening the check.

### Verified against the corpus

Run for real against `corpus/ria-compliance/`: `RIA-REC-01` reports MISSING firm-wide (no matching text anywhere in the corpus); the designated stale client reports STALE with the exact date (`last reviewed 2022-04-01, 1604 days ago`); the designated clean client reports EVIDENCED across all five of its applicable requirements. Three full pack generations (clean, stale, and a client with STALE/INCONSISTENT/MISSING/EVIDENCED all in one pack) drafted and verified live end to end. Total spend across all of that testing: 5 ops, against a 25-op per-run cap and a 500/month quota.

## MCP alternative

Everything above is a hand-rolled REST client, but SuperDocs also runs an MCP server at the same base URL — an agent (Claude Code, or any MCP-capable client) can skip this codebase entirely and talk to SuperDocs directly as tools:

```bash
claude mcp add -s user --transport http superdocs https://api.superdocs.app/mcp/ \
  --header "Authorization: Bearer sk_<your key>"
```

That exposes the same ~50 REST endpoints as MCP tools (chat, documents, sessions, jobs, uploads/downloads) with no client code to maintain — an agent could plan, draft, verify, and export a report purely through tool calls in a single conversation. The tradeoff is control: this repo's value is the *specific* choices above (batching, compact mode, the ops ledger, the error taxonomy) enforced in code, not left to whatever a given turn's tool-calling happens to do. For a one-off or exploratory task, MCP is less code; for a repeatable, budget-bounded pipeline, the REST client in this repo is the more predictable path.

## Architecture

```
src/
├── index.ts        CLI entry, arg parsing, run orchestration
├── compliance.ts    compliance CLI: --list-requirements / --list-clients / --coverage / --generate
├── config.ts         endpoints, limits, tunables
├── types.ts            API response/request shapes
├── logger.ts             structured run log (console + run-log.json)
├── credentials.ts          reuse-first signup
├── client.ts                 SuperDocsClient — fetch wrapper, auth, error taxonomy
├── budget.ts                   OpsLedger — tracks ops_charged, enforces a hard cap
├── notes.ts                      read + normalise the notes folder
├── pipeline.ts                     plan → create → finish (base report pipeline)
├── verify.ts                        free structure-based verification (base pipeline)
├── export.ts                          request_download_url → docx/pdf/html/md/txt
├── handoff.ts                           agent handoff + takeover code
├── domain/
│   ├── yaml.ts                            hand-rolled parser for the one YAML shape config/ uses
│   ├── requirements.ts                     load + validate config/requirements.yaml
│   └── clients.ts                            load + validate config/clients.yaml
└── compliance/
    ├── plan.ts                                 draft per-client pack outline (1 chat call)
    ├── coverage.ts                               EVIDENCED/STALE/MISSING/INCONSISTENT engine
    ├── generate.ts                                 batched per-client pack drafting + polling
    └── verify.ts                                     free structure + citation check

config/
├── requirements.yaml   SEBI (Investment Advisers) Regulations, 2013 obligations — real regulation
└── clients.yaml          invented advisory client roster

corpus/
├── MANIFEST.md         documents all five deliberately planted coverage gaps
└── ria-compliance/       Meridian Advisory Services' fictional compliance notes
```
