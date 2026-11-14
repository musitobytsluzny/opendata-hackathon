import { expect, test } from '@playwright/test'

import { answer, authenticate } from './fixtures'

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
    if (path === '/') {
      const hero = page.locator('.hero')
      const actions = page.locator('.hero__actions')
      await expect(actions).toBeVisible()
      const layout = await page.evaluate(() => ({
        heroBottom: document.querySelector('.hero')!.getBoundingClientRect().bottom,
        actionsBottom: document.querySelector('.hero__actions')!.getBoundingClientRect().bottom,
        nextSectionTop: document.querySelector('.series-demo')!.getBoundingClientRect().top,
      }))
      expect(layout.actionsBottom).toBeLessThan(layout.heroBottom)
      expect(layout.nextSectionTop).toBeGreaterThanOrEqual(layout.heroBottom)
      await expect(hero.locator('h1')).toContainText('Zeptejte se')
      await expect(hero.locator('h1')).toContainText('Plzeňského')
      await expect(hero.locator('.hero__exchange')).toContainText(/parcela 438\/1/i)
      await expect(hero.locator('.hero__answer')).toContainText('375 m²', { timeout: 10000 })
    }
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
  const delta = 650 - (await page.locator('.panel').boundingBox())!.width
  await page.mouse.move(box.x + box.width / 2 + delta, box.y + box.height / 2, { steps: 12 })
  await page.mouse.up()
  await expect(handle).toHaveAttribute('aria-valuenow', '650')
  await expect
    .poll(async () => Math.round((await page.locator('.panel').boundingBox())!.width))
    .toBe(650)
  await expect
    .poll(() =>
      page.evaluate(
        () => JSON.parse(localStorage.getItem('kartogram:preferences:v1') ?? '{}').panelWidth,
      ),
    )
    .toBe(650)
  await page.reload()
  await expect(handle).toHaveAttribute('aria-valuenow', '650')
  await handle.press('End')
  await expect(handle).toHaveAttribute('aria-valuenow', '1080')
  await handle.press('Home')
  await expect(handle).toHaveAttribute('aria-valuenow', '330')
  await page.locator('.map-layers summary').click()
  await page.getByLabel('Ztmavit okolní státy', { exact: true }).uncheck()
  await page.getByLabel('Názvy měst', { exact: true }).uncheck()
  await expect(page.locator('.town')).toHaveCount(0)
  await page.getByRole('button', { name: 'Nastavení', exact: true }).click()
  await page.getByRole('combobox', { name: 'Velikost textu', exact: true }).selectOption('large')
  await expect
    .poll(() =>
      page.evaluate(
        () => JSON.parse(localStorage.getItem('kartogram:preferences:v1') ?? '{}').dimOutside,
      ),
    )
    .toBe(false)
  await page.reload()
  await page.locator('.map-layers summary').click()
  await page.getByRole('button', { name: 'Nastavení', exact: true }).click()
  await expect(page.getByLabel('Ztmavit okolní státy', { exact: true })).not.toBeChecked()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(handle).toHaveCount(0)
  const dialog = page.getByRole('dialog', { name: 'Nastavení', exact: true })
  await expect
    .poll(async () => {
      const box = await dialog.boundingBox()
      return box ? box.y + box.height : Number.POSITIVE_INFINITY
    })
    .toBeLessThanOrEqual(844)
  const settings = (await dialog.boundingBox())!
  expect(settings.y).toBeGreaterThanOrEqual(0)
  expect(settings.y + settings.height).toBeLessThanOrEqual(844)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('landing examples switch real route and population geometries without login', async ({
  page,
}) => {
  await page.goto('/')
  const result = page.locator('.series-demo__result')
  await expect(result).toContainText('Bolevec')
  await expect(result).toContainText('RÚIAN')
  const cards = page.locator('.series-demo__item')
  await cards.nth(1).click()
  await expect(result).toContainText('Rokycany')
  await expect(result).toContainText('OSRM')
  await expect(page.locator('.workspace-map-label').filter({ hasText: 'km' })).toHaveCount(3)
  await cards.nth(2).click()
  await expect(page).toHaveURL('/')
  await expect(result).toContainText('obyvatel')
  await expect(page.locator('.workspace-map-label').filter({ hasText: 'obyvatel' })).toHaveCount(5)
  await expect(page.locator('.workspace-map-label').filter({ hasText: 'km' })).toHaveCount(0)
  await cards.nth(4).click()
  await expect(result).toContainText('záplavové')
  await expect(result).toContainText('VÚV')
  await expect(page.locator('.workspace-map-label').filter({ hasText: 'obyvatel' })).toHaveCount(0)
  await expect(cards.nth(4)).toHaveAttribute('aria-pressed', 'true')
  await page
    .getByRole('group', { name: 'Kategorie ukázek' })
    .getByRole('button', { name: 'Příroda a rizika' })
    .click()
  await expect(page.locator('.series-demo__item')).toHaveCount(1)
  await expect(page.locator('.series-demo__item')).toContainText('Řeky a záplavové zóny')
  await page.screenshot({ path: '/tmp/hpk-landing-real.png' })
})

test('damaged stored artifacts cannot blank the application', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.addInitScript(() => {
    localStorage.setItem(
      'chat_sessions:123',
      JSON.stringify([
        {
          id: 'damaged-session',
          createdAt: Date.now(),
          updatedAt: Date.now(),
          activeId: null,
          messages: [
            {
              id: 'damaged-answer',
              role: 'assistant',
              answer: {
                text: 'Dřívější odpověď zůstane čitelná.',
                sample: false,
                artifacts: [{}],
              },
            },
          ],
        },
      ]),
    )
  })
  await authenticate(page)
  await expect(page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })).toBeVisible()
  await expect(page.locator('.markdown')).toContainText('Dřívější odpověď zůstane čitelná.')
  expect(errors).toEqual([])
})

test('invalid server JSON becomes a recoverable error instead of a blank page', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/api/chat/ask', (route) =>
    route.fulfill({ json: { text: 123, artifacts: [null] } }),
  )
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('Ověř odpověď')
  await input.press('Enter')
  await expect(page.getByRole('alert')).toContainText('Server vrátil neplatnou odpověď')
  await expect(input).toBeEnabled()
  expect(errors).toEqual([])
})

test('long Markdown and code remain contained on a narrow screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/chat/ask', (route) =>
    route.fulfill({
      json: {
        text: 'Dlouhý údaj: ' + 'X'.repeat(5000) + '\n\n```text\n' + 'Y'.repeat(1000) + '\n```',
        sample: false,
      },
    }),
  )
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('Dlouhý údaj')
  await input.press('Enter')
  await expect(page.locator('.markdown')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(input).toBeVisible()
})

test('storage quota failure is visible and does not discard the current conversation', async ({
  page,
}) => {
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem
    Storage.prototype.setItem = function (key, value) {
      if (key.startsWith('chat_sessions:'))
        throw new DOMException('Quota exceeded', 'QuotaExceededError')
      return original.call(this, key, value)
    }
  })
  await page.route('**/api/chat/ask', (route) =>
    route.fulfill({ json: { text: 'Odpověď zůstává dostupná.', sample: false } }),
  )
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('Ulož konverzaci')
  await input.press('Enter')
  await expect(page.locator('.markdown')).toContainText('Odpověď zůstává dostupná.')
  await expect(page.locator('.history-storage-warning')).toContainText(
    'Historii se nepodařilo uložit',
  )
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Stáhnout konverzaci', exact: true }).click()
  expect((await pending).suggestedFilename()).toBe('kartogram-konverzace.md')
  await expect(input).toBeEnabled()
})
