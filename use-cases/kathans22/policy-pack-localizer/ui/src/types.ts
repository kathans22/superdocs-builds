// Shape of evidence/integrity-report.json — service.integrity_report()'s
// output. One language entry's `packs` sharing one `expected` hash is the
// build's central proof (e.g. FR and SN both under the fr hash); `identical`
// is false only if a pack's own re-hashed export failed to match it.

export interface CoreIdentityEntry {
  expected: string;
  packs: string[];
  identical: boolean;
}

export interface IntegrityReport {
  core_version: number;
  packs: number;
  languages: Record<string, number>;
  core_identity: Record<string, CoreIdentityEntry>;
  all_packs_pass: boolean;
  annex_divergence: Record<string, string>;
  // Not produced by service.integrity_report today — a pack that fails
  // verification raises PackIntegrityError and is never included in a
  // report at all (CLAUDE.md: a mismatch quarantines the pack, the run
  // does not report success). Optional here so the screen can show a
  // quarantine list the moment a report ever carries one, without lying
  // about a shape the current pipeline doesn't emit.
  quarantined_packs?: string[];
}
