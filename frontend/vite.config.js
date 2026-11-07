import { defineConfig } from 'vite';
export default defineConfig({server:{proxy:{'/api':'http://127.0.0.1:5000'}},build:{rollupOptions:{output:{manualChunks:{charts:['recharts'],react:['react','react-dom','react-router-dom']}}}},test:{environment:'jsdom',globals:true}});
