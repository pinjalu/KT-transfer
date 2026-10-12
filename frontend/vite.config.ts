import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The built bundle is served by FastAPI from pka/static/ui, under the existing /static mount.
// The application sends script-src 'self' and style-src 'self', so nothing may be inlined:
// assetsInlineLimit 0 keeps every asset a separate file with its own URL.
const API = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  base: '/static/ui/',
  build: {
    outDir: '../pka/static/ui',
    emptyOutDir: true,
    assetsInlineLimit: 0,
    modulePreload: { polyfill: false },
  },
  server: {
    port: 5173,
    proxy: {
      // The backend refuses a request whose Origin is not its own base URL. Behind this proxy
      // the browser's origin is the dev server, so the header is rewritten to the backend's own
      // before it arrives. Nothing in pka/web.py is relaxed to make development work.
      '/api': {
        target: API,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('origin', API)
            proxyReq.setHeader('x-pka-request', '1')
          })
        },
      },
    },
  },
})
