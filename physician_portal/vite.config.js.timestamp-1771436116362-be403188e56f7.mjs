// vite.config.js
import path from "path";
import { defineConfig } from "file:///workspace/development/frappe-bench/apps/healthcare/physician_portal/node_modules/vite/dist/node/index.js";
import vue from "file:///workspace/development/frappe-bench/apps/healthcare/physician_portal/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import frappeui from "file:///workspace/development/frappe-bench/apps/healthcare/physician_portal/node_modules/frappe-ui/vite/index.js";
var __vite_injected_original_dirname = "/workspace/development/frappe-bench/apps/healthcare/physician_portal";
var vite_config_default = defineConfig({
  plugins: [
    frappeui({
      frappeProxy: true,
      lucideIcons: true,
      jinjaBootData: true,
      buildConfig: {
        outDir: path.resolve(__vite_injected_original_dirname, "../healthcare/public/physician_portal"),
        indexHtmlPath: path.resolve(__vite_injected_original_dirname, "../healthcare/www/physician_portal.html"),
        emptyOutDir: true,
        sourcemap: true
      }
    }),
    vue()
  ],
  resolve: {
    alias: {
      "@": path.resolve(__vite_injected_original_dirname, "src")
    }
  },
  build: {
    target: "es2015"
  },
  optimizeDeps: {
    include: [
      "frappe-ui > feather-icons",
      "tailwind.config.js",
      "engine.io-client"
    ]
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvd29ya3NwYWNlL2RldmVsb3BtZW50L2ZyYXBwZS1iZW5jaC9hcHBzL2hlYWx0aGNhcmUvcGh5c2ljaWFuX3BvcnRhbFwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiL3dvcmtzcGFjZS9kZXZlbG9wbWVudC9mcmFwcGUtYmVuY2gvYXBwcy9oZWFsdGhjYXJlL3BoeXNpY2lhbl9wb3J0YWwvdml0ZS5jb25maWcuanNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL3dvcmtzcGFjZS9kZXZlbG9wbWVudC9mcmFwcGUtYmVuY2gvYXBwcy9oZWFsdGhjYXJlL3BoeXNpY2lhbl9wb3J0YWwvdml0ZS5jb25maWcuanNcIjtpbXBvcnQgcGF0aCBmcm9tICdwYXRoJ1xuaW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZSdcbmltcG9ydCB2dWUgZnJvbSAnQHZpdGVqcy9wbHVnaW4tdnVlJ1xuaW1wb3J0IGZyYXBwZXVpIGZyb20gJ2ZyYXBwZS11aS92aXRlJ1xuXG4vLyBodHRwczovL3ZpdGVqcy5kZXYvY29uZmlnL1xuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgcGx1Z2luczogW1xuICAgIGZyYXBwZXVpKHtcbiAgICAgIGZyYXBwZVByb3h5OiB0cnVlLFxuICAgICAgbHVjaWRlSWNvbnM6IHRydWUsXG4gICAgICBqaW5qYUJvb3REYXRhOiB0cnVlLFxuICAgICAgYnVpbGRDb25maWc6IHtcbiAgICAgICAgb3V0RGlyOiBwYXRoLnJlc29sdmUoX19kaXJuYW1lLCAnLi4vaGVhbHRoY2FyZS9wdWJsaWMvcGh5c2ljaWFuX3BvcnRhbCcpLFxuICAgICAgICBpbmRleEh0bWxQYXRoOiBwYXRoLnJlc29sdmUoX19kaXJuYW1lLCAnLi4vaGVhbHRoY2FyZS93d3cvcGh5c2ljaWFuX3BvcnRhbC5odG1sJyksXG4gICAgICAgIGVtcHR5T3V0RGlyOiB0cnVlLFxuICAgICAgICBzb3VyY2VtYXA6IHRydWUsXG4gICAgICB9LFxuICAgIH0pLFxuICAgIHZ1ZSgpLFxuICBdLFxuICByZXNvbHZlOiB7XG4gICAgYWxpYXM6IHtcbiAgICAgICdAJzogcGF0aC5yZXNvbHZlKF9fZGlybmFtZSwgJ3NyYycpLFxuICAgIH0sXG4gIH0sXG4gIGJ1aWxkOiB7XG4gICAgdGFyZ2V0OiAnZXMyMDE1JyxcbiAgfSxcbiAgb3B0aW1pemVEZXBzOiB7XG4gICAgaW5jbHVkZTogW1xuICAgICAgJ2ZyYXBwZS11aSA+IGZlYXRoZXItaWNvbnMnLFxuICAgICAgJ3RhaWx3aW5kLmNvbmZpZy5qcycsXG4gICAgICAnZW5naW5lLmlvLWNsaWVudCcsXG4gICAgXSxcbiAgfSxcbn0pXG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQThYLE9BQU8sVUFBVTtBQUMvWSxTQUFTLG9CQUFvQjtBQUM3QixPQUFPLFNBQVM7QUFDaEIsT0FBTyxjQUFjO0FBSHJCLElBQU0sbUNBQW1DO0FBTXpDLElBQU8sc0JBQVEsYUFBYTtBQUFBLEVBQzFCLFNBQVM7QUFBQSxJQUNQLFNBQVM7QUFBQSxNQUNQLGFBQWE7QUFBQSxNQUNiLGFBQWE7QUFBQSxNQUNiLGVBQWU7QUFBQSxNQUNmLGFBQWE7QUFBQSxRQUNYLFFBQVEsS0FBSyxRQUFRLGtDQUFXLHVDQUF1QztBQUFBLFFBQ3ZFLGVBQWUsS0FBSyxRQUFRLGtDQUFXLHlDQUF5QztBQUFBLFFBQ2hGLGFBQWE7QUFBQSxRQUNiLFdBQVc7QUFBQSxNQUNiO0FBQUEsSUFDRixDQUFDO0FBQUEsSUFDRCxJQUFJO0FBQUEsRUFDTjtBQUFBLEVBQ0EsU0FBUztBQUFBLElBQ1AsT0FBTztBQUFBLE1BQ0wsS0FBSyxLQUFLLFFBQVEsa0NBQVcsS0FBSztBQUFBLElBQ3BDO0FBQUEsRUFDRjtBQUFBLEVBQ0EsT0FBTztBQUFBLElBQ0wsUUFBUTtBQUFBLEVBQ1Y7QUFBQSxFQUNBLGNBQWM7QUFBQSxJQUNaLFNBQVM7QUFBQSxNQUNQO0FBQUEsTUFDQTtBQUFBLE1BQ0E7QUFBQSxJQUNGO0FBQUEsRUFDRjtBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
