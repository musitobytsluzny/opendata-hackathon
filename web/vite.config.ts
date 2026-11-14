import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { fileURLToPath } from 'node:url'

const envDir = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const { HTTP_PORT = '8080' } = loadEnv(mode, envDir, 'HTTP_PORT')
  const backend: import('vite').ProxyOptions = {
    target: `http://127.0.0.1:${HTTP_PORT}`,
    changeOrigin: true,
    configure(proxy) {
      proxy.on('error', (_error, _request, response) => {
        if ('writeHead' in response && !response.headersSent) {
          response.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' })
          response.end(
            JSON.stringify({ detail: 'Backend není dostupný. Spusťte Docker Desktop a make up.' }),
          )
        }
      })
    },
  }
  return {
    envDir,
    plugins: [react()],
    server: { proxy: { '/api': backend, '/mcp': backend } },
  }
})
