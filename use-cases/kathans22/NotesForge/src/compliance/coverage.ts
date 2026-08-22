import type { NoteFile } from "../notes.js";
import type { Client } from "../domain/clients.js";
import type { Requirement } from "../domain/requirements.js";

export type CoverageStatus = "EVIDENCED" | "STALE" | "MISSING" | "INCONSISTENT";

export interface EvidenceRef {
  file: string;
  line: number;
  excerpt: string;
}

export interface CoverageEntry {
  requirement_id: string;
  client_id: string | null; // null = firm-level
  status: CoverageStatus;
  detail: string;
  evidence: EvidenceRef[];
  method: "deterministic" | "model";
}

const ANNUAL_STALE_DAYS = 365;

/**
 * Whether a requirement applies to a given client at all. Firm-level
 * requirements never generate a per-client entry; RIA-AI-01 only applies to
 * clients actually marked ai_assisted. This is a fact about the requirement
 * and the client's own data — never a model's call to make.
 */
export function isRequirementApplicable(requirement: Requirement, client: Client): boolean {
  if (requirement.applies_to === "firm") return false;
  if (requirement.id === "RIA-AI-01") return client.ai_assisted;
  return true;
}

export function findLinesContaining(notes: NoteFile[], fileName: string, needle: string): EvidenceRef[] {
  const note = notes.find((n) => n.name === fileName);
  if (!note) return [];
  const hits: EvidenceRef[] = [];
  const lines = note.content.split(/\r?\n/);
  const needleLower = needle.toLowerCase();
  lines.forEach((line, idx) => {
    if (line.toLowerCase().includes(needleLower)) {
      hits.push({ file: note.name, line: idx + 1, excerpt: line.trim() });
    }
  });
  return hits;
}

function corpusHasAnyMention(notes: NoteFile[], keywords: string[]): EvidenceRef[] {
  const hits: EvidenceRef[] = [];
  for (const note of notes) {
    const lines = note.content.split(/\r?\n/);
    lines.forEach((line, idx) => {
      const lower = line.toLowerCase();
      if (keywords.some((k) => lower.includes(k))) {
        hits.push({ file: note.name, line: idx + 1, excerpt: line.trim() });
      }
    });
  }
  return hits;
}

/**
 * RIA-RISK-01: the review date lives in structured config
 * (client.risk_profile_reviewed_on), not free text — so freshness is
 * arithmetic, not a model call. The evidence line (for citation) is a
 * secondary, best-effort text lookup in risk-profiling-log.md.
 */
function assessRiskProfiling(client: Client, notes: NoteFile[], today: Date): CoverageEntry {
  const evidence = findLinesContaining(notes, "risk-profiling-log.md", client.id);

  if (client.risk_profile_reviewed_on === null) {
    return {
      requirement_id: "RIA-RISK-01",
      client_id: client.id,
      status: "MISSING",
      detail: "no risk profiling review on record for this client",
      evidence,
      method: "deterministic",
    };
  }

  const reviewedOn = new Date(client.risk_profile_reviewed_on);
  const daysSince = Math.floor((today.getTime() - reviewedOn.getTime()) / (1000 * 60 * 60 * 24));

  if (daysSince > ANNUAL_STALE_DAYS) {
    return {
      requirement_id: "RIA-RISK-01",
      client_id: client.id,
      status: "STALE",
      detail: `last reviewed ${client.risk_profile_reviewed_on}, ${daysSince} days ago (annual review is overdue)`,
      evidence,
      method: "deterministic",
    };
  }

  return {
    requirement_id: "RIA-RISK-01",
    client_id: client.id,
    status: "EVIDENCED",
    detail: `last reviewed ${client.risk_profile_reviewed_on}, ${daysSince} days ago (within the annual window)`,
    evidence,
    method: "deterministic",
  };
}

const FIRM_KEYWORDS: Record<string, string[]> = {
  "RIA-NW-01": ["net worth"],
  "RIA-REC-01": [
    "record retention",
    "records retained",
    "record index",
    "records index",
    "retention window",
    "records retriev",
  ],
};

/**
 * Firm-level requirements: presence/absence of a matching mention anywhere
 * in the corpus. Absence is unambiguous — zero hits is zero hits, no model
 * needed to notice nothing is there. This is the honesty rule made
 * mechanical: a requirement with no supporting evidence is MISSING, full
 * stop, never inferred from the surrounding notes.
 */
function assessFirmLevel(requirement: Requirement, notes: NoteFile[]): CoverageEntry {
  const keywords = FIRM_KEYWORDS[requirement.id] ?? [];
  const evidence = corpusHasAnyMention(notes, keywords);

  if (evidence.length === 0) {
    return {
      requirement_id: requirement.id,
      client_id: null,
      status: "MISSING",
      detail: `no mention of ${keywords.map((k) => `"${k}"`).join(" / ")} found anywhere in the corpus`,
      evidence: [],
      method: "deterministic",
    };
  }

  return {
    requirement_id: requirement.id,
    client_id: null,
    status: "EVIDENCED",
    detail: `evidenced in ${new Set(evidence.map((e) => e.file)).size} file(s)`,
    evidence,
    method: "deterministic",
  };
}

/**
 * Deterministic pass only: firm-level requirements (keyword presence /
 * absence) and RIA-RISK-01 (a date comparison). Per-client text-evidence
 * requirements — agreement, suitability, AI disclosure, fee consistency —
 * are added in the next increment, alongside the one genuinely ambiguous
 * case that escalates to a model call.
 */
export function assessCoverageDeterministic(
  requirements: Requirement[],
  clients: Client[],
  notes: NoteFile[],
  today: Date = new Date(),
): CoverageEntry[] {
  const entries: CoverageEntry[] = [];

  for (const requirement of requirements) {
    if (requirement.applies_to === "firm") {
      entries.push(assessFirmLevel(requirement, notes));
      continue;
    }

    if (requirement.id === "RIA-RISK-01") {
      for (const c of clients) {
        if (!isRequirementApplicable(requirement, c)) continue;
        entries.push(assessRiskProfiling(c, notes, today));
      }
    }
  }

  return entries;
}
