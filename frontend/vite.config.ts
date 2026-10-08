import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard runs on http://localhost:5180 (5173-5175 are used by other class projects).
// The backend (FastAPI, port 8000) allows this origin in its CORS settings.
export default defineConfig({
  plugins: [react()],
  server: { port: 5180, strictPort: true },
  preview: { port: 5180, strictPort: true },
});
