import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/cases": "http://127.0.0.1:8000",
      "/redaction-types": "http://127.0.0.1:8000",
      "/activities": "http://127.0.0.1:8000",
      "/redactions": "http://127.0.0.1:8000",
    },
  },
});
