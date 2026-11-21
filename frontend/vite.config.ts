import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { archivePreview } from './archive-preview.mjs'
import { privateSnapshot, releaseSnapshot, validateResearchSnapshot } from './scripts/static-research.mjs'

export default defineConfig(({ command, isPreview, mode }) => {
  const previewSnapshot = loadEnv(mode, '.', 'ALPHALENS_PAGES_PREVIEW').ALPHALENS_PAGES_PREVIEW === '1'
  const researchBuild = mode !== 'demo' && (command === 'build' || isPreview)
  const snapshot = previewSnapshot ? privateSnapshot : releaseSnapshot

  return {
    base: mode === 'pages' ? (loadEnv(mode, '.', 'PAGES_BASE_PATH').PAGES_BASE_PATH || '/alphalens/').replace(/\/?$/, '/') : './',
    publicDir: researchBuild ? (previewSnapshot ? '.local-archive/pages-snapshot' : '../data/public-snapshot') : 'public',
    build: { outDir: researchBuild && previewSnapshot ? 'dist-local/pages-preview' : 'dist' },
    preview: { host: '127.0.0.1' },
    plugins: [
      react(), tailwindcss(),
      ...(mode === 'demo' || researchBuild ? [] : [archivePreview()]),
      ...(researchBuild && command === 'build' ? [{
        name: 'validate-static-research-snapshot',
        configResolved: () => validateResearchSnapshot(snapshot),
      }] : []),
    ],
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
  }
})
