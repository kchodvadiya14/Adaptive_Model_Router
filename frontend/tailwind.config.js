/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Primary / accent
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
        },
        // Semantic status colors
        success: {
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
        },
        warning: {
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
        },
        danger: {
          300: '#fda4af',
          400: '#fb7185',
          500: '#f43f5e',
          600: '#e11d48',
          700: '#be123c',
        },
        info: {
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
        },
        // Background/surface hierarchy (page -> panel -> card -> raised)
        surface: {
          0: '#070a10',
          1: '#0d1220',
          2: '#121a2c',
          3: '#1a2338',
        },
        // Borders
        line: {
          DEFAULT: '#1f2740',
          subtle: '#161c2e',
          strong: '#2c3654',
        },
        // Text hierarchy
        ink: {
          primary: '#f4f6fb',
          secondary: '#9aa4bd',
          muted: '#707b96',
          disabled: '#4b5468',
        },
        // Modal/overlay backdrop
        overlay: 'rgba(4, 7, 15, 0.72)',
      },
      borderRadius: {
        card: '0.75rem',
        control: '0.5rem',
      },
      boxShadow: {
        card: '0 1px 2px 0 rgba(0,0,0,0.5), 0 1px 0 0 rgba(255,255,255,0.02) inset',
        modal: '0 20px 40px -8px rgba(0,0,0,0.6)',
      },
    },
  },
  plugins: [],
}
