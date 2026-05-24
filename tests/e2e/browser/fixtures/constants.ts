export const API_PORT = 8181;
export const VITE_PORT = 3100;
export const BASE_URL = `http://127.0.0.1:${VITE_PORT}`;
export const API_BASE = `http://127.0.0.1:${VITE_PORT}/api/v1`;
export const API_DIRECT = `http://127.0.0.1:${API_PORT}/api/v1`;

export const HOME = process.env.HOME ?? "/home/justin";
export const REPOS_DIR = `${HOME}/code/repos`;

export const TEST_REPOS = {
  dvwa: {
    name: "DVWA",
    localPath: `${REPOS_DIR}/php/DVWA`,
    languages: ["PHP", "Python", "JavaScript"],
    serviceTypes: ["api", "ui"],
    locationMode: "docker",
    containerName: "dvwa-dvwa-1",
    mountPoint: "/var/www/html",
    baseUrl: "http://localhost:4280",
    crawlEnabled: true,
  },
  dvpwa: {
    name: "DVPWA",
    localPath: `${REPOS_DIR}/python/dvpwa`,
    languages: ["Python", "JavaScript"],
    serviceTypes: ["api"],
    locationMode: "docker",
    containerName: "dvpwa-sqli-1",
    mountPoint: "/app",
    baseUrl: "http://localhost:8080",
    crawlEnabled: true,
  },
  phpGoof: {
    name: "php-goof",
    localPath: `${REPOS_DIR}/php/php-goof`,
    languages: ["PHP"],
    serviceTypes: ["api"],
    locationMode: "docker",
    containerName: "php-goof-app-1",
    mountPoint: "/app",
    baseUrl: "http://127.0.0.1:8000/",
    crawlEnabled: true,
  },
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

export const TIMEOUTS = {
  default: 60_000,
  scan: 600_000,
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
