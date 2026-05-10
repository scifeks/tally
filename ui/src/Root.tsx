import { useEffect, useState } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { ActiveProjectGuard } from './components/ActiveProjectGuard'
import { SessionExpiredModal } from './components/SessionExpiredModal'
import { ApiError, subscribeSessionExpired } from './lib/api/client'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          return false
        }
        return failureCount < 3
      },
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
