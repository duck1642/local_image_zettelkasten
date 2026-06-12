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
      '/api': 'http://localhost:8000',
      '/vault': 'http://localhost:8000',
      '/review-assets': 'http://localhost:8000'
    }
  }
})
