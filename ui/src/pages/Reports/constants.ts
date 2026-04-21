import type { ReportDraftSection, ReportFormat, TestingType } from "@/lib/types"

export const SECTION_LABELS: Record<ReportDraftSection, string> = {
  executive_summary: "Executive Summary",
  risk_level: "Risk Level Assessment",
  critical_issues: "Critical Issues",
  improvement_points: "Improvement Points",
  scope_methodology: "Scope & Methodology",
  general_recommendations: "General Recommendations",
}

export const SECTION_ORDER: ReportDraftSection[] = [
  "executive_summary",
  "risk_level",
  "critical_issues",
  "improvement_points",
  "scope_methodology",
  "general_recommendations",
]

export const FORMAT_OPTIONS: { value: ReportFormat; label: string; requiresDrafts: boolean }[] = [
  { value: "pdf", label: "PDF", requiresDrafts: true },
  { value: "markdown", label: "Markdown", requiresDrafts: false },
  { value: "html", label: "HTML", requiresDrafts: false },
  { value: "json", label: "JSON", requiresDrafts: false },
]

export const TESTING_TYPE_OPTIONS: { value: TestingType; label: string }[] = [
  { value: "white_box", label: "White Box" },
  { value: "grey_box", label: "Grey Box" },
  { value: "black_box", label: "Black Box" },
]
