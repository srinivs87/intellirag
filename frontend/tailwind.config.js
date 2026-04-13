/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'acl-navy':   '#060B4E',
        'acl-navy2':  '#0A0F5C',
        'acl-orange': '#FA9600',
        'acl-blue':   '#0096D5',
        'acl-blue2':  '#0043C7',
        'acl-lgray':  '#F5F7FA',
        'acl-dgray':  '#4A4A6A',
        'acl-border': '#E2E8F2',
        accent:       '#FA9600',
        'accent-light': '#FFF4E0',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
