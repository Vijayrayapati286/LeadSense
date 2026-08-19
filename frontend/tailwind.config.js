/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        sidebar: {
          DEFAULT: '#1e293b',
          hover: '#334155',
          active: '#3b82f6',
        },
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'spin-slow': 'spin 2s linear infinite',
        'meet-left': 'meetLeft 0.7s ease-out forwards',
        'meet-right': 'meetRight 0.7s ease-out forwards',
        'scan-pulse': 'scanPulse 1.2s ease-in-out infinite',
        'field-in': 'fieldIn 0.35s ease-out forwards',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideIn: {
          '0%': { transform: 'translateX(-10px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        meetLeft: {
          '0%': { transform: 'translateX(0)', opacity: '0.85' },
          '100%': { transform: 'translateX(12%)', opacity: '1' },
        },
        meetRight: {
          '0%': { transform: 'translateX(0)', opacity: '0.85' },
          '100%': { transform: 'translateX(-12%)', opacity: '1' },
        },
        scanPulse: {
          '0%, 100%': { opacity: '0.35' },
          '50%': { opacity: '1' },
        },
        fieldIn: {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
};
