import { readFile } from 'node:fs/promises'

const base = new URL('./.local-archive/', import.meta.url)
const mediaRequest = /^\/data\/archive-media\/([a-f0-9]{64}\.(?:jpg|png|webp))$/
const imageTypes = { jpg: 'image/jpeg', png: 'image/png', webp: 'image/webp' }

/** @returns {import('vite').Plugin} */
export function archivePreview() {
  return {
    name: 'alphalens-archive-preview',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const pathname = req.url?.split('?')[0] ?? ''
        const dashboard = pathname === '/data/dashboard.json'
        const asset = mediaRequest.exec(pathname)
        if (!dashboard && !asset) return next()

        const address = req.socket.remoteAddress ?? ''
        const loopback = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(address)
        const host = /^(localhost|127\.0\.0\.1|\[::1\])(?::[0-9]+)?$/i.test(req.headers.host ?? '')
        if (!loopback || !host || req.headers['sec-fetch-site'] === 'cross-site') {
          if (dashboard) return next()
          res.statusCode = 404
          return res.end()
        }
        if (req.method !== 'GET' && req.method !== 'HEAD') return next()

        try {
          const snapshot = await readFile(new URL('dashboard.json', base))
          let bytes = snapshot
          let contentType = 'application/json; charset=utf-8'
          if (asset) {
            const media = JSON.parse(snapshot.toString('utf8')).posts
              .flatMap((post) => post.archive?.media ?? [])
            if (!media.some((item) => item.preview_path === pathname.slice(1))) {
              res.statusCode = 404
              return res.end()
            }
            bytes = await readFile(new URL('media/' + asset[1], base))
            const extension = asset[1].split('.').at(-1)
            contentType = imageTypes[extension]
          }
          res.setHeader('Content-Type', contentType)
          res.setHeader('Cache-Control', 'no-store')
          res.setHeader('Cross-Origin-Resource-Policy', 'same-origin')
          res.setHeader('X-Content-Type-Options', 'nosniff')
          return res.end(req.method === 'HEAD' ? undefined : bytes)
        } catch (error) {
          if (error.code === 'ENOENT') {
            if (dashboard) return next()
            res.statusCode = 404
            return res.end()
          }
          return next(error)
        }
      })
    },
  }
}

