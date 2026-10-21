import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}", "vite.config.ts", "vitest.config.ts"],
    rules: {
      "spaced-comment": "off",
    },
  },
  {
    ignores: ["dist/**"],
  },
);
