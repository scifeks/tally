import { setupServer } from 'msw/node'

export const handlers: Parameters<typeof setupServer>[0][] = []

export const server = setupServer(...handlers)
