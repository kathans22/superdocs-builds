import { useEffect, useState } from 'react';
import type { IntegrityReport } from './types';

// First 12 + last 6 characters — enough to eyeball-compare two hashes
// without reading 64 characters, full value always in `title` on hover.
function truncateHash(hash: string): string {
  if (hash.length <= 22) return hash;
  return `${hash.slice(0, 12)}…${hash.slice(-6)}`;
}

export default function Integrity() {
  const [report, setReport] = useState<IntegrityReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/integrity-report.json')
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json() as Promise<IntegrityReport>;
      })
      .then(setReport)
      .catch((err) => setError(String(err)));
  }, []);

  if (error) {
    return (
      <main className="integrity">
        <p className="load-error">Could not load the integrity report: {error}</p>
      </main>
    );
  }

  if (!report) {
    return (
      <main className="integrity">
        <p>Loading integrity report…</p>
      </main>
    );
  }

  const languages = Object.entries(report.core_identity);
  const languageCounts = Object.entries(report.languages)
    .map(([lang, count]) => `${lang} ${count}`)
    .join(' · ');

  return (
    <main className="integrity">
      <header className="integrity-header">
        <h1>Core Integrity</h1>
        <span className={`status-badge ${report.all_packs_pass ? 'pass' : 'fail'}`}>
          {report.all_packs_pass ? 'ALL PACKS PASS' : 'FAILING'}
        </span>
      </header>

      <p className="summary">
        Core v{report.core_version} · {report.packs} packs · {languageCounts}
      </p>

      <section className="identity">
        <h2>Core identity, per language</h2>
        {languages.map(([lang, entry]) => (
          <div key={lang} className={`identity-row ${entry.identical ? 'identical' : 'divergent'}`}>
            <div className="identity-lang">{lang}</div>
            <div className="identity-hash" title={entry.expected}>
              {truncateHash(entry.expected)}
            </div>
            <div className="identity-packs">
              {entry.packs.map((code) => (
                <span key={code} className="pack-chip">
                  {code}
                </span>
              ))}
            </div>
            <div className="identity-state">{entry.identical ? 'IDENTICAL' : 'DIVERGENT'}</div>
          </div>
        ))}
      </section>
    </main>
  );
}
