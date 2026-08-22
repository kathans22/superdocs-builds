import { useState } from "react";
import { Placeholder } from "./screens/Placeholder";
import { useArtifacts } from "./useArtifacts";

const TABS = ["COVERAGE", "CLIENTS", "PACKS", "AMENDMENTS", "RUN"] as const;
type Tab = (typeof TABS)[number];

export default function App() {
  const [tab, setTab] = useState<Tab>("COVERAGE");
  const artifacts = useArtifacts();

  return (
    <>
      <header className="app-header">
        <h1>Meridian Advisory — Compliance Console</h1>
        <p className="app-subtitle">
          Reads the CLI's own run artifacts (state/*.json, out/). Every pack and notice is a draft for
          professional review, not a compliance certification.
        </p>
        <nav className="tab-bar" role="tablist">
          {TABS.map((t) => (
            <button key={t} type="button" role="tab" aria-selected={t === tab} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
      </header>

      <main className="app-main">
        {artifacts.status === "loading" && <p className="state-message">Loading run artifacts…</p>}
        {artifacts.status === "error" && (
          <p className="state-message error">
            {artifacts.message}
            <br />
            Run <code>npm run sync</code> in <code>ui/</code> after a compliance CLI command, then reload.
          </p>
        )}
        {artifacts.status === "ready" && (
          <>
            {tab === "COVERAGE" && <Placeholder name="COVERAGE" />}
            {tab === "CLIENTS" && <Placeholder name="CLIENTS" />}
            {tab === "PACKS" && <Placeholder name="PACKS" />}
            {tab === "AMENDMENTS" && <Placeholder name="AMENDMENTS" />}
            {tab === "RUN" && <Placeholder name="RUN" />}
          </>
        )}
      </main>
    </>
  );
}
