import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: "var(--paper)",
        "paper-2": "var(--paper-2)",
        "paper-3": "var(--paper-3)",
        rule: "var(--rule)",
        ink: "var(--ink)",
        "ink-muted": "var(--ink-muted)",
        stamp: "var(--stamp)",
        "stamp-deep": "var(--stamp-deep)",
        recovered: "var(--recovered)",
        "at-risk": "var(--at-risk)",
        blocked: "var(--blocked)",
      },
      fontFamily: {
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["var(--font-sans)", "-apple-system", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
