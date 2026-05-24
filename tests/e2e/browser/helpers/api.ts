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

  async patchRepository(
    projectId: number,
    repoId: number,
    data: Record<string, unknown>
  ): Promise<unknown> {
    const form = new URLSearchParams();
    form.set("payload", JSON.stringify(data));
    const res = await this.request.patch(
      `${API_BASE}/projects/${projectId}/repositories/${repoId}`,
      {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        data: form.toString(),
      }
    );
    return res.json();
  }

  async uploadEndpointFile(
    projectId: number,
    repoId: number,
    filePath: string
  ): Promise<unknown> {
    const fs = await import("fs");
    const path = await import("path");
    const buffer = fs.readFileSync(filePath);
    const filename = path.basename(filePath);
    const response = await this.request.patch(
      `${API_BASE}/projects/${projectId}/repositories/${repoId}`,
      {
        multipart: {
          endpoint_file: {
            name: filename,
            mimeType: "application/x-jsonl",
            buffer,
          },
        },
      }
    );
    return response.json();
  }

  async createToolOverride(
    projectId: number,
    override: Record<string, unknown>
  ): Promise<ToolOverrideResponse> {
    const res = await this.request.post(
      `${API_BASE}/projects/${projectId}/tools/overrides`,
      { data: override }
    );
    return res.json();
  }

  async listToolOverrides(
    projectId: number
  ): Promise<{ items: ToolOverrideResponse[]; total: number }> {
    const res = await this.request.get(
      `${API_BASE}/projects/${projectId}/tools/overrides`
    );
    return res.json();
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

interface ToolOverrideResponse {
  id: number;
  toolName: string;
  scope: string;
  repoId: number | null;
  serviceName: string | null;
  location: string;
}
