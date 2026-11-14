import { expect, test } from '@playwright/test'
import { authenticate } from './fixtures'

const result = {
  result_id: 'verified-fixture',
  title: 'Obce a obyvatelé',
  view: 'bar',
  sample: false,
  columns: [
    { key: 'name', label: 'Obec', numeric: false, unit: '' },
    { key: 'value', label: 'Obyvatelé', numeric: true, unit: '' },
  ],
  rows: [
    { id: 'obec:1', name: 'Plzeň', value: 150 },
    { id: 'obec:2', name: 'Klatovy', value: 50 },
  ],
  features: [
    {
      type: 'Feature',
      id: 'obec:1',
      properties: { label: 'Plzeň' },
      geometry: { type: 'Point', coordinates: [13.37, 49.74] },
    },
  ],
  sources: [{ name: 'Ověřená fixture' }],
  note: 'Pouze dostupná data.',
}

test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/(tiles\.maps\.eox\.at|ags\.cuzk\.cz)\//, (route) => route.abort())
})

test('one verified result supports charts, sorting, CSV and a persistent map layer', async ({
  page,
}) => {
  await page.route('**/api/chat/ask', (route) =>
    route.fulfill({
      json: {
        text: 'Srovnání obcí.',
        sample: false,
        artifacts: [result, { ...result, view: 'map' }],
      },
    }),
  )
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('Porovnej obce')
  await input.press('Enter')
  await expect(page.locator('.result-view')).toHaveCount(1)
  await expect(page.getByRole('separator', { name: 'Šířka konverzace' })).toHaveAttribute(
    'aria-valuenow',
    '760',
  )
  await expect(page.locator('.result-view')).toBeFocused()
  await expect(page.getByRole('img', { name: /sloupcový graf/ })).toBeVisible()
  await page.getByRole('button', { name: 'Tabulka', exact: true }).click()
  await expect(page.locator('.result-view tbody tr').first()).toContainText('Plzeň')
  await page.getByRole('button', { name: 'Seřadit podle: Obyvatelé', exact: true }).click()
  await page.getByRole('button', { name: 'Seřadit podle: Obyvatelé', exact: true }).click()
  await expect(page.locator('.result-view tbody tr').first()).toContainText('Klatovy')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'CSV', exact: true }).click()
  expect((await download).suggestedFilename()).toBe('kartogram-vysledek.csv')
  await page.locator('.map-layers summary').click()
  const layer = page.getByRole('checkbox', { name: 'Obce a obyvatelé' })
  await expect(layer).toBeChecked()
  await layer.uncheck()
  await expect(layer).not.toBeChecked()
  await page.getByRole('button', { name: 'Zobrazit na mapě', exact: true }).click()
  await expect(layer).toBeChecked()
})

test('map appearance, cadastral overlay and result layers share one control panel', async ({
  page,
}) => {
  await authenticate(page)
  await page.locator('.map-layers summary').click()

  const ortho = page.getByRole('radio', { name: 'Ortofoto' })
  await ortho.check()
  await expect(ortho).toBeChecked()
  await expect(page.getByText(/detail zdroje do zoomu 19/)).toBeVisible()

  const cadastre = page.getByRole('checkbox', { name: 'Katastrální parcely · ČÚZK' })
  await expect(cadastre).not.toBeChecked()
  const opacity = page.getByRole('slider', { name: /Průhlednost katastru/ })
  await expect(opacity).toBeDisabled()
  await cadastre.check()
  await expect(opacity).toBeEnabled()
  await expect(page.getByText(/měřítku přibližně 1 : 15 000/)).toBeVisible()
})

test('new answers stay positioned at the start of the response', async ({ page }) => {
  const text = Array.from(
    { length: 24 },
    (_, index) =>
      `Odstavec ${index + 1}: Toto je delší odpověď, kterou si má uživatel pohodlně přečíst.`,
  ).join('\n\n')
  await page.route('**/api/chat/ask', (route) => route.fulfill({ json: { text } }))
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('Dlouhá odpověď')
  await input.press('Enter')

  const assistantMessage = page.locator('.msg--assistant').filter({ hasText: 'Odstavec 1' })
  await expect(assistantMessage).toBeVisible()
  await expect
    .poll(() =>
      page.locator('.panel__body').evaluate((list) => {
        const message = list.querySelector('.msg--assistant')
        return message
          ? message.getBoundingClientRect().top - list.getBoundingClientRect().top
          : Number.POSITIVE_INFINITY
      }),
    )
    .toBeLessThan(50)

  const position = await page.locator('.panel__body').evaluate((list) => {
    const message = list.querySelector('.msg--assistant')
    return {
      top: message
        ? message.getBoundingClientRect().top - list.getBoundingClientRect().top
        : Number.POSITIVE_INFINITY,
      remaining: list.scrollHeight - list.scrollTop - list.clientHeight,
    }
  })
  expect(position.top).toBeGreaterThanOrEqual(0)
  expect(position.top).toBeLessThan(50)
  expect(position.remaining).toBeGreaterThan(50)
})

test('agent can hide a layer from a prior answer and receives its verified reference', async ({
  page,
}) => {
  let call = 0
  await page.route('**/api/chat/ask', async (route) => {
    call++
    if (call === 1)
      await route.fulfill({
        json: {
          text: 'Vrstva načtená.',
          sample: false,
          result_ids: ['verified-hidden-route'],
          artifacts: [{ ...result, view: 'map' }],
        },
      })
    else {
      expect(route.request().postDataJSON().result_ids).toContain(result.result_id)
      expect(route.request().postDataJSON().result_ids).toContain('verified-hidden-route')
      await route.fulfill({
        json: {
          text: 'Vrstva skrytá.',
          sample: false,
          layer_actions: [{ result_id: result.result_id, visible: false }],
        },
      })
    }
  })
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('Ukaž obce')
  await input.press('Enter')
  await expect(page.locator('.result-view')).toBeVisible()
  await page.locator('.map-layers summary').click()
  const layer = page.getByRole('checkbox', { name: 'Obce a obyvatelé' })
  await expect(layer).toBeChecked()
  await expect(page.getByRole('separator', { name: 'Šířka konverzace' })).toHaveAttribute(
    'aria-valuenow',
    '330',
  )
  await input.fill('Skryj vrstvu obcí')
  await input.press('Enter')
  await expect(layer).not.toBeChecked()
})

test('parcel selection uses actual click coordinates and comparison requires two distinct hits', async ({
  page,
}) => {
  let count = 0
  await page.route('**/api/data/parcels/at-point?*', async (route) => {
    const url = new URL(route.request().url())
    expect(Number(url.searchParams.get('lat'))).toBeGreaterThan(48)
    expect(Number(url.searchParams.get('lon'))).toBeGreaterThan(12)
    count++
    await route.fulfill({
      json: {
        result: {
          ...result,
          result_id: `parcel-${count}`,
          title: 'Parcela z mapy',
          view: 'table',
          rows: [{ id: `parcela:${count}`, name: String(count), kod_ku: 722618, value: 100 }],
          features: [
            {
              type: 'Feature',
              id: `parcela:${count}`,
              properties: { label: `Parcela ${count}` },
              geometry: { type: 'Point', coordinates: [13.37 + count * 0.001, 49.74] },
            },
          ],
        },
      },
    })
  })
  await authenticate(page)
  await page.locator('.map-layers summary').click()
  await page.getByRole('button', { name: 'Porovnat parcely', exact: true }).click()
  const canvas = page.locator('.maplibregl-canvas')
  await expect(canvas).toBeVisible()
  await canvas.click({ position: { x: 1000, y: 450 }, force: true })
  await expect(page.getByRole('button', { name: 'Prověřit v chatu' })).toBeDisabled()
  await canvas.click({ position: { x: 1050, y: 500 }, force: true })
  await expect(page.getByRole('button', { name: 'Porovnat v chatu' })).toBeEnabled()
  await expect(page.locator('.map-layers__result input:checked')).toHaveCount(2)
  await canvas.click({ position: { x: 1060, y: 510 }, force: true })
  await expect(page.getByRole('button', { name: 'Prověřit v chatu' })).toBeDisabled()
  await expect(page.locator('.map-layers__result input:checked')).toHaveCount(1)
  await expect(page.locator('.workspace-map-label')).toHaveCount(1)
  await page.getByRole('button', { name: 'Vybrat parcelu', exact: true }).click()
  await expect(page.locator('.map-layers__result input:checked')).toHaveCount(0)
  await expect(page.locator('.workspace-map-label')).toHaveCount(0)
})

test('a new map answer replaces previous results instead of replaying history', async ({
  page,
}) => {
  let call = 0
  await page.route('**/api/chat/ask', (route) => {
    call++
    return route.fulfill({
      json: {
        text: 'Nový výsledek.',
        sample: false,
        artifacts: [
          { ...result, result_id: `result-${call}`, title: `Výsledek ${call}`, view: 'map' },
        ],
      },
    })
  })
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('První výsledek')
  await input.press('Enter')
  await expect(page.locator('.result-view')).toHaveCount(1)
  await page.locator('.map-layers summary').click()
  await expect(page.getByRole('checkbox', { name: 'Výsledek 1' })).toBeChecked()
  await input.fill('Druhý výsledek')
  await input.press('Enter')
  await expect(page.locator('.result-view')).toHaveCount(2)
  await expect(page.getByRole('checkbox', { name: 'Výsledek 1' })).toHaveCount(0)
  await expect(page.getByRole('checkbox', { name: 'Výsledek 2' })).toBeChecked()
  await page
    .locator('.result-view')
    .first()
    .getByRole('button', { name: 'Zobrazit na mapě' })
    .click()
  await expect(page.getByRole('checkbox', { name: 'Výsledek 1' })).toBeChecked()
  await expect(page.getByRole('checkbox', { name: 'Výsledek 2' })).not.toBeChecked()
  await page
    .locator('.result-view')
    .first()
    .getByRole('button', { name: 'Zobrazit na mapě' })
    .click()
  await expect(page.locator('.map-layers__result input:checked')).toHaveCount(1)
  await expect(page.locator('.workspace-map-label')).toHaveCount(1)
})

test('pie charts show verified shares of the selected subset and focus the chart', async ({
  page,
}) => {
  await page.route('**/api/chat/ask', (route) =>
    route.fulfill({
      json: {
        text: 'Podíly vybraných obcí.',
        sample: false,
        artifacts: [
          {
            ...result,
            view: 'pie',
            value_key: 'value',
            label_key: 'name',
            columns: result.columns.map((column) => ({ ...column, additive: column.numeric })),
          },
        ],
      },
    }),
  )
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('Koláč obyvatel')
  await input.press('Enter')
  await expect(page.getByRole('img', { name: /koláčový graf/ })).toBeVisible()
  await expect(page.locator('.result-view__pie li').first()).toContainText('75')
  await expect(page.locator('.result-view__pie')).toContainText('nikoliv z celého kraje')
  await expect(page.locator('.result-view')).toBeFocused()
  await page.getByRole('button', { name: 'Sloupce', exact: true }).click()
  await expect(page.getByRole('img', { name: /sloupcový graf/ })).toBeVisible()
})

test('CSV neutralizes a spreadsheet formula even after whitespace', async ({ page }) => {
  await page.route('**/api/chat/ask', (route) =>
    route.fulfill({
      json: {
        text: 'Export dat.',
        sample: false,
        artifacts: [{ ...result, rows: [{ id: 'a', name: ' \t=1+1', value: -3 }] }],
      },
    }),
  )
  await authenticate(page)
  const input = page.getByRole('textbox', { name: 'Dotaz na data Plzeňského kraje' })
  await input.fill('Export')
  await input.press('Enter')
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: 'CSV', exact: true }).click()
  const download = await pending
  const stream = await download.createReadStream()
  const chunks = []
  for await (const chunk of stream!) chunks.push(chunk)
  const csv = Buffer.concat(chunks).toString('utf8')
  expect(csv).toContain('"\' \t=1+1"')
  expect(csv).toContain('"-3"')
})
