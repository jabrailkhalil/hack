import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (outgoing, incoming) => {
            // Preserve the API's same-origin rule when the local dev server proxies requests.
            if (
              incoming.headers.origin &&
              new URL(incoming.headers.origin).host === incoming.headers.host
            )
              outgoing.setHeader("Origin", "http://localhost:8080");
          });
        },
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          charts: [
            "echarts/core",
            "echarts/charts",
            "echarts/components",
            "echarts/renderers",
          ],
          map: ["leaflet"],
        },
      },
    },
  },
});
