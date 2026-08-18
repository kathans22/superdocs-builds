import type { DivergenceReport } from './report'
import { fmt } from './report'
import './Divergence.css'

type Props = {
  report: DivergenceReport
}

export default function Divergence({ report }: Props) {
  const { evaluation, report: inner } = report
  const verticalMean = evaluation.mean_vertical_overlap
  const sharedMean = evaluation.mean_shared_overlap
  const max = evaluation.thresholds.vertical_mean_max

  return (
    <main className="div">
      <p className="div-kicker">ClarityDocs · speaking scripts · not a slide deck</p>
      <h1 className="div-title">Divergence</h1>
      <p className="div-lede">
        Pairwise lexical overlap. Vertical-tagged sections must differ in substance.
        Shared sections may overlap — the product is held constant. The inverse of
        Build&nbsp;1’s identical core-hash, made numeric.
      </p>

      <section className="div-means" aria-label="Mean overlap by weight class">
        <article className="div-mean">
          <p className="div-mean-label">Vertical mean</p>
          <p className="div-mean-value">{fmt(verticalMean)}</p>
          <p className="div-mean-note">
            Must stay below {fmt(max)}. {inner.aggregates.vertical_cells} pair×section
            cells.
          </p>
        </article>
        <article className="div-mean div-mean-shared">
          <p className="div-mean-label">Shared mean</p>
          <p className="div-mean-value">{fmt(sharedMean)}</p>
          <p className="div-mean-note">
            Reported, not gated. Opening, overview, call to action.{' '}
            {inner.aggregates.shared_cells} cells.
          </p>
        </article>
      </section>
    </main>
  )
}
