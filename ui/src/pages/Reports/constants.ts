import type { ReportDraftSection, ReportFormat, TestingType } from '@/lib/types'

export const SECTION_LABELS: Record<ReportDraftSection, string> = {
  'executive-summary': 'Executive Summary',
  'risk-level': 'Risk Level Assessment',
  'critical-issues': 'Critical Issues',
  'improvement-points': 'Improvement Points',
  'scope-and-methodology': 'Scope & Methodology',
  'general-recommendations': 'General Recommendations',
}

export const SECTION_ORDER: ReportDraftSection[] = [
  'executive-summary',
  'risk-level',
  'critical-issues',
  'improvement-points',
  'scope-and-methodology',
  'general-recommendations',
]

export const FORMAT_OPTIONS: { value: ReportFormat; label: string; requiresDrafts: boolean }[] = [
  { value: 'pdf', label: 'PDF', requiresDrafts: true },
  { value: 'markdown', label: 'Markdown', requiresDrafts: false },
  { value: 'html', label: 'HTML', requiresDrafts: false },
  { value: 'json', label: 'JSON', requiresDrafts: false },
]

export const TESTING_TYPE_OPTIONS: { value: TestingType; label: string }[] = [
  { value: 'white_box', label: 'White Box' },
  { value: 'grey_box', label: 'Grey Box' },
  { value: 'black_box', label: 'Black Box' },
]
