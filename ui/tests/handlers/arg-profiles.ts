import { http, HttpResponse } from 'msw'
import { errorEnvelope } from './_helpers'
import argProfilesEmpty from '../fixtures/arg-profiles/empty.json'
import argProfilesPopulated from '../fixtures/arg-profiles/populated.json'
import argProfilesByToolGitleaks from '../fixtures/arg-profiles/by-tool-gitleaks.json'
import argProfileFlagOnly from '../fixtures/arg-profiles/flag-only.json'
import argProfileStringOnly from '../fixtures/arg-profiles/string-only.json'
import argProfileFileOnly from '../fixtures/arg-profiles/file-only.json'
import argProfileDetailMixed from '../fixtures/arg-profiles/detail-mixed.json'

const ARG_PROFILE_DOWNLOAD_SAMPLE = `rules:
  - id: example-rule
    pattern: $X == $X
    message: tautology
    languages: [python]
    severity: WARNING
`

const ARG_PROFILE_NOT_FOUND_ID = '9999'
const ARG_PROFILE_IN_USE_ID = '3'
const ARG_PROFILE_UNIQUE_CONFLICT_NAME = 'verbose-only'

const DETAIL_BY_ID: Record<string, unknown> = {
  '1': argProfileFlagOnly,
  '2': argProfileStringOnly,
  '3': argProfileFileOnly,
  '4': argProfileDetailMixed,
}

export const argProfilesHandlers = [
  http.get('/api/v1/projects/:projectId/arg-profiles', ({ request }) => {
    const url = new URL(request.url)
    const toolName = url.searchParams.get('tool_name')
    if (toolName === 'gitleaks') return HttpResponse.json(argProfilesByToolGitleaks)
    if (toolName === 'unknown-tool') return HttpResponse.json(argProfilesEmpty)
    const totalRaw = (argProfilesPopulated as { total?: number }).total
    if (typeof totalRaw === 'number' && totalRaw === 0) {
      return HttpResponse.json(argProfilesEmpty)
    }
    return HttpResponse.json(argProfilesPopulated)
  }),
  http.get('/api/v1/projects/:projectId/arg-profiles/:profileId', ({ params }) => {
    if (params.profileId === ARG_PROFILE_NOT_FOUND_ID) {
      return errorEnvelope(404, 'NOT_FOUND', `Arg profile id=${params.profileId} not found`)
    }
    const detail = DETAIL_BY_ID[params.profileId as string]
    if (!detail) {
      return errorEnvelope(404, 'NOT_FOUND', `Arg profile id=${params.profileId} not found`)
    }
    return HttpResponse.json(detail)
  }),
  http.get('/api/v1/projects/:projectId/arg-profiles/:profileId/files/:argName', ({ params }) => {
    if (params.profileId === ARG_PROFILE_NOT_FOUND_ID) {
      return errorEnvelope(404, 'NOT_FOUND', `Arg profile id=${params.profileId} not found`)
    }
    return new HttpResponse(ARG_PROFILE_DOWNLOAD_SAMPLE, {
      status: 200,
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `inline; filename="${params.argName}"`,
      },
    })
  }),
  http.post('/api/v1/projects/:projectId/arg-profiles', async ({ request }) => {
    const form = await request.formData().catch(() => null)
    const payloadRaw = form?.get('payload')
    if (typeof payloadRaw !== 'string' || payloadRaw === '') {
      return errorEnvelope(422, 'VALIDATION_ERROR', 'payload form field is required')
    }
    let payload: { toolName?: string; name?: string; args?: Array<{ name: string; type: string }> }
    try {
      payload = JSON.parse(payloadRaw)
    } catch (exc) {
      return errorEnvelope(
        422,
        'VALIDATION_ERROR',
        `invalid JSON payload: ${(exc as Error).message}`
      )
    }
    if (payload.name === ARG_PROFILE_UNIQUE_CONFLICT_NAME) {
      return errorEnvelope(
        409,
        'CONFLICT',
        `profile '${payload.name}' already exists for tool '${payload.toolName}'`
      )
    }
    const fileArgs = (payload.args ?? []).filter(a => a.type === 'file')
    const missing = fileArgs.filter(a => !form?.has(a.name))
    if (missing.length > 0) {
      return errorEnvelope(
        422,
        'VALIDATION_ERROR',
        'Arg profile payload references files that were not uploaded',
        {
          fields: missing.map(a => ({
            field: a.name,
            issue: 'missing upload field',
          })),
        }
      )
    }
    return HttpResponse.json(argProfileFlagOnly, { status: 201 })
  }),
  http.put('/api/v1/projects/:projectId/arg-profiles/:profileId', async ({ params }) => {
    if (params.profileId === ARG_PROFILE_NOT_FOUND_ID) {
      return errorEnvelope(404, 'NOT_FOUND', `tool_arg_profile id=${params.profileId} not found`)
    }
    const detail = DETAIL_BY_ID[params.profileId as string]
    if (!detail) {
      return errorEnvelope(404, 'NOT_FOUND', `tool_arg_profile id=${params.profileId} not found`)
    }
    return HttpResponse.json(detail)
  }),
  http.delete('/api/v1/projects/:projectId/arg-profiles/:profileId', ({ params }) => {
    if (params.profileId === ARG_PROFILE_NOT_FOUND_ID) {
      return errorEnvelope(404, 'NOT_FOUND', `Arg profile id=${params.profileId} not found`)
    }
    if (params.profileId === ARG_PROFILE_IN_USE_ID) {
      return errorEnvelope(409, 'IN_USE', 'Arg profile is referenced by one or more saved scans', {
        savedScanIds: [2],
        savedScanNames: ['Full SAST + SCA'],
      })
    }
    return new HttpResponse(null, { status: 204 })
  }),
]
