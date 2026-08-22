# Compliance console

A read-only console over the compliance CLI's own run artifacts — no second
pipeline, no recomputation. It shows what `compliance --coverage`,
`--generate`, `--matrix` and `--amend` already produced in `../state/`,
`../config/` and `../out/`.

## Usage

From the parent `NotesForge/` directory, run whichever compliance commands
you want reflected (at minimum `compliance --coverage` for the coverage
grid; `--generate`, `--matrix` and `--amend` for the other screens), then:

```bash
cd ui
npm install
npm run dev
```

`npm run dev` runs `npm run sync` first (see `predev` in package.json),
which copies `../state/*.json`, the client/requirement registers, the
amendment notices and the corpus notes into `public/data/` as static JSON.
Re-run `npm run sync` (or just restart `npm run dev`) after running the CLI
again to pick up new results — the browser only ever reads what's already
on disk.

## Screens

| Tab | Source artifacts |
|---|---|
| COVERAGE | `state/coverage.json` |
| CLIENTS | `config/clients.yaml`, `state/versions.json`, `state/consent-matrix.json` |
| PACKS | `state/packs.json`, `out/<client_id>/` |
| AMENDMENTS | `state/amendments/**/event.json` |
| RUN | `state/ledger.json` |

Every generated pack and amendment notice carries its own
"draft for professional review" banner — this console does not add or
imply a compliance determination beyond what the CLI already computed.
