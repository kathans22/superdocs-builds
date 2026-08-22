import { OpsLedger } from "./budget.js";
import { SuperDocsClient } from "./client.js";
import { CONFIG } from "./config.js";
import { assessCoverage, formatCoverageReport } from "./compliance/coverage.js";
import { buildPlannedSections, generateCompliancePack } from "./compliance/generate.js";
import { planCompliancePacks } from "./compliance/plan.js";
import { verifyCompliancePack } from "./compliance/verify.js";
import { resolveCredentials } from "./credentials.js";
import type { Client } from "./domain/clients.js";
import { loadClients } from "./domain/clients.js";
import { loadRequirements } from "./domain/requirements.js";
import { Logger } from "./logger.js";
import { readNotes, summariseNotes } from "./notes.js";

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

  console.log(
    "compliance: no recognised command. Try --list-requirements, --list-clients, --coverage or --generate.",
  );
  process.exitCode = 1;
}
