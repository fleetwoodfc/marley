import path from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    frappeui({
      frappeProxy: true,
      lucideIcons: true,
      jinjaBootData: true,
      buildConfig: {
        outDir: path.resolve(
          __dirname,
          '../ups_worklist_portal/public/ups_worklist',
        ),
        indexHtmlPath: path.resolve(
          __dirname,
          '../ups_worklist_portal/www/ups_worklist.html',
        ),
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
