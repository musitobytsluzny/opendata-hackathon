import { expect, type Page } from '@playwright/test'

export const answer = {
  text: '## Dostupné obce\n\n**Plzeň-město**: 181 200 obyvatel.\n\n| Okres | Počet |\n| --- | ---: |\n| Plzeň-město | 181 200 |\n\n[Odkaz](https://example.com)\n\n[Chybný odkaz](javascript:alert(1))\n\n<img src="https://example.com/tracker" onerror="alert(1)">\n\n<script>alert(1)</script>',
  metric: 'Počet obyvatel dostupných obcí',
  unit: '',
  sample: true,
  rows: [{ okres: 'CZ0323000000', value: 181200 }],
  source: { publisher: 'Syntetická demo data ETL', name: '1 obec', period: '2024' },
}

export async function authenticate(page: Page) {
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({ json: { id: 123, username: 'ui-test' } }),
  )
  await page.route('**/api/data/catalog', (route) =>
    route.fulfill({ json: { datasets: [{ row_count: 3, data_kind: 'demo' }] } }),
  )
  await page.addInitScript(() => {
    const encode = (value: object) =>
      btoa(JSON.stringify(value)).replaceAll('=', '').replaceAll('+', '-').replaceAll('/', '_')
    // API responses are intercepted; this fixture grants no access to a real server.
    localStorage.setItem(
      'auth_token',
      encode({ alg: 'none' }) +
        '.' +
        encode({
          sub: '123',
          username: 'ui-test',
          iat: Math.floor(Date.now() / 1000),
          exp: Math.floor(Date.now() / 1000) + 3600,
        }) +
        '.fixture',
    )
  })
  await page.goto('/mapa')
  await expect(page.locator('.panel__status')).toHaveText('Ukázková data')
}
