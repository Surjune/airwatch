import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
// vitest/config re-exports Vite's defineConfig with the `test` key typed; the
// plain vite export does not know about it.
import { defineConfig } from 'vitest/config';

/** Backend origin during development. The API is versioned under /v1. */
const LOCAL_API = 'http://localhost:8000';

/**
 * The deployed API, for `npm run dev:live`: a change can be looked at against
 * real data without a local database. Read-only screens only; nothing here
 * signs in.
 */
const LIVE_API = 'https://airwatch-cbe.duckdns.org';

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // Proxying in development keeps the browser same-origin, so the CORS
    // allowlist only has to be correct in deployed environments.
    proxy: { '/v1': { target: mode === 'live' ? LIVE_API : LOCAL_API, changeOrigin: true } },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
}));
