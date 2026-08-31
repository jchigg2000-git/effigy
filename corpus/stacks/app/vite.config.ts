import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5300,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://localhost:8300",
        changeOrigin: false,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "happy-dom",
    setupFiles: ["src/test-setup.ts"],
  },
});
