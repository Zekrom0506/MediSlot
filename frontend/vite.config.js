import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // In development the API runs separately; forward /api calls to it.
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
