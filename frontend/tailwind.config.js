/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1E2A44",
        muted: "#5B6678",
        line: "#D9E0DD",
        canvas: "#F3F6F5",
        brand: {
          DEFAULT: "#0F7B5F",
          dark: "#0A5C47",
          soft: "#E3F2EC",
        },
        warn: { DEFAULT: "#B45309", soft: "#FDF3E4" },
        danger: { DEFAULT: "#B42318", soft: "#FDECEA" },
      },
      fontFamily: {
        sans: ["Figtree", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
