/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'JetBrains Mono', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        DEFAULT: 'var(--radius)',
        lg: 'calc(var(--radius) + 0.25rem)',
        md: 'var(--radius)',
        sm: 'calc(var(--radius) - 0.125rem)',
      },
      colors: {
        background: 'hsl(var(--background) / <alpha-value>)',
        foreground: 'hsl(var(--foreground) / <alpha-value>)',
        card: {
          DEFAULT: 'hsl(var(--card) / <alpha-value>)',
          foreground: 'hsl(var(--card-foreground) / <alpha-value>)',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover) / <alpha-value>)',
          foreground: 'hsl(var(--popover-foreground) / <alpha-value>)',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary) / <alpha-value>)',
          foreground: 'hsl(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary) / <alpha-value>)',
          foreground: 'hsl(var(--secondary-foreground) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted) / <alpha-value>)',
          foreground: 'hsl(var(--muted-foreground) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent) / <alpha-value>)',
          foreground: 'hsl(var(--accent-foreground) / <alpha-value>)',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive) / <alpha-value>)',
          foreground: 'hsl(var(--destructive-foreground) / <alpha-value>)',
        },
        border: 'hsl(var(--border) / <alpha-value>)',
        ring: 'hsl(var(--ring) / <alpha-value>)',
        sidebar: {
          DEFAULT: 'hsl(var(--sidebar) / <alpha-value>)',
          foreground: 'hsl(var(--sidebar-foreground) / <alpha-value>)',
          accent: 'hsl(var(--sidebar-accent) / <alpha-value>)',
        },
        cs: {
          red: 'hsl(var(--cs-red) / <alpha-value>)',
          orange: 'hsl(var(--cs-orange) / <alpha-value>)',
          yellow: 'hsl(var(--cs-yellow) / <alpha-value>)',
          blue: 'hsl(var(--cs-blue) / <alpha-value>)',
          green: 'hsl(var(--cs-green) / <alpha-value>)',
          teal: 'hsl(var(--cs-teal) / <alpha-value>)',
          purple: 'hsl(var(--cs-purple) / <alpha-value>)',
          pink: 'hsl(var(--cs-pink) / <alpha-value>)',
          grey: 'hsl(var(--cs-grey) / <alpha-value>)',
        },
        graph: {
          panel: 'hsl(var(--graph-panel-bg) / <alpha-value>)',
          border: 'hsl(var(--graph-panel-border) / <alpha-value>)',
          text: 'hsl(var(--graph-panel-text) / <alpha-value>)',
          muted: 'hsl(var(--graph-panel-muted) / <alpha-value>)',
          control: 'hsl(var(--graph-control) / <alpha-value>)',
          'control-hover': 'hsl(var(--graph-control-hover) / <alpha-value>)',
          minimap: 'hsl(var(--graph-minimap) / <alpha-value>)',
        },
      },
    },
  },
  plugins: [],
}
