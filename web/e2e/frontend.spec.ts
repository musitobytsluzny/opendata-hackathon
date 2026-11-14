import { expect, test, type Page } from '@playwright/test'

const answer = {
  text: '## Dostupné obce\n\n**Plzeň-město**: 181 200 obyvatel.\n\n| Okres | Počet |\n| --- | ---: |\n| Plzeň-město | 181 200 |\n\n[Odkaz](https://example.com)\n\n[Chybný odkaz](javascript:alert(1))\n\n<img src="https://example.com/tracker" onerror="alert(1)">\n\n<script>alert(1)</script>',
  metric: 'Počet obyvatel dostupných obcí',
  unit: '',
  sample: true,
  rows: [{ okres: 'CZ0323000000', value: 181200 }],
  source: { publisher: 'Syntetická demo data ETL', name: '1 obec', period: '2024' },
}

async function authenticate(page: Page) {
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

test.beforeEach(async ({ page }) => {
  // Geometry and chat must remain usable independently of external imagery.
  await page.route(/https:\/\/(tiles\.maps\.eox\.at|ags\.cuzk\.cz)\//, (route) => route.abort())
})

test('map worker is a valid local asset on landing and login', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.text().includes('Worker failed')) errors.push(message.text())
  })
  for (const path of ['/', '/prihlaseni']) {
    const workerPromise = page.waitForEvent('worker')
    await page.goto(path)
    const worker = await workerPromise
    expect(new URL(worker.url()).origin).toBe('http://127.0.0.1:4173')
    expect(await worker.evaluate(() => typeof self.postMessage)).toBe('function')
    await expect(page.locator('.maplibregl-map')).toBeVisible()
    expect((await page.locator('.maplibregl-map').boundingBox())!.height).toBeGreaterThan(500)
  }
  expect(errors).toEqual([])
})

test('chat renders safe Markdown, sends multiline questions and exports data', async ({ page }) => {
  const questions: string[] = []
  await page.route('**/api/chat/ask', async (route) => {
    questions.push(route.request().postDataJSON().question)
    await route.fulfill({ json: answer })
  })
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('Kolik obyvatel?')
  await input.press('Shift+Enter')
  expect(questions).toEqual([])
  await input.press('Enter')
  await expect(page.locator('.markdown h2')).toHaveText('Dostupné obce')
  await expect(page.locator('.markdown strong')).toHaveText('Plzeň-město')
  await expect(page.locator('.markdown table')).toHaveCount(1)
  await expect(
    page.locator('.markdown img, .markdown script, .markdown a[href^="javascript:"]'),
  ).toHaveCount(0)
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Stáhnout CSV' }).click()
  expect((await downloadPromise).suggestedFilename()).toBe('kartogram-data.csv')
  await page.getByRole('button', { name: 'Pokrytí a omezení dat' }).click()
  await expect.poll(() => questions.length).toBe(2)
})

test('chat width supports drag, keyboard and persistence; settings fit mobile', async ({
  page,
}) => {
  await authenticate(page)
  const handle = page.getByRole('separator', { name: 'Šířka konverzace' })
  const box = (await handle.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 320, box.y + box.height / 2, { steps: 12 })
  await page.mouse.up()
  await expect(handle).toHaveAttribute('aria-valuenow', '650')
  await expect
    .poll(async () => Math.round((await page.locator('.panel').boundingBox())!.width))
    .toBe(650)
  await expect
    .poll(() =>
      page.evaluate(() => JSON.parse(localStorage.getItem('kartogram:preferences:v1')!).panelWidth),
    )
    .toBe(650)
  await page.reload()
  await expect(handle).toHaveAttribute('aria-valuenow', '650')
  await handle.press('End')
  await expect(handle).toHaveAttribute('aria-valuenow', '1080')
  await handle.press('Home')
  await expect(handle).toHaveAttribute('aria-valuenow', '330')
  await page.getByRole('button', { name: 'Nastavení', exact: true }).click()
  await page.getByLabel('Ztmavit okolní státy', { exact: true }).uncheck()
  await page.getByLabel('Názvy měst', { exact: true }).uncheck()
  await expect(page.locator('.town')).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Velikost textu', exact: true }).selectOption('large')
  await expect
    .poll(() =>
      page.evaluate(() => JSON.parse(localStorage.getItem('kartogram:preferences:v1')!).dimOutside),
    )
    .toBe(false)
  await page.reload()
  await page.getByRole('button', { name: 'Nastavení', exact: true }).click()
  await expect(page.getByLabel('Ztmavit okolní státy', { exact: true })).not.toBeChecked()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(handle).toHaveCount(0)
  const settings = (await page
    .getByRole('dialog', { name: 'Nastavení', exact: true })
    .boundingBox())!
  expect(settings.y).toBeGreaterThanOrEqual(0)
  expect(settings.y + settings.height).toBeLessThanOrEqual(844)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
