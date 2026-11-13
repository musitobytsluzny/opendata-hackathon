import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  envDir: fileURLToPath(new URL('..', import.meta.url)),
  plugins: [react()],
})
