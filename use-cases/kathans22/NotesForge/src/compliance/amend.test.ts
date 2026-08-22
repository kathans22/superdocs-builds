import assert from "node:assert/strict";
import { test } from "node:test";
import type { Requirement } from "../domain/requirements.js";
import { recordIssue, registerTemplateVersion, type VersionStore } from "./registry.js";
import { detectAmendments, scopeAmendment } from "./amend.js";

function req(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: "RIA-AI-01",
    citation: "SEBI ... Regulation 15(14) and 18(9)",
    title: "AI-assisted advice documented and disclosed",
    obligation: "Original obligation text.",
    evidence_expected: ["AI usage disclosure"],
    frequency: "continuous",
    applies_to: "advisory_clients",
    ...overrides,
  };
}

test("detectAmendments: identical registers produce no events", () => {
  const baseline = [req()];
  const updated = [req()];
  assert.deepEqual(detectAmendments(baseline, updated), []);
});

test("detectAmendments: a changed obligation text is a changed_obligation event", () => {
  const baseline = [req({ obligation: "Original obligation text." })];
  const updated = [req({ obligation: "Extended obligation text with a new clause." })];

  const events = detectAmendments(baseline, updated);
  assert.equal(events.length, 1);
  assert.equal(events[0]!.kind, "changed_obligation");
  assert.equal(events[0]!.requirement_id, "RIA-AI-01");
  assert.equal(events[0]!.previous?.obligation, "Original obligation text.");
  assert.equal(events[0]!.updated.obligation, "Extended obligation text with a new clause.");
});

test("detectAmendments: a requirement id absent from baseline is new_requirement", () => {
  const baseline = [req({ id: "RIA-AI-01" })];
  const updated = [req({ id: "RIA-AI-01" }), req({ id: "RIA-NEW-01", title: "Brand new obligation" })];

  const events = detectAmendments(baseline, updated);
  assert.equal(events.length, 1);
  assert.equal(events[0]!.kind, "new_requirement");
  assert.equal(events[0]!.requirement_id, "RIA-NEW-01");
  assert.equal(events[0]!.previous, null);
});

test("detectAmendments: unrelated requirements produce no events even when one changes", () => {
  const baseline = [req({ id: "RIA-AI-01" }), req({ id: "RIA-FEE-01", title: "Fee disclosure" })];
  const updated = [
    req({ id: "RIA-AI-01", obligation: "Extended obligation text." }),
    req({ id: "RIA-FEE-01", title: "Fee disclosure" }),
  ];

  const events = detectAmendments(baseline, updated);
  assert.equal(events.length, 1);
  assert.equal(events[0]!.requirement_id, "RIA-AI-01");
});

test("detectAmendments: an empty baseline (first ever run) treats every requirement as new", () => {
  const updated = [req({ id: "RIA-AI-01" }), req({ id: "RIA-FEE-01" })];
  const events = detectAmendments([], updated);
  assert.equal(events.length, 2);
  assert.ok(events.every((e) => e.kind === "new_requirement"));
});

function seededStore(): VersionStore {
  // Mirrors the real corpus shape: v1 (agreement-only) is superseded by v2
  // (agreement + AI clause); non-AI clients stayed on v1, AI-assisted
  // clients are on v2.
  const store: VersionStore = { template_versions: [], client_versions: [] };
  registerTemplateVersion(store, "ria-advisory-agreement", "v1", "2015-04-01", ["RIA-AGR-01"], "v1 content");
  registerTemplateVersion(
    store,
    "ria-advisory-agreement",
    "v2",
    "2023-01-01",
    ["RIA-AGR-01", "RIA-AI-01"],
    "v2 content",
  );
  recordIssue(store, "CL-01", "ria-advisory-agreement", "v1", "2021-03-10"); // non-AI
  recordIssue(store, "CL-02", "ria-advisory-agreement", "v2", "2023-06-15"); // AI-assisted
  recordIssue(store, "CL-04", "ria-advisory-agreement", "v2", "2024-01-20"); // AI-assisted
  return store;
}

test("scopeAmendment: only the template referencing the changed requirement, and only its current holders", () => {
  const store = seededStore();
  const event = {
    requirement_id: "RIA-AI-01",
    kind: "changed_obligation" as const,
    previous: req(),
    updated: req({ obligation: "Extended." }),
  };

  const scope = scopeAmendment(store, event);

  assert.deepEqual(scope.affected_template_ids, ["ria-advisory-agreement"]);
  // CL-01 is on v1, which doesn't reference RIA-AI-01 at all — not in scope.
  assert.deepEqual(scope.affected_client_ids, ["CL-02", "CL-04"]);
});

test("scopeAmendment: a requirement no current template references has an empty blast radius", () => {
  const store = seededStore();
  const event = {
    requirement_id: "RIA-NW-01", // firm-level, not on any client agreement template
    kind: "changed_obligation" as const,
    previous: req({ id: "RIA-NW-01" }),
    updated: req({ id: "RIA-NW-01", obligation: "Extended." }),
  };

  const scope = scopeAmendment(store, event);
  assert.deepEqual(scope.affected_template_ids, []);
  assert.deepEqual(scope.affected_client_ids, []);
});
