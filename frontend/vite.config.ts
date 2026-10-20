import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import { fileURLToPath } from "node:url";

// The browser only ever talks to localhost:5173. The dev server forwards:
//   /auth, /users -> auth-service (keeps the path: the refresh cookie has Path=/auth)
//   /api/*        -> core-service (the /api prefix is removed)
// nginx/default.conf.template has the same three rules for Docker.
export default defineConfig(({ mode }) => {
  // Reads .env / .env.local too (AUTH_URL, CORE_URL); shell variables win.
  const env = { ...loadEnv(mode, process.cwd(), ""), ...process.env };
  const AUTH_URL = env.AUTH_URL ?? "http://127.0.0.1:8001";
  const CORE_URL = env.CORE_URL ?? "http://127.0.0.1:8002";
  const proxy = {
    "/auth": { target: AUTH_URL, changeOrigin: true },
    "/users": { target: AUTH_URL, changeOrigin: true },
    "/api": {
      target: CORE_URL,
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/api/, ""),
    },
  };

  return {
    plugins: [
      tanstackRouter({
        target: "react",
        autoCodeSplitting: true,
        routesDirectory: "./src/routes",
        generatedRouteTree: "./src/app/routeTree.gen.ts",
      }),
      react(),
      tailwindcss(),
    ],
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    server: { port: 5173, proxy },
    preview: { port: 4173, proxy },
  };
});
