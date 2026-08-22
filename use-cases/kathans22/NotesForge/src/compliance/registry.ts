import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

export interface TemplateVersion {
  template_id: string;
  version: string;
  effective_from: string;
  requirement_ids: string[];
  content_hash: string;
  superseded_by: string | null;
}

export interface ClientVersionRecord {
  client_id: string;
  template_id: string;
  version: string;
  issued_on: string;
  consented_on: string | null;
  consent_evidence: string | null;
}

export interface VersionStore {
  template_versions: TemplateVersion[];
  client_versions: ClientVersionRecord[];
}

export const DEFAULT_VERSION_STORE_PATH = fileURLToPath(new URL("../../state/versions.json", import.meta.url));

export class RegistryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RegistryError";
  }
}

function emptyStore(): VersionStore {
  return { template_versions: [], client_versions: [] };
}

/** Missing store file is a fresh register, not an error — this is the first run. */
export async function loadVersionStore(filePath: string = DEFAULT_VERSION_STORE_PATH): Promise<VersionStore> {
  try {
    const text = await readFile(filePath, "utf8");
    return JSON.parse(text) as VersionStore;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return emptyStore();
    }
    throw err;
  }
}

export async function saveVersionStore(
  store: VersionStore,
  filePath: string = DEFAULT_VERSION_STORE_PATH,
): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(store, null, 2)}\n`, "utf8");
}

export function hashTemplateContent(content: string): string {
  return createHash("sha256").update(content.trim()).digest("hex");
}

/**
 * Registers a template version. This increment always appends a new entry —
 * identifying two versions with the same content as one and the same is the
 * next increment's job.
 */
export function registerTemplateVersion(
  store: VersionStore,
  templateId: string,
  version: string,
  effectiveFrom: string,
  requirementIds: string[],
  content: string,
): TemplateVersion {
  const entry: TemplateVersion = {
    template_id: templateId,
    version,
    effective_from: effectiveFrom,
    requirement_ids: requirementIds,
    content_hash: hashTemplateContent(content),
    superseded_by: null,
  };
  store.template_versions.push(entry);
  return entry;
}

/** The template_versions entry for this template with nothing superseding it. */
export function currentVersion(store: VersionStore, templateId: string): TemplateVersion | null {
  return store.template_versions.find((t) => t.template_id === templateId && t.superseded_by === null) ?? null;
}

/**
 * Issues a template version to a client. Fails loudly if that template
 * version was never registered — a typo'd version is an error, not a
 * silent no-op. Re-issuing (e.g. a client moved from v1 to v2) is a new
 * row, not an edit — the client's issuance history stays intact.
 */
export function recordIssue(
  store: VersionStore,
  clientId: string,
  templateId: string,
  version: string,
  issuedOn: string,
): ClientVersionRecord {
  const templateExists = store.template_versions.some(
    (t) => t.template_id === templateId && t.version === version,
  );
  if (!templateExists) {
    throw new RegistryError(
      `recordIssue: no such template version "${templateId}@${version}" — register it with registerTemplateVersion first`,
    );
  }

  const entry: ClientVersionRecord = {
    client_id: clientId,
    template_id: templateId,
    version,
    issued_on: issuedOn,
    consented_on: null,
    consent_evidence: null,
  };
  store.client_versions.push(entry);
  return entry;
}

/** A client's most recent issuance of a given template, by issued_on. */
function latestRecordFor(
  store: VersionStore,
  clientId: string,
  templateId: string,
): ClientVersionRecord | null {
  const records = store.client_versions
    .filter((r) => r.client_id === clientId && r.template_id === templateId)
    .sort((a, b) => a.issued_on.localeCompare(b.issued_on));
  return records.length > 0 ? records[records.length - 1]! : null;
}

/** Every client whose most recent issuance of this template is exactly this version. */
export function clientsOnVersion(store: VersionStore, templateId: string, version: string): string[] {
  const clientIds = new Set(
    store.client_versions.filter((r) => r.template_id === templateId).map((r) => r.client_id),
  );
  const onVersion: string[] = [];
  for (const clientId of clientIds) {
    if (latestRecordFor(store, clientId, templateId)?.version === version) onVersion.push(clientId);
  }
  return onVersion.sort();
}

export type BehindReason = "outdated_version" | "not_consented" | "outdated_version_and_not_consented";

export interface BehindEntry {
  client_id: string;
  version: string;
  current_version: string;
  reason: BehindReason;
}

/**
 * A client is behind if their most recent issuance isn't the current
 * version, or if it is but they never consented to it — either way, it's
 * something a compliance officer needs to chase, not a passive fact.
 */
export function clientsBehind(store: VersionStore, templateId: string): BehindEntry[] {
  const current = currentVersion(store, templateId);
  if (!current) return [];

  const clientIds = new Set(
    store.client_versions.filter((r) => r.template_id === templateId).map((r) => r.client_id),
  );
  const behind: BehindEntry[] = [];

  for (const clientId of clientIds) {
    const latest = latestRecordFor(store, clientId, templateId);
    if (!latest) continue;

    const outdated = latest.version !== current.version;
    const notConsented = latest.consented_on === null;
    if (!outdated && !notConsented) continue;

    behind.push({
      client_id: clientId,
      version: latest.version,
      current_version: current.version,
      reason:
        outdated && notConsented
          ? "outdated_version_and_not_consented"
          : outdated
            ? "outdated_version"
            : "not_consented",
    });
  }

  return behind.sort((a, b) => a.client_id.localeCompare(b.client_id));
}
