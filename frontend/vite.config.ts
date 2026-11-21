import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { archivePreview } from './archive-preview.mjs'

export default defineConfig(({ mode }) => ({
  base: mode === 'pages' ? (loadEnv(mode, '.', 'PAGES_BASE_PATH').PAGES_BASE_PATH || '/alphalens/').replace(/\/?$/, '/') : './',
  plugins: [react(), tailwindcss(), ...(mode === 'demo' ? [] : [archivePreview()])],
  server: {
    host: '127.0.0.1',
    fs: {
      deny: [
        '.env', '.env.*', '*.{crt,pem}', '**/.git/**', '**/.local-archive/**',
        '**/data/raw/**', '**/data/processed/posts.json', '**/data/processed/imports/**',
        '**/data/processed/media_manifest.json', '**/data/processed/post_analyses/**',
      ],
    },
    watch: { ignored: ['**/.local-archive/**'] },
  },
}))

