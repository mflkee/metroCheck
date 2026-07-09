import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#12212b",
        mist: "#eef2f4",
        steel: "#5f707b",
        line: "#d3dde2",
        signal: {
          info: "#2d6f8e",
          warn: "#b87428",
          danger: "#ad4242",
          ok: "#2f6b48",
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', '"Segoe UI"', "sans-serif"],
      },
      boxShadow: {
        panel: "0 18px 44px rgba(10, 28, 43, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
