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
          if (id.includes('@xyflow') || id.includes('d3-')) return 'graph'
          if (id.includes('recharts')) return 'charts'
          if (id.includes('@tiptap') || id.includes('prosemirror')) return 'editor'
          if (id.includes('framer-motion') || id.includes('lucide-react')) return 'motion'
          // Before the `react` catch-all: @dnd-kit's paths contain "react",
          // so it would otherwise land in the critical-path chunk.
          if (id.includes('@dnd-kit')) return 'dnd'
          if (id.includes('react')) return 'react'
        },
      },
    },
  },
})
