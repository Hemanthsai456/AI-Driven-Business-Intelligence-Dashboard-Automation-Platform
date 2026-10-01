/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        surface: {
          DEFAULT: 'var(--surface)',
          elevated: 'var(--surface-elevated)',
          muted: 'var(--surface-muted)',
        },
        border: {
          DEFAULT: 'var(--border)',
          strong: 'var(--border-strong)',
        },
        primary: {
          DEFAULT: 'var(--primary)',
          hover: 'var(--primary-hover)',
          soft: 'var(--primary-soft)',
          foreground: 'var(--primary-foreground)',
        },
        attention: {
          DEFAULT: 'var(--attention)',
          soft: 'var(--attention-soft)',
          foreground: 'var(--attention-foreground)',
        },
        error: {
          DEFAULT: 'var(--error)',
          soft: 'var(--error-soft)',
          foreground: 'var(--error-foreground)',
        },
        success: {
          DEFAULT: 'var(--success)',
          soft: 'var(--success-soft)',
          foreground: 'var(--success-foreground)',
        },
        muted: {
          DEFAULT: 'var(--surface-muted)',
          foreground: 'var(--muted-foreground)',
        },
        chart: {
          1: 'var(--chart-1)',
          2: 'var(--chart-2)',
          3: 'var(--chart-3)',
          4: 'var(--chart-4)',
          5: 'var(--chart-5)',
        },
      },
      borderRadius: {
        sm: '4px',
        DEFAULT: '6px',
        md: '8px',
        card: '10px',
        lg: '10px',
        xl: '12px',
      },
      fontSize: {
        '2xs': '0.6875rem',
      },
      boxShadow: {
        card: '0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        none: 'none',
      },
    },
  },
  plugins: [],
};
