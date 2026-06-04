import path from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'

export default defineConfig({
  plugins: [
    frappeui({
      frappeProxy: true,
      lucideIcons: true,
      jinjaBootData: true,
      buildConfig: {
        outDir: path.resolve(__dirname, '../healthcare/public/event_reports'),
        indexHtmlPath: path.resolve(__dirname, '../healthcare/www/event_reports.html'),
        emptyOutDir: true,
        sourcemap: true,
      },
    }),
    vue(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    target: 'es2015',
  },
  optimizeDeps: {
    include: [
      'frappe-ui > feather-icons',
      'tailwind.config.js',
      'engine.io-client',
    ],
  },
})

