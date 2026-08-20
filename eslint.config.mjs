import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXText[value=/\\S/][value=/[A-Za-z\\u4e00-\\u9fff\\u3040-\\u30ff]/]",
          message: "Avoid hardcoded UI text in JSX. Use i18n t(\"...\") keys.",
        },
        {
          selector: "JSXAttribute[name.name=/^(placeholder|aria-label|title)$/] > Literal[value=/[A-Za-z\\u4e00-\\u9fff\\u3040-\\u30ff]/]",
          message: "Avoid hardcoded attribute copy. Use i18n t(\"...\") values.",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
