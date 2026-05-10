import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import Root from './Root'
import { SessionExpiredModal } from './components/SessionExpiredModal'
import { bootstrapAuth } from './lib/api/handshake'
import './index.css'

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('Root element #root not found')

const root = createRoot(rootEl)

bootstrapAuth()
  .then(() => {
    root.render(
      <StrictMode>
        <Root />
      </StrictMode>
    )
  })
  .catch(() => {
    root.render(
      <StrictMode>
        <SessionExpiredModal />
      </StrictMode>
    )
  })
