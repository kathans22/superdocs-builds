import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { OpsLedger } from "./budget.js";
import { SuperDocsClient } from "./client.js";
import { CONFIG } from "./config.js";
import { assessCoverage, blockForClient, findInBlock, formatCoverageReport } from "./compliance/coverage.js";
import { buildPlannedSections, generateCompliancePack } from "./compliance/generate.js";
import { planCompliancePacks } from "./compliance/plan.js";
import {
  clientsBehind,
  DEFAULT_VERSION_STORE_PATH,
  loadVersionStore,
  recordConsent,
  recordIssue,
  registerTemplateVersion,
  saveVersionStore,
} from "./compliance/registry.js";
import { buildConsentMatrix, formatConsentMatrixTable } from "./compliance/report.js";
import { verifyCompliancePack } from "./compliance/verify.js";
import { resolveCredentials } from "./credentials.js";
import type { Client } from "./domain/clients.js";
import { loadClients } from "./domain/clients.js";
import { loadRequirements } from "./domain/requirements.js";
import { Logger } from "./logger.js";
import { readNotes, summariseNotes } from "./notes.js";

const TEMPLATE_ID = "ria-advisory-agreement";
const TEMPLATES_DIR = fileURLToPath(new URL("../config/templates", import.meta.url));
const DEFAULT_CONSENT_MATRIX_PATH = fileURLToPath(new URL("../state/consent-matrix.json", import.meta.url));

function getFlagValue(args: string[], flag: string): string | undefined {
  const idx = args.indexOf(flag);
  return idx === -1 ? undefined : args[idx + 1];
}

async function listRequirements(): Promise<void> {
  const requirements = await loadRequirements();
  console.log(`${requirements.length} SEBI requirement(s) tracked:\n`);
  for (const r of requirements) {
    console.log(`${r.id}  [${r.frequency} / ${r.applies_to}]`);
    console.log(`  ${r.title}`);
    console.log(`  ${r.citation}`);
    console.log("");
  }
}

async function listClients(): Promise<void> {
  const clients = await loadClients();
  console.log(`${clients.length} advisory client(s) on file:\n`);
  for (const c of clients) {
    const aiTag = c.ai_assisted ? "AI-assisted" : "non-AI";
    const reviewTag = c.risk_profile_reviewed_on ?? "NEVER REVIEWED";
    console.log(
      `${c.id}  ${c.name} (${c.advisory_type}, agreement ${c.agreement_version}, ${aiTag}) — onboarded ${c.onboarded_on}, risk review ${reviewTag}`,
    );
  }
}

async function runCoverage(args: string[]): Promise<void> {
  const notesDir = getFlagValue(args, "--notes") ?? "./corpus/ria-compliance";
  const opsCapArg = getFlagValue(args, "--ops-cap");
  const opsCap = opsCapArg ? Number(opsCapArg) : CONFIG.OPS_CAP;
  const todayArg = getFlagValue(args, "--today");
  const today = todayArg ? new Date(todayArg) : new Date();

  const logger = new Logger();
  const creds = await resolveCredentials(logger);
  const ledger = new OpsLedger(logger, opsCap);
  const client = new SuperDocsClient(creds.api_key, logger, ledger);

  const [requirements, clients, notes] = await Promise.all([
    loadRequirements(),
    loadClients(),
    readNotes(notesDir),
  ]);

  const entries = await assessCoverage(client, ledger, requirements, clients, notes, today);

  console.log(`\n=== Coverage report (${notes.length} note file(s) from ${notesDir}) ===\n`);
  console.log(formatCoverageReport(entries, clients, requirements));

  const byStatus = { EVIDENCED: 0, STALE: 0, MISSING: 0, INCONSISTENT: 0 };
  for (const e of entries) byStatus[e.status]++;
  console.log(
    `\n${entries.length} entries — EVIDENCED ${byStatus.EVIDENCED}, STALE ${byStatus.STALE}, MISSING ${byStatus.MISSING}, INCONSISTENT ${byStatus.INCONSISTENT}`,
  );

  console.log(`\n${ledger.report()}\n`);
  console.log(`total ops charged: ${ledger.spent}`);
  console.log(`monthly remaining: ${ledger.remaining ?? "?"}`);

  await logger.flush("compliance-coverage-log.json");
}

async function runGenerate(args: string[]): Promise<void> {
  const notesDir = getFlagValue(args, "--notes") ?? "./corpus/ria-compliance";
  const opsCapArg = getFlagValue(args, "--ops-cap");
  const opsCap = opsCapArg ? Number(opsCapArg) : CONFIG.OPS_CAP;
  const todayArg = getFlagValue(args, "--today");
  const today = todayArg ? new Date(todayArg) : new Date();
  const clientsArg = getFlagValue(args, "--clients");
  const selectedIds = clientsArg ? new Set(clientsArg.split(",").map((s) => s.trim())) : null;

  const logger = new Logger();
  const creds = await resolveCredentials(logger);
  const ledger = new OpsLedger(logger, opsCap);
  const client = new SuperDocsClient(creds.api_key, logger, ledger);

  const [requirements, allClients, notes] = await Promise.all([
    loadRequirements(),
    loadClients(),
    readNotes(notesDir),
  ]);

  const clients: Client[] = selectedIds ? allClients.filter((c) => selectedIds.has(c.id)) : allClients;
  if (clients.length === 0) {
    throw new Error(`runGenerate: no clients matched --clients "${clientsArg}"`);
  }
  console.log(`[INFO] generating pack(s) for: ${clients.map((c) => c.id).join(", ")}`);

  logger.step("planning per-client pack outlines");
  const digest = summariseNotes(notes);
  const { outlines } = await planCompliancePacks(client, ledger, requirements, allClients, digest);

  logger.step("assessing coverage");
  const coverageEntries = await assessCoverage(client, ledger, requirements, allClients, notes, today);

  for (const c of clients) {
    const outline = outlines.find((o) => o.client_id === c.id);
    if (!outline) {
      console.warn(`[WARN] no plan outline returned for ${c.id} — skipping`);
      continue;
    }

    const plannedSections = buildPlannedSections(outline, coverageEntries, requirements);

    logger.step(`generating pack for ${c.id} (${c.name})`);
    const draft = await generateCompliancePack(client, ledger, c, outline, plannedSections);
    console.log(`[OK] pack drafted: ${draft.durableDocumentId ?? draft.documentId}`);

    if (draft.durableDocumentId) {
      logger.step(`verifying pack for ${c.id}`);
      const result = await verifyCompliancePack(client, draft.durableDocumentId, plannedSections);
      if (!result.ok) {
        console.warn(`[WARN] ${c.id}: verification failed — see warnings above`);
      }
    } else {
      console.warn(`[WARN] ${c.id}: no durable document id — skipping verification`);
    }
  }

  console.log(`\n${ledger.report()}\n`);
  console.log(`total ops charged: ${ledger.spent}`);
  console.log(`monthly remaining: ${ledger.remaining ?? "?"}`);

  await logger.flush("compliance-generate-log.json");
}

/**
 * Registers the two known template versions and, for every client, records
 * their historical agreement issuance and (where the corpus documents a
 * signed date) their consent — idempotent, so re-running never duplicates
 * an issuance already on file. This is the one place the registry gets
 * populated from the corpus; everything downstream (--matrix) only reads.
 */
async function runRegistrySeed(args: string[]): Promise<void> {
  const notesDir = getFlagValue(args, "--notes") ?? "./corpus/ria-compliance";

  const store = await loadVersionStore();

  const v1Content = await readFile(path.join(TEMPLATES_DIR, "ria-advisory-agreement-v1.md"), "utf8");
  const v2Content = await readFile(path.join(TEMPLATES_DIR, "ria-advisory-agreement-v2.md"), "utf8");
  registerTemplateVersion(store, TEMPLATE_ID, "v1", "2015-04-01", ["RIA-AGR-01"], v1Content);
  registerTemplateVersion(store, TEMPLATE_ID, "v2", "2023-01-01", ["RIA-AGR-01", "RIA-AI-01"], v2Content);

  const clients = await loadClients();
  const notes = await readNotes(notesDir);
  const onboardingNote = notes.find((n) => n.name === "client-onboarding-notes.md");

  let issued = 0;
  let consented = 0;

  for (const c of clients) {
    const alreadyIssued = store.client_versions.some(
      (r) => r.client_id === c.id && r.template_id === TEMPLATE_ID && r.version === c.agreement_version,
    );
    if (alreadyIssued) continue;

    recordIssue(store, c.id, TEMPLATE_ID, c.agreement_version, c.onboarded_on);
    issued++;

    const block = onboardingNote ? blockForClient(onboardingNote, c.id) : null;
    const evidence = block ? findInBlock(block, ["agreement"])[0] : undefined;
    if (evidence) {
      recordConsent(store, c.id, TEMPLATE_ID, c.agreement_version, c.onboarded_on, `${evidence.file}:${evidence.line}`);
      consented++;
    } else {
      console.warn(`[WARN] runRegistrySeed: no agreement-signing evidence found for ${c.id} — issued without consent recorded`);
    }
  }

  await saveVersionStore(store);
  console.log(`[OK] registry seeded: ${issued} new issuance(s), ${consented} consent(s) recorded`);
  console.log(`[INFO] store written to ${DEFAULT_VERSION_STORE_PATH}`);
}

async function runMatrix(): Promise<void> {
  const store = await loadVersionStore();
  const clients = await loadClients();
  const matrix = buildConsentMatrix(store, clients);

  console.log(formatConsentMatrixTable(matrix));

  const behind = clientsBehind(store, TEMPLATE_ID);
  console.log(`\n${behind.length} client(s) behind on ${TEMPLATE_ID}:`);
  for (const b of behind) {
    console.log(`  ${b.client_id}: issued ${b.version} (current: ${b.current_version}) — ${b.reason}`);
  }

  await mkdir(path.dirname(DEFAULT_CONSENT_MATRIX_PATH), { recursive: true });
  await writeFile(DEFAULT_CONSENT_MATRIX_PATH, `${JSON.stringify(matrix, null, 2)}\n`, "utf8");
  console.log(`\n[INFO] matrix written to ${DEFAULT_CONSENT_MATRIX_PATH}`);
}

export async function runComplianceCli(args: string[]): Promise<void> {
  if (args.includes("--list-requirements")) {
    await listRequirements();
    return;
  }

  if (args.includes("--list-clients")) {
    await listClients();
    return;
  }

  if (args.includes("--coverage")) {
    await runCoverage(args);
    return;
  }

  if (args.includes("--generate")) {
    await runGenerate(args);
    return;
  }

  if (args.includes("--registry-seed")) {
    await runRegistrySeed(args);
    return;
  }

  if (args.includes("--matrix")) {
    await runMatrix();
    return;
  }

  console.log(
    "compliance: no recognised command. Try --list-requirements, --list-clients, --coverage, --generate, --registry-seed or --matrix.",
  );
  process.exitCode = 1;
}
