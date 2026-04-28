import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/vault': 'http://localhost:8000',
      '/review-assets': 'http://localhost:8000'
    }
  }
})
