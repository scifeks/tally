# CI Gates — tally-ui

All gates must pass before merging to `main`.

## Local validation

```sh
cd ui
npm run validate        # type-check + lint + format:check + test:run
npm run test:coverage   # coverage report (lcov + text)
```

## Gates

| Gate | Command | Pass condition |
|------|---------|----------------|
| Type-check | `npm run type-check` | Zero TypeScript errors |
| Lint | `npm run lint` | Zero ESLint errors or warnings |
| Format | `npm run format:check` | All files match Prettier style |
| Tests | `npm run test:run` | All tests pass |
| Coverage | `npm run test:coverage` | Every tested file ≥ 60% line coverage |

## Pre-commit enforcement

Staged `ts/tsx/json/css` files under `ui/src/` are automatically linted and
formatted via `lint-staged` when you run `git commit` from the repo root.
The hook is defined in `.pre-commit-config.yaml` (`ui-lint-staged`).

## Adding tests

- Unit tests: `src/**/__tests__/*.test.ts(x)` or `src/**/*.test.ts(x)`
- Setup file: `src/test/setup.ts`
- MSW handlers: `src/test/handlers/index.ts`
- Coverage exclusions: `src/test/**`, `**/*.d.ts`, `**/*.config.*`
