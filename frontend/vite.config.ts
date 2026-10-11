import { readFileSync } from "node:fs"
import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

/** The version shown by the shell's version badge; the fleet takes it from the build. */
function readAppVersion(): string {
  const manifest = JSON.parse(readFileSync(path.resolve(import.meta.dirname, "package.json"), "utf8")) as {
    version?: string
  }
  return manifest.version ?? "0.0.0"
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(readAppVersion()),
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
})
