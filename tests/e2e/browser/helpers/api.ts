import { APIRequestContext } from "@playwright/test";
import { API_BASE } from "../fixtures/constants";

export class TallyApi {
  constructor(private request: APIRequestContext) {}

  async listProjects(): Promise<{ items: ProjectSummary[]; total: number }> {
    const res = await this.request.get(`${API_BASE}/projects`);
    return res.json();
  }

  async getProjectMeta(
    projectId: number
  ): Promise<{ repo_count: number; finding_count: number }> {
    const res = await this.request.get(
      `${API_BASE}/projects/${projectId}/meta`
    );
    return res.json();
  }

  async getRepositories(projectId: number): Promise<Repository[]> {
    const res = await this.request.get(
      `${API_BASE}/projects/${projectId}/repositories`
    );
    const body = await res.json();
    return body.items ?? body;
  }

  async getScanHistory(projectId: number): Promise<ScanRun[]> {
    const res = await this.request.get(
      `${API_BASE}/projects/${projectId}/scans`
    );
    const body = await res.json();
    return body.items ?? body;
  }

  async getFindings(
    projectId: number,
    params?: Record<string, string>
  ): Promise<{ items: Finding[]; total: number }> {
    const query = params
      ? "?" + new URLSearchParams(params).toString()
      : "";
    const res = await this.request.get(
      `${API_BASE}/projects/${projectId}/findings${query}`
    );
    return res.json();
  }

  async getToolCatalog(): Promise<ToolCatalogEntry[]> {
    const res = await this.request.get(`${API_BASE}/tools/catalog`);
    const body = await res.json();
    return body.items ?? body;
  }
}

interface ProjectSummary {
  id: number;
  project_name: string;
  abbreviation: string;
}

interface Repository {
  id: number;
  name: string;
  local_path: string;
}

interface ScanRun {
  id: number;
  status: string;
  findings_count: number;
}

interface Finding {
  id: number;
  title: string;
  severity: string;
  status: string;
  tool: string;
}

interface ToolCatalogEntry {
  name: string;
  domain: string;
  enabled: boolean;
}
