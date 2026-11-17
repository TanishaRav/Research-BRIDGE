import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "node_modules/**",
    "backend/**",
    "coverage/**",
    "playwright-report/**",
    "test-results/**",
  ]),
  {
    rules: {
      // Synchronizing local editable state from freshly loaded server data, and toggling
      // loading flags inside async data-fetching effects, are intentional here. The React
      // Compiler rule flags the pattern but it is correct and cancellation-guarded.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
]);
