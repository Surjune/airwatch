import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
// vitest/config re-exports Vite's defineConfig with the `test` key typed; the
// plain vite export does not know about it.
import { defineConfig } from 'vitest/config';

/** Backend origin during development. The API is versioned under /v1. */
const API_TARGET = 'http://localhost:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // Proxying in development keeps the browser same-origin, so the CORS
    // allowlist only has to be correct in deployed environments.
    proxy: { '/v1': { target: API_TARGET, changeOrigin: true } },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
});
