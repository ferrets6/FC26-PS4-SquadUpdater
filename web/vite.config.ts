import { defineConfig } from "vite";

export default defineConfig({
  // When running `netlify dev`, Netlify CLI starts both Vite (port 5173)
  // and the edge-function runtime (port 8888). The CLI auto-proxies /api/*
  // from the Vite dev server to the edge-function runtime, so no manual
  // proxy configuration is needed here for local development.
  build: {
    // Generate source maps for easier debugging
    sourcemap: true,
  },
});
