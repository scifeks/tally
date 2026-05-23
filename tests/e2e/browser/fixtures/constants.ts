export const API_PORT = 8181;
export const VITE_PORT = 3100;
export const BASE_URL = `http://127.0.0.1:${VITE_PORT}`;
export const API_BASE = `http://127.0.0.1:${VITE_PORT}/api/v1`;

export const REPOS_DIR = `${process.env.HOME}/code/repos`;

export const TEST_REPOS = {
  dvwa: {
    name: "DVWA",
    localPath: `${REPOS_DIR}/DVWA`,
    languages: ["PHP", "Python", "JavaScript"],
    containerName: "dvwa-dvwa-1",
    baseUrl: "http://localhost:4280",
    dockerPath: "/var/www/html",
    crawlEnabled: true,
  },
  dvpwa: {
    name: "DVPWA",
    localPath: `${REPOS_DIR}/DVPWA`,
    languages: ["Python", "JavaScript"],
    containerName: "dvpwa-sqli-1",
    baseUrl: "http://localhost:8080",
    dockerPath: "/app",
    crawlEnabled: true,
  },
  phpGoof: {
    name: "php-goof",
    localPath: `${REPOS_DIR}/php-goof`,
    languages: ["PHP"],
    containerName: "php-goof-app-1",
    baseUrl: "http://127.0.0.1:8000/",
    dockerPath: "/app",
    crawlEnabled: true,
  },
  dveca: {
    name: "DVEca",
    localPath: `${REPOS_DIR}/DVEca`,
    languages: ["PHP"],
    containerName: "",
    baseUrl: "http://127.0.0.1:8082",
    dockerPath: "/var/www/html/public",
    crawlEnabled: true,
  },
} as const;

export const TIMEOUTS = {
  default: 60_000,
  scan: 300_000,
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
