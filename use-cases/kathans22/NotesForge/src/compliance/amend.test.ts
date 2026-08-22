import assert from "node:assert/strict";
import { test } from "node:test";
import type { Requirement } from "../domain/requirements.js";
import { detectAmendments } from "./amend.js";

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
