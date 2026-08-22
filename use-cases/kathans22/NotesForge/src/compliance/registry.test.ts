import assert from "node:assert/strict";
import { test } from "node:test";
import {
  clientsBehind,
  clientsOnVersion,
  currentVersion,
  recordIssue,
  registerTemplateVersion,
  RegistryError,
  type VersionStore,
} from "./registry.js";

function freshStore(): VersionStore {
  return { template_versions: [], client_versions: [] };
}

test("registerTemplateVersion + currentVersion: a freshly registered version is current", () => {
  const store = freshStore();
  registerTemplateVersion(store, "agreement", "v1", "2015-04-01", ["RIA-AGR-01"], "content v1");
  const current = currentVersion(store, "agreement");
  assert.equal(current?.version, "v1");
  assert.equal(current?.superseded_by, null);
});

test("recordIssue: refuses to issue a template version that was never registered", () => {
  const store = freshStore();
  assert.throws(
    () => recordIssue(store, "CL-01", "agreement", "v1", "2021-03-10"),
    RegistryError,
  );
});

test("recordIssue: succeeds once the template version is registered", () => {
  const store = freshStore();
  registerTemplateVersion(store, "agreement", "v1", "2015-04-01", ["RIA-AGR-01"], "content v1");
  const record = recordIssue(store, "CL-01", "agreement", "v1", "2021-03-10");
  assert.equal(record.consented_on, null);
  assert.equal(record.consent_evidence, null);
  assert.equal(store.client_versions.length, 1);
});

test("clientsOnVersion: reflects each client's most recent issuance, not their first", () => {
  const store = freshStore();
  registerTemplateVersion(store, "agreement", "v1", "2015-04-01", ["RIA-AGR-01"], "content v1");
  registerTemplateVersion(store, "agreement", "v2", "2023-01-01", ["RIA-AGR-01", "RIA-AI-01"], "content v2");
  recordIssue(store, "CL-01", "agreement", "v1", "2021-03-10");
  recordIssue(store, "CL-02", "agreement", "v1", "2020-01-01");
  recordIssue(store, "CL-02", "agreement", "v2", "2023-06-15"); // re-issued later

  assert.deepEqual(clientsOnVersion(store, "agreement", "v1"), ["CL-01"]);
  assert.deepEqual(clientsOnVersion(store, "agreement", "v2"), ["CL-02"]);
});

test("clientsBehind: a client only ever issued the superseded version is behind", () => {
  const store = freshStore();
  registerTemplateVersion(store, "agreement", "v1", "2015-04-01", ["RIA-AGR-01"], "content v1");
  recordIssue(store, "CL-01", "agreement", "v1", "2021-03-10");
  // Manually mark v1 superseded, as registering v2 will do once that lands.
  store.template_versions[0]!.superseded_by = "v2";
  registerTemplateVersion(store, "agreement", "v2", "2023-01-01", ["RIA-AGR-01", "RIA-AI-01"], "content v2");

  const behind = clientsBehind(store, "agreement");
  assert.equal(behind.length, 1);
  assert.equal(behind[0]!.client_id, "CL-01");
  assert.equal(behind[0]!.reason, "outdated_version_and_not_consented");
});

test("clientsBehind: a client on the current version with nothing else wrong is not behind", () => {
  const store = freshStore();
  registerTemplateVersion(store, "agreement", "v1", "2015-04-01", ["RIA-AGR-01"], "content v1");
  const record = recordIssue(store, "CL-04", "agreement", "v1", "2024-01-20");
  record.consented_on = "2024-01-20";
  record.consent_evidence = "client-onboarding-notes.md:33";

  assert.deepEqual(clientsBehind(store, "agreement"), []);
});
