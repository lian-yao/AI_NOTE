import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import tailwindcss from '@tailwindcss/vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

function readAppVersion() {
  const fallbackVersion = '0.0.0'

  try {
    const tauriConfigPath = path.resolve(__dirname, 'src-tauri/tauri.conf.json')
    const tauriConfig = JSON.parse(fs.readFileSync(tauriConfigPath, 'utf-8')) as { version?: string }
    return tauriConfig.version || fallbackVersion
  }
  catch {
    return fallbackVersion
  }
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // 在 Docker 环境中，父目录可能没有 .env 文件，使用当前目录
  const envDir = process.env.DOCKER_BUILD ? __dirname : path.resolve(__dirname, '../')
  const env = loadEnv(mode, envDir)

  const apiBaseUrl = env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
  const port = parseInt(env.VITE_FRONTEND_PORT || '5173', 10)
  const appVersion = env.VITE_APP_VERSION || process.env.VITE_APP_VERSION || readAppVersion()

  return {
    base: './',
    define: {
      __APP_VERSION__: JSON.stringify(appVersion),
    },
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('vite/preload-helper') || id.includes('commonjsHelpers')) {
              return 'vendor'
            }
            if (!id.includes('node_modules')) return undefined
            if (/[\\/]node_modules[\\/](react|react-dom|react-router-dom)[\\/]/.test(id)) {
              return 'vendor'
            }
            if (/[\\/]node_modules[\\/](markmap-|@vscode[\\/]markdown-it-katex|katex|markdown-it)/.test(id)) {
              return 'markmap'
            }
            if (/[\\/]node_modules[\\/](react-markdown|react-syntax-highlighter|remark-|rehype-|mdast-|micromark|unified|vfile|hast-|unist-)/.test(id)) {
              return 'markdown'
            }
            return undefined
          },
        },
      },
    },
    server: {
      host: '0.0.0.0',
      port: port,
      allowedHosts: true, // 允许任意域名访问
      proxy: {
        '/api': {
          target: apiBaseUrl,
          changeOrigin: true,
          rewrite: path => path.replace(/^\/api/, '/api'),
        },
        '/static': {
          target: apiBaseUrl,
          changeOrigin: true,
          rewrite: path => path.replace(/^\/static/, '/static'),
        },
      },
    },
  }
})
