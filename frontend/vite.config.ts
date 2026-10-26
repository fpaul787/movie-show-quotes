import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/static/quotes/homepage/",
  build: {
    outDir: "../quotes/static/quotes/homepage",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "homepage.js",
        assetFileNames: "homepage.[ext]",
      },
    },
  },
});