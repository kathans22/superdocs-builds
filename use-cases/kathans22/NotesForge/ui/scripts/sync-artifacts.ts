/**
 * Copies the CLI's own read artifacts into ui/public/data/ as static JSON.
 * This is NOT a second pipeline: every file here is either read verbatim
 * from state/ (already written by `compliance --coverage/--generate/--amend`)
 * or loaded via the same config/ loaders (loadClients, loadRequirements)
 * the CLI itself uses — nothing is recomputed. Run after a CLI command, then
 * `npm run dev` in ui/ to view the result.
 */
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadClients } from "../../src/domain/clients.js";
import { loadRequirements } from "../../src/domain/requirements.js";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const OUT_DIR = fileURLToPath(new URL("../public/data", import.meta.url));

async function writeJson(name: string, data: unknown): Promise<void> {
  await writeFile(path.join(OUT_DIR, name), `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function isEnoent(err: unknown): boolean {
  return (err as NodeJS.ErrnoException).code === "ENOENT";
}

/** Copies a state/ JSON file verbatim if it exists; otherwise writes the fallback. */
async function copyStateFile(relPath: string, destName: string, fallback: unknown): Promise<unknown> {
  try {
    const text = await readFile(path.join(ROOT, relPath), "utf8");
    await writeFile(path.join(OUT_DIR, destName), text, "utf8");
    return JSON.parse(text);
  } catch (err) {
    if (isEnoent(err)) {
      await writeJson(destName, fallback);
      return fallback;
    }
    throw err;
  }
}

/** Walks state/amendments/<REQ-ID>-<date>/event.json — the structured sibling of each notice batch. */
async function collectAmendmentEvents(): Promise<unknown[]> {
  const amendmentsDir = path.join(ROOT, "state", "amendments");
  let entries: import("node:fs").Dirent[];
  try {
    entries = await readdir(amendmentsDir, { withFileTypes: true });
  } catch (err) {
    if (isEnoent(err)) return [];
    throw err;
  }

  const events: unknown[] = [];
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    if (!entry.isDirectory()) continue;
    try {
      const text = await readFile(path.join(amendmentsDir, entry.name, "event.json"), "utf8");
      events.push(JSON.parse(text));
    } catch (err) {
      if (!isEnoent(err)) throw err;
    }
  }
  return events;
}

/** Every note file in the compliance corpus, verbatim — coverage entries cite file:line into these. */
async function collectCorpusNotes(): Promise<Record<string, string>> {
  const corpusDir = path.join(ROOT, "corpus", "ria-compliance");
  let files: string[];
  try {
    files = (await readdir(corpusDir)).filter((f) => f.endsWith(".md"));
  } catch (err) {
    if (isEnoent(err)) return {};
    throw err;
  }
  const notes: Record<string, string> = {};
  for (const file of files) {
    notes[file] = await readFile(path.join(corpusDir, file), "utf8");
  }
  return notes;
}

async function main(): Promise<void> {
  await mkdir(OUT_DIR, { recursive: true });

  const clients = await loadClients();
  await writeJson("clients.json", clients);

  const requirements = await loadRequirements();
  await writeJson("requirements.json", requirements);

  await copyStateFile("state/coverage.json", "coverage.json", {
    generated_at: null,
    notes_dir: null,
    summary: {},
    entries: [],
  });
  const packs = (await copyStateFile("state/packs.json", "packs.json", { generated_at: null, packs: [] })) as {
    packs: unknown[];
  };
  await copyStateFile("state/versions.json", "versions.json", { template_versions: [], client_versions: [] });
  await copyStateFile("state/consent-matrix.json", "consent-matrix.json", {
    generated_at: null,
    templates: [],
    rows: [],
  });
  await copyStateFile("state/requirements-snapshot.json", "requirements-snapshot.json", null);
  await copyStateFile("state/ledger.json", "ledger.json", null);

  const amendments = await collectAmendmentEvents();
  await writeJson("amendments.json", amendments);

  const corpusNotes = await collectCorpusNotes();
  await writeJson("corpus-notes.json", corpusNotes);

  console.log(
    `[OK] synced ${clients.length} client(s), ${requirements.length} requirement(s), ${packs.packs.length} pack(s), ${amendments.length} amendment event(s), ${Object.keys(corpusNotes).length} corpus note(s) into ui/public/data/`,
  );
}

main().catch((err: unknown) => {
  console.error(err);
  process.exitCode = 1;
});
