import type { Feature } from 'geojson'
import snapshot from './landing-data.json'

// Real exported results for public places, never synthetic answers or chat history.
// Refresh with api/scripts/export_landing_examples.py; the snapshot date stays visible.
export const SAMPLE_DATE = new Intl.DateTimeFormat('cs-CZ').format(new Date(snapshot.generated_at))

export const SAMPLES = snapshot.examples.map((sample) => ({
  ...sample,
  features: sample.features as Feature[],
}))
