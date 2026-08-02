import { frappeRequest, setConfig } from 'frappe-ui'
import { GridItem, GridLayout } from 'grid-layout-plus'
import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import { registerControllers, registerGlobalComponents } from './globals.ts'
import './index.css'
import './composables/useTheme'
import router from './router.ts'
import { createToast } from './helpers/toasts'

setConfig('resourceFetcher', frappeRequest)

// Initialize frappe global object if not exists
if (!window.frappe) window.frappe = {}

// Add CSRF token getter
Object.defineProperty(window.frappe, 'csrf_token', {
  get: () => {
    const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
    return token || ''
  }
})

// Add show_alert method to frappe
window.frappe.show_alert = (options) => {
  const { message, indicator = 'blue', title } = options
  createToast({
    title: title || 'Notification',
    message,
    variant: indicator === 'red' ? 'error' : indicator === 'green' ? 'success' : 'info'
  })
}

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.component('grid-layout', GridLayout)
app.component('grid-item', GridItem)

app.config.errorHandler = (err, vm, info) => {
	console.groupCollapsed('Unhandled Error in: ', info)
	console.error('Context:', vm)
	console.error('Error:', err)
	console.groupEnd()
	return false
}

registerGlobalComponents(app)
registerControllers(app)

app.mount('#app')
