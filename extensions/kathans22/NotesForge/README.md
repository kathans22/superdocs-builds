# NotesForge

A zero-dependency Node 20+/TypeScript CLI agent that turns a folder of rough-notes into a finished, exported report using the [SuperDocs](https://docs.superdocs.app) REST API.

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
├── config.ts        endpoints, limits, tunables
├── types.ts          API response/request shapes
├── logger.ts          structured run log (console + run-log.json)
├── credentials.ts      reuse-first signup
├── client.ts             SuperDocsClient — fetch wrapper, auth, error taxonomy
├── budget.ts               OpsLedger — tracks ops_charged, enforces a hard cap
├── notes.ts                 read + normalise the notes folder
├── pipeline.ts                plan → create → finish
├── verify.ts                   free structure-based verification
├── export.ts                    request_download_url → docx/pdf/html/md/txt
└── handoff.ts                    agent handoff + takeover code
```

## Video Link
Visit [NotesForge Demo](https://youtu.be/cYoo76M_Y7Q)

