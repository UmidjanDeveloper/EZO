import {defineConfig} from 'vite';
import {resolve} from 'node:path';
export default defineConfig({root:import.meta.dirname,worker:{format:'iife'},build:{outDir:'../../.browser-dist',emptyOutDir:true,rollupOptions:{input:resolve(import.meta.dirname,'index.html')}}});
