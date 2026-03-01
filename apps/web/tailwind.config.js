/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ["var(--font-playfair)", "serif"],
        sans: ["var(--font-outfit)", "sans-serif"],
      },
      colors: {
        background: "var(--bg-base)",
        sidebar: "var(--bg-sidebar)",
        surface: "var(--bg-surface)",
        elevated: "var(--bg-elevated)",
        userMessage: "var(--bg-user-message)",
        input: "var(--bg-input)",
        foreground: "var(--text-primary)",
        secondary: "var(--text-secondary)",
        muted: "var(--text-muted)",
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          light: "var(--accent-light)",
          subtle: "var(--accent-subtle)",
        },
        border: "var(--border)",
        borderFocus: "var(--border-focus)",
        success: "var(--success)",
        warning: "var(--warning)",
        error: "var(--error)",
        mode: {
          solo: "var(--mode-solo)",
          team: "var(--mode-team)",
          auto: "var(--mode-auto)",
        }
      }
    }
  },
  plugins: []
};
