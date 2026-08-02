import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import Icons from 'unplugin-icons/vite'
import path from 'path'

export default defineConfig({
  // Icons mirrors vite.config.js. frappe-ui's barrel (`import { Badge } from
  // 'frappe-ui'`) pulls in Combobox.vue, which imports `~icons/lucide/check`.
  // That is a virtual module only unplugin-icons can resolve, so without this
  // any spec importing a frappe-ui component fails at transform time.
  plugins: [Icons({ compiler: 'vue3' }), vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    // Unit specs live beside the code in src2. `tests/` holds Playwright E2E
    // specs (see playwright.config.js) which import @playwright/test and need a
    // live server; collecting them here fails the run before any unit test.
    include: ['src2/**/*.spec.{ts,js}'],
    server: {
      deps: {
        // frappe-ui ships untranspiled ESM from src/ and its utils/dayjs.js does
        // a directory import. Externalised deps are resolved by Node, which
        // rejects that and skips the alias below, so any spec touching
        // frappe-ui's chart option builders fails to load. Inlining routes it
        // through Vite, exactly as the app build does.
        inline: ['frappe-ui'],
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src2'),
      // frappe-ui's utils/dayjs.js does a directory import of 'dayjs/esm'.
      // Vite resolves that during a build; Node's ESM resolver in vitest does
      // not, which breaks any spec that reaches frappe-ui's chart option
      // builders. Point at the explicit entry instead.
      'dayjs/esm/plugin': path.resolve(__dirname, 'node_modules/dayjs/esm/plugin'),
      'dayjs/esm': path.resolve(__dirname, 'node_modules/dayjs/esm/index.js'),
    },
  },
})
