export const API_PORT = 8181;
export const VITE_PORT = 3100;
export const BASE_URL = `http://127.0.0.1:${VITE_PORT}`;
export const API_BASE = `http://127.0.0.1:${VITE_PORT}/api/v1`;
export const API_DIRECT = `http://127.0.0.1:${API_PORT}/api/v1`;

export const HOME = process.env.HOME ?? "/home/justin";

export const TEST_REPOS = {
  dveca: {
    name: "DVEca",
    localPath: `${HOME}/code/dveca`,
    languages: ["PHP"],
    serviceTypes: ["api", "ui"],
    locationMode: "docker",
    containerName: "dveca-web-1",
    mountPoint: "/var/www/html/public",
    baseUrl: "http://127.0.0.1:8082",
    crawlEnabled: true,
  },
} as const;

export const DVECA_SCAN_TARGET_SERVICES = [
  {
    name: "sca-php",
    container_name: "dveca-scan-target-1",
    docker_path: "/scan-targets/php",
    languages: ["PHP"],
    type: ["library"],
  },
  {
    name: "sca-node",
    container_name: "dveca-scan-target-1",
    docker_path: "/scan-targets/node",
    languages: ["JavaScript"],
    type: ["library"],
  },
  {
    name: "sca-python",
    container_name: "dveca-scan-target-1",
    docker_path: "/scan-targets/python",
    languages: ["Python"],
    type: ["library"],
  },
] as const;

export function buildScaOverrides(repoId: number) {
  return [
    {
      toolName: "composer-audit",
      argsMode: "stock",
      type: "repo",
      location: "docker",
      scope: "service",
      repoId: repoId,
      serviceName: "sca-php",
      container: {
        name: "dveca-scan-target-1",
        toolPath: "/usr/local/bin/composer",
      },
    },
    {
      toolName: "npm-audit",
      argsMode: "stock",
      type: "repo",
      location: "docker",
      scope: "service",
      repoId: repoId,
      serviceName: "sca-node",
      container: {
        name: "dveca-scan-target-1",
        toolPath: "/usr/bin/npm",
      },
    },
    {
      toolName: "pip-audit",
      argsMode: "stock",
      type: "repo",
      location: "docker",
      scope: "service",
      repoId: repoId,
      serviceName: "sca-python",
      container: {
        name: "dveca-scan-target-1",
        toolPath: "/usr/bin/pip-audit",
      },
    },
  ];
}

export const TIMEOUTS = {
  default: 60_000,
  scan: 1_200_000,
  reportGeneration: 180_000,
  chatStream: 120_000,
  authSetup: 30_000,
} as const;

export const NAV_TABS = [
  "DASHBOARD",
  "FINDINGS",
  "URL LISTS",
  "SCANS",
  "TRIAGE",
  "REPORTS",
  "CHAT",
  "CONFIG",
] as const;

export const ROUTES = {
  dashboard: "/",
  findings: "/findings",
  urls: "/urls",
  scans: "/scans",
  triage: "/triage",
  reports: "/reports",
  chat: "/chat",
  config: "/config",
} as const;
