import { useEffect, useState } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { ActiveProjectGuard } from './components/ActiveProjectGuard'
import { SessionExpiredModal } from './components/SessionExpiredModal'
import { subscribeSessionExpired } from './lib/api/client'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

export default function Root() {
  const [sessionExpired, setSessionExpired] = useState(false)

  useEffect(() => {
    return subscribeSessionExpired(() => setSessionExpired(true))
  }, [])

  if (sessionExpired) {
    return <SessionExpiredModal />
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ActiveProjectGuard />
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
