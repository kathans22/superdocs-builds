export type Weight = 'shared' | 'vertical'

export type DivergenceReport = {
  evaluation: {
    passed: boolean
    failures: string[]
    mean_vertical_overlap: number
    mean_shared_overlap: number
    thresholds: {
      vertical_mean_max: number
      vertical_section_max: number
      shared_sections_gated: boolean
    }
  }
  report: {
    aggregates: {
      mean_vertical_overlap: number
      mean_shared_overlap: number
      vertical_cells: number
      shared_cells: number
    }
    pairs: Array<{
      vertical_a: string
      vertical_b: string
      sections: Record<string, number>
    }>
  }
  section_weights: Record<string, Weight>
  verticals: string[]
}

export function fmt(n: number): string {
  return n.toFixed(3)
}
