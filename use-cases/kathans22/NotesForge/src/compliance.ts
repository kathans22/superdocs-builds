import { loadClients } from "./domain/clients.js";
import { loadRequirements } from "./domain/requirements.js";

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

export async function runComplianceCli(args: string[]): Promise<void> {
  if (args.includes("--list-requirements")) {
    await listRequirements();
    return;
  }

  if (args.includes("--list-clients")) {
    await listClients();
    return;
  }

  console.log("compliance: no recognised command. Try --list-requirements or --list-clients.");
  process.exitCode = 1;
}
