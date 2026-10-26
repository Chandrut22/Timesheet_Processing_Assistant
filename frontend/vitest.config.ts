import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// Tests sit next to the file they cover (src/**/*.test.ts[x]) and run in Node. Component tests (*.test.tsx) start with
// `// @vitest-environment jsdom` to get a browser-like DOM.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: { include: ["src/**/*.test.{ts,tsx}"], environment: "node" },
});
