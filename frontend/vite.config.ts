import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(() => ({
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://127.0.0.1:5000',
      '/hls': 'http://127.0.0.1:5000',
      '/media': 'http://127.0.0.1:5000'
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // Vendor chunks - separate large libraries
          'react-vendor': ['react', 'react-dom'],
          'ui-vendor': ['lucide-react'],
          'hls-vendor': ['hls.js'],
        },
      },
    },
    chunkSizeWarningLimit: 1000, // Increase limit to 1000 kB to reduce warnings
  },
}));
