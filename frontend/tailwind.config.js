/** @type {import('tailwindcss').Config} */

function rgbChannel(variable) {
  return ({ opacityValue }) =>
    opacityValue === undefined
      ? `rgb(var(${variable}))`
      : `rgb(var(${variable}) / ${opacityValue})`;
}

const primary = Object.fromEntries(
  [50, 100, 200, 300, 400, 500, 600, 700, 800, 900].map((step) => [
    String(step),
    rgbChannel(`--ls-primary-${step}`),
  ]),
);

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary,
        sidebar: {
          DEFAULT: rgbChannel('--ls-sidebar'),
          hover: 'rgba(255,255,255,0.06)',
          active: rgbChannel('--ls-primary-500'),
        },
        surface: {
          DEFAULT: rgbChannel('--ls-surface'),
          muted: rgbChannel('--ls-surface-muted'),
          inset: rgbChannel('--ls-surface-inset'),
        },
        ink: {
          DEFAULT: '#0f172a',
          secondary: '#64748b',
          tertiary: '#94a3b8',
        },
        accent: {
          DEFAULT: rgbChannel('--ls-accent'),
          hover: rgbChannel('--ls-accent-hover'),
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
        button: 'var(--shadow-button)',
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
