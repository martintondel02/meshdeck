import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  server: {
    // dev flow: `pnpm dev` here + `python -m meshdeck` in the repo root.
    // The token query param is forwarded to the backend unchanged.
    proxy: {
      "/api": { target: "http://127.0.0.1:8570", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8570", ws: true },
    },
  },
  test: {
    // The renderer is pure string work; no DOM is needed.
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
