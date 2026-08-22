import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Requirement } from "../domain/requirements.js";

export const DEFAULT_REQUIREMENTS_SNAPSHOT_PATH = fileURLToPath(
  new URL("../../state/requirements-snapshot.json", import.meta.url),
);

/** Missing snapshot means no amendment has ever run — not an error. */
export async function loadRequirementsSnapshot(
  filePath: string = DEFAULT_REQUIREMENTS_SNAPSHOT_PATH,
): Promise<Requirement[] | null> {
  try {
    const text = await readFile(filePath, "utf8");
    return JSON.parse(text) as Requirement[];
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}

export async function saveRequirementsSnapshot(
  requirements: Requirement[],
  filePath: string = DEFAULT_REQUIREMENTS_SNAPSHOT_PATH,
): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(requirements, null, 2)}\n`, "utf8");
}

/** Hashes the substantive fields of a requirement — not its id, which is the lookup key. */
export function hashRequirementContent(r: Requirement): string {
  const material = JSON.stringify({
    citation: r.citation,
    title: r.title,
    obligation: r.obligation,
    evidence_expected: r.evidence_expected,
    frequency: r.frequency,
    applies_to: r.applies_to,
  });
  return createHash("sha256").update(material).digest("hex");
}

export type AmendmentKind = "new_requirement" | "changed_obligation";

export interface AmendmentEvent {
  requirement_id: string;
  kind: AmendmentKind;
  previous: Requirement | null;
  updated: Requirement;
}

/**
 * Compares the requirements register recorded in state against a candidate
 * updated register. Purely a content comparison — no model call, and
 * nothing here is a judgment: a requirement is either byte-for-byte the
 * same as what state last recorded, or it isn't.
 */
export function detectAmendments(baseline: Requirement[], updated: Requirement[]): AmendmentEvent[] {
  const baselineById = new Map(baseline.map((r) => [r.id, r]));
  const events: AmendmentEvent[] = [];

  for (const req of updated) {
    const prev = baselineById.get(req.id);
    if (!prev) {
      events.push({ requirement_id: req.id, kind: "new_requirement", previous: null, updated: req });
      continue;
    }
    if (hashRequirementContent(prev) !== hashRequirementContent(req)) {
      events.push({ requirement_id: req.id, kind: "changed_obligation", previous: prev, updated: req });
    }
  }

  return events;
}
