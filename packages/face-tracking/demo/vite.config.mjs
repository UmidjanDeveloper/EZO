import {defineConfig} from 'vite';
export default defineConfig({worker:{format:'iife'},server:{host:'127.0.0.1',port:8099,strictPort:true},preview:{host:'127.0.0.1',port:8099,strictPort:true}});
