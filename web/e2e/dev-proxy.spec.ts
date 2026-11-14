import { test, expect } from '@playwright/test'
import { createServer as createHttpServer } from 'node:http'
import { createServer as createViteServer } from 'vite'

test('standalone Vite forwards registration and login and explains unavailable backend', async () => {
  const requests: string[] = []
  const upstream = createHttpServer((request, response) => {
    requests.push(`${request.method} ${request.url}`)
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify({ forwarded: true }))
  })
  await new Promise<void>((resolve) => upstream.listen(0, '127.0.0.1', resolve))
  const address = upstream.address()
  if (!address || typeof address === 'string') throw new Error('No upstream port')
  const previousPort = process.env.HTTP_PORT
  process.env.HTTP_PORT = String(address.port)
  let vite: Awaited<ReturnType<typeof createViteServer>> | undefined
  try {
    vite = await createViteServer({
      configFile: 'vite.config.ts',
      server: { host: '127.0.0.1', port: 0, strictPort: false },
    })
    await vite.listen()
    const url = vite.resolvedUrls!.local[0]
    for (const path of ['api/users/', 'api/auth/login']) {
      const response = await fetch(new URL(path, url), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'proxy-fixture' }),
      })
      expect(response.status).toBe(200)
      expect(await response.json()).toEqual({ forwarded: true })
    }
    expect(requests).toEqual(['POST /api/users/', 'POST /api/auth/login'])
    upstream.closeAllConnections()
    await new Promise<void>((resolve) => upstream.close(() => resolve()))
    const unavailable = await fetch(new URL('api/auth/login', url), { method: 'POST' })
    expect(unavailable.status).toBe(503)
    expect((await unavailable.json()).detail).toContain('Backend není dostupný')
  } finally {
    await vite?.close()
    upstream.closeAllConnections()
    upstream.close()
    if (previousPort === undefined) delete process.env.HTTP_PORT
    else process.env.HTTP_PORT = previousPort
  }
})

test('a delayed 401 cannot log out a newer session', async ({ page }) => {
  const vite = await createViteServer({
    configFile: 'vite.config.ts',
    server: { host: '127.0.0.1', port: 0, strictPort: false },
  })
  try {
    await vite.listen()
    const url = vite.resolvedUrls!.local[0]
    await page.route(url, (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: '<!doctype html><title>API client audit</title>',
      }),
    )
    await page.goto(url)
    let intercept: (route: import('@playwright/test').Route) => void
    const intercepted = new Promise<import('@playwright/test').Route>((resolve) => {
      intercept = resolve
    })
    await page.route('**/api/audit-stale', (route) => intercept(route))
    await page.evaluate(async () => {
      const client = await import('/src/api/client.ts')
      localStorage.setItem('auth_token', 'old-session-fixture')
      const state = { pending: client.apiFetch('/audit-stale').catch(() => null), unauthorized: 0 }
      window.addEventListener(client.UNAUTHORIZED_EVENT, () => state.unauthorized++)
      Object.assign(window, { auditClient: state })
    })
    const route = await intercepted
    await page.evaluate(() => localStorage.setItem('auth_token', 'new-session-fixture'))
    await route.fulfill({ status: 401, json: { detail: 'expired' } })
    const state = await page.evaluate(async () => {
      const state = (
        window as unknown as { auditClient: { pending: Promise<unknown>; unauthorized: number } }
      ).auditClient
      await state.pending
      return { token: localStorage.getItem('auth_token'), unauthorized: state.unauthorized }
    })
    expect(state).toEqual({ token: 'new-session-fixture', unauthorized: 0 })
    await page.route('**/api/audit-current', (route) =>
      route.fulfill({ status: 401, json: { detail: 'expired' } }),
    )
    const current = await page.evaluate(async () => {
      const { apiFetch } = await import('/src/api/client.ts')
      await apiFetch('/audit-current').catch(() => null)
      return localStorage.getItem('auth_token')
    })
    expect(current).toBeNull()
  } finally {
    await vite.close()
  }
})
