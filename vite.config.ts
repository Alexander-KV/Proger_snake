import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
        configure(proxy) {
          proxy.on('proxyReq', (proxyRequest, request) => {
            proxyRequest.removeHeader('X-Snake-Client-IP')
            const address = request.socket.remoteAddress
            if (address) proxyRequest.setHeader('X-Snake-Client-IP', address)
          })
        },
      },
    },
  },
  plugins: [react(), tailwindcss()],
})
