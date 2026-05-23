import { TEST_REPOS } from "../fixtures/constants";

export type RepoKey = keyof typeof TEST_REPOS;
export type RepoConfig = (typeof TEST_REPOS)[RepoKey];

export function getAllRepoConfigs(): RepoConfig[] {
  return Object.values(TEST_REPOS);
}

export function getRepoConfig(key: RepoKey): RepoConfig {
  return TEST_REPOS[key];
}
