import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from 'react-hot-toast'

async function bootstrap() {
  const [{ default: App }] = await Promise.all([
    import('./App.tsx'),
    import('./index.css'),
  ])

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <Toaster
        position="top-center"
        toastOptions={{
          style: {
            borderRadius: '8px',
            background: '#333',
            color: '#fff',
          },
        }}
      />
      <App />
    </StrictMode>,
  )
}

bootstrap().catch((error) => {
  console.error('[main] failed to bootstrap app:', error)
})
