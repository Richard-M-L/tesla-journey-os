/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        tesla: {
          red: "#E82127",
          blue: "#3E6AE1",
          gray: {
            50: "#F5F5F5",
            100: "#E5E5E5",
            200: "#D0D0D0",
            300: "#A2A2A2",
            400: "#747474",
            500: "#5C5C5C",
            600: "#444444",
            700: "#333333",
            800: "#222222",
            900: "#111111",
          },
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};
