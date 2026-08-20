// ESLint flat config.
//
// The plugins were already declared in package.json but there was no config
// file, so `eslint` could not run at all outside the webpack build. The rules
// below focus on mistakes that break the app at runtime — hook dependencies,
// unused bindings, missing keys — rather than formatting.
import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";

export default [
  {
    ignores: ["build/**", "node_modules/**", "plugins/**", "*.config.js", "eslint.config.mjs"],
  },
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.browser, ...globals.es2021, process: "readonly" },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: "detect" } },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...react.configs.flat.recommended.rules,
      ...reactHooks.configs.recommended.rules,

      // The project does not use PropTypes or TypeScript.
      "react/prop-types": "off",
      // React 17+ automatic JSX runtime.
      "react/react-in-jsx-scope": "off",
      "react/no-unescaped-entities": "off",

      // A missing hook dependency is a stale-closure bug waiting to happen.
      "react-hooks/exhaustive-deps": "warn",
      "react-hooks/rules-of-hooks": "error",

      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-console": ["warn", { allow: ["warn", "error"] }],
      eqeqeq: ["warn", "smart"],
    },
  },
  {
    // Vendored shadcn/ui primitives: library-specific DOM attributes (cmdk)
    // and re-exported helpers are expected here.
    files: ["src/components/ui/**/*.{js,jsx}", "src/hooks/**/*.js"],
    rules: {
      "react/no-unknown-property": "off",
      "no-unused-vars": "off",
      "react/display-name": "off",
    },
  },
];
