import { useEffect, useState } from 'react'
import Divergence from './Divergence.tsx'
import Nav from './Nav.tsx'
import Verticals from './Verticals.tsx'
import type { DivergenceReport } from './report'
import report from './data/divergence-report.json'
import verticals from './data/verticals.json'
import { parseHash, type Screen } from './screen'
import type { VerticalsFile } from './Verticals.tsx'
import './Divergence.css'
import './App.css'

export default function App() {
  const [screen, setScreen] = useState<Screen>(() => parseHash())

  useEffect(() => {
    const onHash = () => setScreen(parseHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  return (
    <>
      <Nav current={screen} />
      {screen === 'verticals' ? (
        <Verticals file={verticals as VerticalsFile} />
      ) : (
        <Divergence report={report as DivergenceReport} />
      )}
    </>
  )
}
