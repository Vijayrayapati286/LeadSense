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
          DEFAULT: '#0b1220',
          hover: 'rgba(255,255,255,0.06)',
          active: '#3b82f6',
        },
        surface: {
          DEFAULT: '#ffffff',
          muted: '#f8f9fb',
          inset: '#f1f5f9',
        },
        ink: {
          DEFAULT: '#0f172a',
          secondary: '#64748b',
          tertiary: '#94a3b8',
        },
        accent: {
          DEFAULT: '#2563eb',
          hover: '#1d4ed8',
        },
      },
      borderRadius: {
        sm: '8px',
        md: '12px',
        lg: '16px',
        xl: '24px',
      },
      boxShadow: {
        card: '0 6px 24px rgba(15, 23, 42, 0.04)',
        'card-hover': '0 8px 30px rgba(15, 23, 42, 0.08)',
        button: '0 4px 14px rgba(37, 99, 235, 0.2)',
      },
      fontSize: {
        display: ['1.75rem', { lineHeight: '2.25rem', fontWeight: '700' }],
        'body-sm': ['0.875rem', { lineHeight: '1.375rem' }],
        caption: ['0.6875rem', { lineHeight: '1rem', fontWeight: '600' }],
        micro: ['0.625rem', { lineHeight: '0.875rem', fontWeight: '600' }],
      },
      spacing: {
        section: '1.5rem',
        card: '1.25rem',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'spin-slow': 'spin 2s linear infinite',
        'meet-left': 'meetLeft 0.7s ease-out forwards',
        'meet-right': 'meetRight 0.7s ease-out forwards',
        'scan-pulse': 'scanPulse 1.2s ease-in-out infinite',
        'field-in': 'fieldIn 0.35s ease-out forwards',
        'slide-up-in': 'slideUpIn 0.38s cubic-bezier(0.22, 1, 0.36, 1) both',
        'review-expand': 'reviewExpand 0.32s cubic-bezier(0.22, 1, 0.36, 1) both',
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
        slideUpIn: {
          '0%': { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        reviewExpand: {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
};
