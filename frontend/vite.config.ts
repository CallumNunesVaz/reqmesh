import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Split the heavyweight visualisation/editor libraries into their own
        // cacheable chunks instead of one monolithic bundle.
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('@xyflow') || id.includes('@dagrejs') || id.includes('d3-')) return 'graph'
          if (id.includes('recharts')) return 'charts'
          if (id.includes('@tiptap') || id.includes('prosemirror')) return 'editor'
          if (id.includes('framer-motion') || id.includes('lucide-react')) return 'motion'
          if (id.includes('react')) return 'react'
        },
      },
    },
  },
})
