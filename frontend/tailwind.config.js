/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        graphite: "#090816",
        surface: "#101024",
        surface_raised: "#171738",
        surface_border: "#292750",
        titanium: "#9C9AB8",
        text_primary: "#F5F3FF",
        text_secondary: "#8D8AA8",
        emerald: "#34D399",
        forest: "#34D399", // Legacy semantic alias used by existing status and evidence components.
        vermillion: "#FB7185",
        amber: "#FBBF24",
        gold: "#FBBF24", // Legacy semantic alias used by existing evidence and audit components.
        cyan: "#67E8F9",
        violet: "#A78BFA",
        pink: "#F0ABFC",
      },
      fontFamily: {
        display: ["Manrope", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        ui: ["Inter", "Manrope", "ui-sans-serif", "system-ui", "sans-serif"],
        label: ["IBM Plex Mono", "JetBrains Mono", "ui-monospace", "monospace"],
      },
      maxWidth: { canvas: "1600px" },
      transitionDuration: { 250: "250ms", 400: "400ms" },
      boxShadow: {
        paper: "0 20px 70px rgba(0,0,0,.20)",
        raised: "0 14px 40px rgba(0,0,0,.32)",
      },
    },
  },
  plugins: [],
};
