import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactPlugin from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import prettierConfig from 'eslint-config-prettier'
import prettierPlugin from 'eslint-plugin-prettier'

export default tseslint.config(
  { ignores: ['dist/', 'node_modules/', 'coverage/', '*.config.js'] },

  // Layer 1 — JS baseline
  js.configs.recommended,

  // Layer 2 — TypeScript
  ...tseslint.configs.recommended,

  // Layer 3 — React
  {
    ...reactPlugin.configs.flat.recommended,
    settings: { react: { version: 'detect' } },
  },
  reactPlugin.configs.flat['jsx-runtime'],
  {
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': 'warn',
    },
  },

  // Layer 4 — Accessibility
  jsxA11y.flatConfigs.recommended,

  // Layer 5 — Prettier (must be last — disables conflicting formatting rules)
  prettierConfig,

  // Explicit rule overrides
  {
    plugins: { prettier: prettierPlugin },
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-non-null-assertion': 'error',
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],

      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'error',
      'prefer-const': 'error',
      'no-var': 'error',

      'prettier/prettier': 'error',
    },
  },
)
