import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Porta de dev 13100 (nao a predefinida). A API corre em 18100 (ver README).
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 13100, strictPort: true },
  preview: { host: "127.0.0.1", port: 13100, strictPort: true },
});
