import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path';

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  define:{
    'process.env':{
      
    }
  },
  build:{
    outDir:"../backend/assets/",
    lib:{
      entry:resolve(__dirname, "src/main.tsx"),
      formats:['es'],
      fileName:'chat-widget'
    },
    rollupOptions:{
      output:{
        entryFileNames:'chat-widget.js',
        chunkFileNames:'chat-widget.js',
        inlineDynamicImports:true,
      }
    }
  }
})
