// Canonical Praxion ESLint baseline (flat config) — the FRAMEWORK path for
// JS/TS (React / Vue / Next), where framework ESLint plugins have no Biome
// equivalent. Non-framework JS/TS projects use Biome (biome.json) instead; see
// the typescript-development skill's Biome-vs-ESLint decision rule.
//
// /onboard-project Phase 8e installs this as `eslint.config.mjs` (paired with
// prettierrc.json) for framework projects when no ESLint config exists yet —
// never overwriting an existing one. Satisfies the agent-readiness style
// criterion: an ESLint config = linter config; prettierrc.json = formatter.
//
// Required dev dependencies (onboarding prints the install line; it does not
// install them):
//   npm i -D eslint @eslint/js typescript-eslint prettier
// For a plain-JS project, drop the typescript-eslint import + spread.

import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    ignores: ["dist/", "build/", "node_modules/", ".next/", "coverage/"]
  }
);
