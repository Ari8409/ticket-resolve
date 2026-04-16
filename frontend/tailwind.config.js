/** @type {import('tailwindcss').Config} */
export default {
  content: [
    'C:/Users/aritra.e.chatterjee/R&D/ticket-resolve/frontend/index.html',
    'C:/Users/aritra.e.chatterjee/R&D/ticket-resolve/frontend/src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        slate: {
          750: '#293548',
          850: '#172033',
          950: '#0b1120',
        },
        // Singtel brand palette
        singtel: {
          DEFAULT: '#E60028',
          light: '#FF3355',
          lighter: '#FF7088',
          dark: '#B8001F',
          hover: '#CC0022',
          navy: '#00204E',
          'navy-light': '#003087',
        },
      },
      animation: {
        'pulse-slow': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}
