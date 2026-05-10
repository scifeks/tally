import { HttpResponse } from 'msw'

export function errorEnvelope(
  status: number,
  code: string,
  message: string,
  details: Record<string, unknown> = {}
) {
  return HttpResponse.json({ error: { code, message, details } }, { status })
}
