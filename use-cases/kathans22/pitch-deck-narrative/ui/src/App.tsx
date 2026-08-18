import Divergence from './Divergence.tsx'
import type { DivergenceReport } from './report'
import report from './data/divergence-report.json'

export default function App() {
  return <Divergence report={report as DivergenceReport} />
}
