import { expect, test } from '@playwright/test'
import { answer, authenticate } from './fixtures'

const statistics = {
  ...answer,
  rows: [
    { okres: 'CZ0323000000', value: 181200 },
    { okres: 'CZ0322000000', value: 22140 },
    { okres: 'CZ0326000000', value: 0 },
  ],
}
const inputName = 'Dotaz na data Plzeňského kraje'

test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/(tiles\.maps\.eox\.at|ags\.cuzk\.cz)\//, (route) => route.abort())
})

test('floating composer survives resize, collapse and shortcuts without losing a draft', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await authenticate(page)
  const input = page.getByRole('textbox', { name: inputName })
  await input.fill('Rozepsaný dotaz')
  const compact = (await input.boundingBox())!
  expect(compact.x).toBeGreaterThan((await page.locator('.panel').boundingBox())!.width)
  await page.getByRole('button', { name: 'Rozšířit konverzaci', exact: true }).click()
  await expect(page.getByRole('separator', { name: 'Šířka konverzace' })).toHaveAttribute(
    'aria-valuenow',
    '1080',
  )
  await expect
    .poll(async () => {
      const pane = (await page.locator('.panel').boundingBox())!
      const composer = (await page.locator('.composer-dock').boundingBox())!
      return Math.abs(composer.x + composer.width / 2 - (pane.x + pane.width / 2))
    })
    .toBeLessThan(2)
  await page.screenshot({ path: '/tmp/kartogram-workspace-expanded.png' })
  await page.getByRole('button', { name: 'Sbalit konverzaci' }).click()
  await expect(page.locator('.panel')).toHaveCount(0)
  await expect(input).toHaveCount(0)
  await page.keyboard.press('/')
  await expect(input).toBeFocused()
  await expect(input).toHaveValue('Rozepsaný dotaz')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Otevřít konverzaci' })).toBeVisible()
  await page.keyboard.press('Control+k')
  await expect(page.getByRole('textbox', { name: 'Hledat v konverzacích' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.locator('.panel')).toBeVisible()
  expect(errors).toEqual([])
})

test('legend separates missing data from zero; table sorts and selects districts', async ({
  page,
}) => {
  await page.route('**/api/chat/ask', (route) => route.fulfill({ json: statistics }))
  await authenticate(page)
  await expect(page.getByRole('region', { name: 'Legenda mapy' })).toHaveCount(0)
  await page.getByRole('textbox', { name: inputName }).fill('Obyvatelé')
  await page.getByRole('textbox', { name: inputName }).press('Enter')
  const legend = page.getByRole('region', { name: 'Legenda mapy' })
  await expect(legend).toContainText('3 ze 7 okresů')
  await expect(legend).toContainText('4 bez dat')
  await expect(legend).toContainText('Chybějící hodnoty nejsou nuly.')
  await expect(legend.locator('.map-legend__range > span').first()).toHaveText('0')
  const rows = page.locator('.answer__data tbody tr')
  await expect(rows.first()).toContainText('Plzeň-město')
  await page.getByRole('button', { name: 'Seřadit podle hodnoty' }).click()
  await expect(rows.first()).toContainText('Rokycany')
  await page.getByRole('button', { name: 'Seřadit podle okresu' }).click()
  await expect(rows.first()).toContainText('Klatovy')
  await page.locator('.okres-btn').filter({ hasText: 'Rokycany' }).click()
  await expect(legend.locator('.map-legend__selection')).toContainText('Rokycany')
  await expect(legend.locator('.map-legend__selection strong')).toHaveText('0')
  await page.getByRole('button', { name: 'Skrýt legendu' }).click()
  await expect(legend).toHaveCount(0)
  await page.getByRole('button', { name: 'Legenda', exact: true }).click()
  await expect(legend).toBeVisible()
  await page.getByRole('button', { name: 'Zrušit výběr okresu' }).click()
  await expect(legend.locator('.map-legend__selection')).toHaveCount(0)
  await page.screenshot({ path: '/tmp/kartogram-workspace-compact.png' })
})

test('history supports names, pins, full-text search, export and undo deletion', async ({
  page,
}) => {
  await page.route('**/api/chat/ask', (route) => route.fulfill({ json: statistics }))
  await authenticate(page)
  const input = page.getByRole('textbox', { name: inputName })
  await input.fill('První otázka')
  await input.press('Enter')
  await expect(page.locator('.markdown h2')).toBeVisible()
  await page.getByRole('button', { name: 'Historie konverzací', exact: true }).click()
  await page.getByRole('button', { name: /^Přejmenovat konverzaci:/ }).click()
  await page.getByRole('textbox', { name: 'Název konverzace' }).fill('Obyvatelé kraje')
  await page.getByRole('button', { name: 'Uložit název' }).click()
  await page
    .getByRole('button', { name: 'Připnout konverzaci: Obyvatelé kraje', exact: true })
    .click()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Nová konverzace', exact: true }).click()
  await input.fill('Druhá otázka')
  await input.press('Enter')
  await expect(page.locator('.markdown h2')).toBeVisible()
  await page.getByRole('button', { name: 'Historie konverzací', exact: true }).click()
  await expect(page.locator('.session').first()).toContainText('Obyvatelé kraje')
  const search = page.getByRole('textbox', { name: 'Hledat v konverzacích' })
  await search.fill('obyvatele kraje')
  await expect(page.locator('.session')).toHaveCount(1)
  await search.fill('naprosto neznamy dotaz')
  await expect(page.getByText('Této frázi neodpovídá žádná konverzace.')).toBeVisible()
  await search.fill('')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Stáhnout aktuální konverzaci (.md)' }).click()
  expect((await download).suggestedFilename()).toBe('kartogram-konverzace.md')
  await page
    .getByRole('button', { name: 'Smazat konverzaci: Obyvatelé kraje', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Přejmenovat konverzaci: Obyvatelé kraje' }),
  ).toHaveCount(0)
  await page.getByRole('button', { name: 'Vrátit', exact: true }).click()
  await page.getByRole('button', { name: 'Historie konverzací', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Odepnout konverzaci: Obyvatelé kraje', exact: true }),
  ).toBeVisible()
})

test('editing branches history and sends only the context before the edited question', async ({
  page,
}) => {
  const requests: { question: string; history: { role: string; text: string }[] }[] = []
  await page.route('**/api/chat/ask', async (route) => {
    requests.push(route.request().postDataJSON())
    await route.fulfill({ json: statistics })
  })
  await authenticate(page)
  const input = page.getByRole('textbox', { name: inputName })
  await input.fill('Původní otázka')
  await input.press('Enter')
  await expect(page.locator('.markdown h2')).toBeVisible()
  await input.fill('Rozpracovaný dotaz')
  await page.getByRole('button', { name: 'Upravit dotaz: Původní otázka', exact: true }).click()
  await expect(input).toHaveValue('Původní otázka')
  await page.getByRole('button', { name: 'Zrušit úpravu dotazu' }).click()
  await expect(input).toHaveValue('Rozpracovaný dotaz')
  await page.getByRole('button', { name: 'Upravit dotaz: Původní otázka', exact: true }).click()
  await input.fill('Opravená otázka')
  await input.press('Enter')
  await expect(page.locator('.markdown h2')).toBeVisible()
  expect(requests[1]).toEqual({ question: 'Opravená otázka', history: [] })
  await expect(page.locator('.msg--user')).toContainText('Opravená otázka')
  await page.getByRole('button', { name: 'Historie konverzací', exact: true }).click()
  await expect(page.locator('.session')).toHaveCount(2)
  await page.locator('.session__open').filter({ hasText: 'Původní otázka' }).click()
  await expect(page.locator('.msg--user')).toContainText('Původní otázka')
  await expect(input).toHaveValue('Rozpracovaný dotaz')
  await page.waitForTimeout(300)
  await page.reload()
  await expect(page.locator('.panel')).toBeVisible()
  await page.getByRole('button', { name: 'Historie konverzací', exact: true }).click()
  await page.locator('.session__open').filter({ hasText: 'Původní otázka' }).click()
  await expect(input).toHaveValue('Rozpracovaný dotaz')
})

test('mobile sheet can be resized by dragging and keyboard while composer remains reachable', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await authenticate(page)
  const handle = page.getByRole('separator', { name: 'Výška konverzace' })
  const initial = Number(await handle.getAttribute('aria-valuenow'))
  const box = (await handle.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 - 120, { steps: 12 })
  await page.mouse.up()
  await expect
    .poll(async () => Number(await handle.getAttribute('aria-valuenow')))
    .toBe(initial + 120)
  await handle.press('Home')
  await expect(handle).toHaveAttribute('aria-valuenow', '240')
  await handle.press('End')
  await expect(handle).toHaveAttribute('aria-valuenow', '668')
  const input = page.getByRole('textbox', { name: inputName })
  const bounds = (await input.boundingBox())!
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(844)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await input.fill('Rozepsáno na mobilu')
  await page.getByRole('button', { name: 'Sbalit konverzaci' }).click()
  await page.getByRole('button', { name: 'Otevřít konverzaci' }).click()
  await expect(input).toHaveValue('Rozepsáno na mobilu')
  await page.screenshot({ path: '/tmp/kartogram-workspace-mobile.png' })
})

test('reading earlier messages does not jump when a reply arrives', async ({ page }) => {
  const messages = Array.from({ length: 12 }, (_, index) => [
    { id: `u-${index}`, role: 'user', text: `Dřívější otázka ${index}` },
    {
      id: `a-${index}`,
      role: 'assistant',
      answer: {
        text: Array.from({ length: 6 }, () => 'Delší odpověď k dostupným údajům v kraji.').join(
          '\n\n',
        ),
        sample: false,
      },
    },
  ]).flat()
  await page.addInitScript((messages) => {
    localStorage.setItem(
      'chat_sessions:123',
      JSON.stringify([
        { id: 'reading', messages, activeId: null, createdAt: Date.now(), updatedAt: Date.now() },
      ]),
    )
  }, messages)
  let release: () => void = () => {}
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/chat/ask', async (route) => {
    await pending
    await route.fulfill({ json: statistics })
  })
  await authenticate(page)
  const input = page.getByRole('textbox', { name: inputName })
  await input.fill('Další otázka')
  await input.press('Enter')
  await expect(page.getByRole('button', { name: 'Zastavit čekání na odpověď' })).toBeVisible()
  const log = page.getByRole('log', { name: 'Zprávy konverzace' })
  await log.evaluate((element) => {
    element.scrollTop = 0
    element.dispatchEvent(new Event('scroll'))
  })
  release()
  await expect(page.locator('.markdown h2')).toBeAttached()
  expect(await log.evaluate((element) => element.scrollTop)).toBeLessThan(10)
  await page.getByRole('button', { name: 'Nové zprávy', exact: true }).click()
  await expect
    .poll(() =>
      log.evaluate((element) => element.scrollHeight - element.scrollTop - element.clientHeight),
    )
    .toBeLessThan(65)
})
