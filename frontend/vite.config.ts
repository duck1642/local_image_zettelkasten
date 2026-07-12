import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte()],
  optimizeDeps: {
    exclude: ['@tauri-apps/api', '@tauri-apps/api/core', '@tauri-apps/api/dpi', '@tauri-apps/api/window']
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/vault': 'http://127.0.0.1:8000',
      '/review-assets': 'http://127.0.0.1:8000'
    }
  }
})
