// vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  preview: {
    allowedHosts: ['all'],
  },
  server: {
    host: '0.0.0.0',  // Or true
    port: 4173        // Can change if needed
  }  
})