<!-- Floating Chat Button -->
<template>
  <div class="fixed bottom-6 right-6 z-50">
    <!-- Chat Panel (Expanded) -->
    <transition
      enter-active-class="transition ease-out duration-200 motion-reduce:transition-none"
      enter-from-class="transform opacity-0 scale-95 translate-y-4"
      enter-to-class="transform opacity-100 scale-100 translate-y-0"
      leave-active-class="transition ease-in duration-150 motion-reduce:transition-none"
      leave-from-class="transform opacity-100 scale-100 translate-y-0"
      leave-to-class="transform opacity-0 scale-95 translate-y-4"
    >
      <div
        v-if="isOpen"
        class="absolute bottom-16 right-0 w-96 h-[500px] bg-surface-white rounded-xl shadow-2xl border border-outline-gray-1 flex flex-col overflow-hidden"
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3 bg-accent text-ink-white">
          <div class="flex items-center gap-2">
            <Sparkles class="w-5 h-5" />
            <span class="font-semibold">{{ dashboardTitle }} AI Assistant</span>
          </div>
          <div class="flex items-center gap-1">
            <button
              @click="startNewSession"
              class="p-1.5 hover:bg-white-overlay-200 rounded-lg transition-colors motion-reduce:transition-none"
              title="New conversation"
            >
              <Plus class="w-4 h-4" />
            </button>
            <button
              @click="showHistory = !showHistory"
              class="p-1.5 hover:bg-white-overlay-200 rounded-lg transition-colors motion-reduce:transition-none"
              title="Chat history"
            >
              <History class="w-4 h-4" />
            </button>
            <button
              @click="isOpen = false"
              class="p-1.5 hover:bg-white-overlay-200 rounded-lg transition-colors motion-reduce:transition-none"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Session History Dropdown -->
        <div v-if="showHistory" class="absolute top-14 right-4 w-72 bg-surface-white rounded-lg shadow-xl border border-outline-gray-1 z-10 max-h-64 overflow-y-auto">
          <div class="p-2 border-b border-outline-gray-1 bg-surface-gray-1">
            <span class="text-xs font-medium text-ink-gray-6">Recent Conversations</span>
          </div>
          <div v-if="sessions.length === 0" class="p-4 text-center text-sm text-ink-gray-6">
            No previous conversations
          </div>
          <div
            v-for="session in sessions"
            :key="session.name"
            @click="loadSession(session.name)"
            class="p-3 hover:bg-surface-gray-1 cursor-pointer border-b border-outline-gray-1 last:border-0"
          >
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium truncate">{{ formatRelative(session.last_activity) }}</span>
              <span class="text-xs text-ink-gray-6">{{ session.message_count }} msgs</span>
            </div>
            <p class="text-xs text-ink-gray-6 truncate mt-1">{{ session.preview || 'No messages' }}</p>
          </div>
        </div>

        <!-- Chat Messages -->
        <div
          ref="messagesContainer"
          class="flex-1 overflow-y-auto p-4 space-y-4"
        >
          <!-- Welcome Message -->
          <div v-if="messages.length === 0" class="text-center py-8">
            <Sparkles class="w-12 h-12 mx-auto text-accent mb-3" />
            <h3 class="font-semibold text-ink-gray-9">{{ dashboardTitle }} AI Assistant</h3>
            <p class="text-sm text-ink-gray-6 mt-1">
              Ask me anything about your {{ dashboardType.toLowerCase() }} data
            </p>
            
            <!-- Quick Actions -->
            <div class="mt-4 space-y-2">
              <p class="text-xs text-ink-gray-6 uppercase tracking-wider">Quick Actions</p>
              <div class="flex flex-wrap justify-center gap-2">
                <button
                  v-for="action in quickActions"
                  :key="action.label"
                  @click="sendQuickAction(action)"
                  class="px-3 py-1.5 text-xs bg-surface-gray-2 text-ink-gray-8 rounded-full hover:bg-surface-gray-3 transition-colors border border-outline-gray-2 motion-reduce:transition-none"
                >
                  {{ action.label }}
                </button>
              </div>
            </div>
          </div>

          <!-- Messages -->
          <template v-for="(message, index) in messages" :key="index">
            <!-- User Message -->
            <div v-if="message.role === 'user'" class="flex justify-end">
              <div class="max-w-[80%] bg-accent text-ink-white rounded-2xl rounded-br-md px-4 py-2">
                <p class="text-sm whitespace-pre-wrap">{{ message.content }}</p>
              </div>
            </div>

            <!-- Assistant Message -->
            <div v-else class="flex justify-start">
              <div class="max-w-[85%] bg-surface-gray-2 rounded-2xl rounded-bl-md px-4 py-2">
                <div class="prose prose-sm max-w-none text-ink-gray-8" v-html="renderMarkdown(message.content)"></div>
                <div v-if="message.metadata?.model_used" class="mt-2 pt-2 border-t border-outline-gray-1">
                  <span class="text-xs text-ink-gray-6">{{ formatModelName(message.metadata.model_used) }}</span>
                </div>
              </div>
            </div>
          </template>

          <!-- Typing Indicator -->
          <div v-if="isLoading" class="flex justify-start">
            <div class="bg-surface-gray-2 rounded-2xl rounded-bl-md px-4 py-3">
              <div class="flex items-center gap-1">
                <span class="w-2 h-2 bg-muted-fill rounded-full animate-bounce motion-reduce:animate-none" style="animation-delay: 0ms"></span>
                <span class="w-2 h-2 bg-muted-fill rounded-full animate-bounce motion-reduce:animate-none" style="animation-delay: 150ms"></span>
                <span class="w-2 h-2 bg-muted-fill rounded-full animate-bounce motion-reduce:animate-none" style="animation-delay: 300ms"></span>
              </div>
            </div>
          </div>

          <!-- Redirect Suggestion -->
          <div v-if="redirectSuggestion" class="bg-surface-amber-1 border border-outline-amber-2 rounded-lg p-3">
            <div class="flex items-start gap-2">
              <ArrowRight class="w-4 h-4 text-warn mt-0.5" />
              <div class="flex-1">
                <p class="text-sm text-warn">{{ redirectSuggestion.reason }}</p>
                <button
                  @click="handleRedirect"
                  class="mt-2 text-sm font-medium text-warn hover:underline underline"
                >
                  Go to {{ redirectSuggestion.target }} Intelligence →
                </button>
              </div>
              <button @click="redirectSuggestion = null" class="text-warn hover:opacity-75">
                <X class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <!-- Quick Actions Bar (when has messages) -->
        <div v-if="messages.length > 0" class="px-3 py-2 border-t border-outline-gray-1 bg-surface-gray-1 overflow-x-auto">
          <div class="flex gap-2">
            <button
              v-for="action in quickActions.slice(0, 3)"
              :key="action.label"
              @click="sendQuickAction(action)"
              class="px-2 py-1 text-xs bg-surface-white border border-outline-gray-1 text-ink-gray-6 rounded-lg hover:bg-surface-gray-2 whitespace-nowrap"
            >
              {{ action.label }}
            </button>
          </div>
        </div>

        <!-- Input Area -->
        <div class="p-3 border-t border-outline-gray-1 bg-surface-white">
          <div class="flex items-end gap-2">
            <textarea
              ref="inputRef"
              v-model="inputMessage"
              @keydown.enter.exact.prevent="sendMessage"
              placeholder="Ask about your data..."
              rows="1"
              class="flex-1 resize-none rounded-xl border border-outline-gray-1 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent max-h-32"
              :disabled="isLoading"
            />
            <button
              @click="sendMessage"
              :disabled="!inputMessage.trim() || isLoading"
              class="p-2.5 bg-accent text-ink-white rounded-xl hover:bg-accent-strong disabled:opacity-50 disabled:cursor-not-allowed transition-colors motion-reduce:transition-none"
            >
              <Send class="w-5 h-5" />
            </button>
          </div>
          <p class="text-xs text-ink-gray-6 mt-1.5 text-center">
            AI may make mistakes. Verify important information.
          </p>
        </div>
      </div>
    </transition>

    <!-- Floating Button -->
    <button
      @click="toggleChat"
      :class="[
        'w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-300 border-2',
        isOpen 
          ? 'bg-surface-white border-outline-gray-3 hover:bg-surface-gray-2'
          : 'bg-accent border-accent hover:bg-accent-strong'
      , 'motion-reduce:transition-none']"
    >
      <MessageCircle v-if="!isOpen" class="w-6 h-6 text-ink-white" />
      <ChevronDown v-else class="w-6 h-6 text-ink-gray-9" />
    </button>

    <!-- Notification Badge -->
    <span
      v-if="!isOpen && hasNewMessage"
      class="absolute -top-1 -right-1 w-4 h-4 bg-neg-fill rounded-full flex items-center justify-center"
    >
      <span class="w-2 h-2 bg-neg-fill rounded-full animate-ping motion-reduce:animate-none opacity-70"></span>
    </span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { call } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { renderMarkdown } from '../utils/markdown'
import { formatRelative } from '../utils/format'
import type { ChatDashboardType } from '../helpers/dashboards'
import { 
  MessageCircle, X, Send, Sparkles, Plus, History,
  ChevronDown, ArrowRight
} from 'lucide-vue-next'
import { createToast, createInfoToast } from '../helpers/toasts'

// Props
const props = defineProps<{
  dashboardType: ChatDashboardType
  dashboardContext: Record<string, any>
}>()

// Emits
const emit = defineEmits<{
  (e: 'navigate-dashboard', target: string): void
}>()

// Router
const router = useRouter()

// State
const isOpen = ref(false)
const isLoading = ref(false)
const inputMessage = ref('')
const messages = ref<Array<{role: string, content: string, timestamp?: string, metadata?: any}>>([])
const sessionId = ref<string | null>(null)
const quickActions = ref<Array<{label: string, prompt_template: string, icon?: string}>>([])
const sessions = ref<Array<{name: string, last_activity: string, message_count: number, preview: string}>>([])
const showHistory = ref(false)
const hasNewMessage = ref(false)
const redirectSuggestion = ref<{target: string, reason: string} | null>(null)

// Refs
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)

// Computed
/**
 * The prop value is already the display name for every type in use, so this is
 * an identity mapping.
 *
 * It previously listed only 7 of 12 union members, which read as exhaustive and
 * invited callers to trust it; the 5 unlisted ones fell through to the same
 * value the map would have returned anyway.
 */
const dashboardTitle = computed(() => props.dashboardType)

// LocalStorage key for panel state
const storageKey = computed(() => `insights:chat:${props.dashboardType}:open`)

// Initialize on mount
onMounted(async () => {
  // Restore panel state
  const savedState = localStorage.getItem(storageKey.value)
  if (savedState === 'true') {
    isOpen.value = true
  }
  
  // Load quick actions
  await loadQuickActions()
  
  // Auto-load recent session when panel opens
  if (isOpen.value) {
    await loadRecentSession()
  }
})

// Watch for panel open/close
watch(isOpen, async (newVal) => {
  localStorage.setItem(storageKey.value, String(newVal))
  
  if (newVal) {
    await loadRecentSession()
    nextTick(() => {
      inputRef.value?.focus()
      scrollToBottom()
    })
  }
  
  showHistory.value = false
})

// Methods
function toggleChat() {
  isOpen.value = !isOpen.value
  hasNewMessage.value = false
}

async function loadQuickActions() {
  try {
    const response = await call('insights.api.dashboard_chat.get_quick_actions', {
      dashboard_type: props.dashboardType
    })
    if (response?.success) {
      quickActions.value = response.quick_actions || []
    }
  } catch (e) {
    console.error('Failed to load quick actions:', e)
  }
}

async function loadRecentSession() {
  try {
    const response = await call('insights.api.dashboard_chat.get_recent_session', {
      dashboard_type: props.dashboardType
    })
    
    if (response?.has_session) {
      sessionId.value = response.session_id
      messages.value = response.messages || []
      scrollToBottom()
    } else {
      sessionId.value = null
      messages.value = []
    }
    
    // Also load session list
    await loadSessionList()
  } catch (e) {
    console.error('Failed to load recent session:', e)
  }
}

async function loadSessionList() {
  try {
    const response = await call('insights.api.dashboard_chat.list_sessions', {
      dashboard_type: props.dashboardType,
      limit: 10
    })
    if (response?.success) {
      sessions.value = response.sessions || []
    }
  } catch (e) {
    console.error('Failed to load sessions:', e)
  }
}

async function loadSession(name: string) {
  try {
    const response = await call('insights.api.dashboard_chat.get_session', {
      session_id: name
    })
    if (response?.success) {
      sessionId.value = response.session_id
      messages.value = response.messages || []
      showHistory.value = false
      scrollToBottom()
    }
  } catch (e) {
    console.error('Failed to load session:', e)
  }
}

async function startNewSession() {
  try {
    // Start session without context to avoid size issues
    const response = await call('insights.api.dashboard_chat.start_new_session', {
      dashboard_type: props.dashboardType
    })
    
    if (response?.success) {
      sessionId.value = response.session_id
      messages.value = []
      quickActions.value = response.quick_actions || quickActions.value
      showHistory.value = false
      
      createToast({
        title: 'New Conversation',
        message: 'Started a fresh conversation',
        variant: 'success'
      })
    }
  } catch (e) {
    console.error('Failed to start new session:', e)
  }
}

// Dashboard payloads are large but modern models have six-figure context
// windows, so the budget is about staying cheap, not about fitting.
const AI_CONTEXT_MAX_CHARS = 24000

type PruneOpts = { depth: number; arrayCap: number; stringCap: number }

/** Our ML endpoints answer {status, data}; the figures live under `data`. */
function unwrapEnvelope(value: any): any {
	if (
		value && typeof value === 'object' && !Array.isArray(value) &&
		'data' in value && ('status' in value || 'success' in value)
	) {
		return value.data
	}
	return value
}

function prune(value: any, opts: PruneOpts, depth = 0): any {
	if (value === null || value === undefined) return undefined
	const t = typeof value
	if (t === 'number' || t === 'boolean') return value
	if (t === 'string') {
		return value.length > opts.stringCap ? `${value.slice(0, opts.stringCap)}…` : value
	}
	if (Array.isArray(value)) {
		if (depth >= opts.depth) return undefined
		const kept = value
			.slice(0, opts.arrayCap)
			.map((v) => prune(unwrapEnvelope(v), opts, depth + 1))
			.filter((v) => v !== undefined)
		if (!kept.length) return undefined
		const omitted = value.length - kept.length
		return omitted > 0 ? [...kept, `…${omitted} more`] : kept
	}
	if (t === 'object') {
		if (depth >= opts.depth) return undefined
		const out: Record<string, any> = {}
		for (const [k, v] of Object.entries(value)) {
			const p = prune(unwrapEnvelope(v), opts, depth + 1)
			if (p !== undefined) out[k] = p
		}
		return Object.keys(out).length ? out : undefined
	}
	return undefined
}

/**
 * Serialise dashboard state for the model.
 *
 * The previous compressor kept only scalar children, which collapsed a 1.4MB
 * payload to {"sales":{"status":"success"}} — every figure was discarded and
 * the model correctly reported that it had no data. This keeps real nested
 * metrics, tightening depth/array limits across passes instead of dropping
 * content, and always emits valid JSON.
 */
function buildAIContext(context: Record<string, any>, maxChars = AI_CONTEXT_MAX_CHARS): string {
	if (!context) return '{}'

	const root: Record<string, any> = {}
	for (const [k, v] of Object.entries(context)) root[k] = unwrapEnvelope(v)

	const passes: PruneOpts[] = [
		{ depth: 5, arrayCap: 10, stringCap: 200 },
		{ depth: 4, arrayCap: 6, stringCap: 120 },
		{ depth: 3, arrayCap: 4, stringCap: 80 },
		{ depth: 2, arrayCap: 3, stringCap: 60 },
	]

	let pruned: Record<string, any> = {}
	for (const opts of passes) {
		pruned = prune(root, opts) ?? {}
		if (JSON.stringify(pruned).length <= maxChars) return JSON.stringify(pruned)
	}

	// Still over budget: drop the heaviest branches until it fits, so the model
	// gets less data rather than truncated (invalid) JSON.
	const entries = Object.entries(pruned).sort(
		(a, b) => JSON.stringify(b[1]).length - JSON.stringify(a[1]).length,
	)
	while (entries.length > 1 && JSON.stringify(Object.fromEntries(entries)).length > maxChars) {
		const [key, value] = entries.shift() as [string, any]
		entries.push([key, `…omitted, ${JSON.stringify(value).length} chars`])
		entries.sort((a, b) => JSON.stringify(b[1]).length - JSON.stringify(a[1]).length)
		if (entries.every(([, v]) => typeof v === 'string')) break
	}
	return JSON.stringify(Object.fromEntries(entries)).slice(0, maxChars)
}

async function sendMessage() {
  const query = inputMessage.value.trim()
  if (!query || isLoading.value) return
  
  // Clear input immediately
  inputMessage.value = ''
  
  // Add user message to UI
  messages.value.push({
    role: 'user',
    content: query,
    timestamp: new Date().toISOString()
  })
  
  scrollToBottom()
  isLoading.value = true
  redirectSuggestion.value = null
  
  try {
    // Ensure we have a session
    if (!sessionId.value) {
      const sessionResponse = await call('insights.api.dashboard_chat.start_new_session', {
        dashboard_type: props.dashboardType
      })
      if (sessionResponse?.success) {
        sessionId.value = sessionResponse.session_id
      } else {
        throw new Error('Failed to create session')
      }
    }
    
    // Real dashboard figures, bounded by character budget
    const safeContext = buildAIContext(props.dashboardContext || {})

    const response = await call('insights.api.dashboard_chat.send_message', {
      session_id: sessionId.value,
      query: query,
      context: safeContext
    })
    
    if (response?.success) {
      // Add AI response to UI
      messages.value.push({
        role: 'assistant',
        content: response.response,
        timestamp: response.timestamp,
        metadata: {
          model_used: response.model_used
        }
      })
      
      // Handle redirect suggestion
      if (response.should_redirect && response.redirect_to) {
        redirectSuggestion.value = {
          target: response.redirect_to,
          reason: response.redirect_reason
        }
      }
    } else {
      // Add error message
      messages.value.push({
        role: 'assistant',
        content: `Sorry, I encountered an error: ${response?.error || 'Unknown error'}. Please try again.`,
        timestamp: new Date().toISOString()
      })
    }
  } catch (e: any) {
    messages.value.push({
      role: 'assistant',
      content: `Sorry, I couldn't process your request. ${e.message || 'Please try again.'}`,
      timestamp: new Date().toISOString()
    })
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}

async function sendQuickAction(action: { label: string, prompt_template: string }) {
  inputMessage.value = action.prompt_template
  await sendMessage()
}

async function updateSessionContext(context: Record<string, any>) {
  if (!sessionId.value) return
  
  try {
    await call('insights.api.dashboard_chat.update_session_context', {
      session_id: sessionId.value,
      context: buildAIContext(context)
    })
  } catch (e) {
    console.error('Failed to update context:', e)
  }
}

function handleRedirect() {
  if (!redirectSuggestion.value) return
  
  const target = redirectSuggestion.value.target.toLowerCase()
  createInfoToast(`Redirecting to ${redirectSuggestion.value.target} Intelligence...`)
  
  emit('navigate-dashboard', target)
  
  // Navigate using router
  router.push(`/${target}-intelligence`)
  
  redirectSuggestion.value = null
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function formatModelName(model: string): string {
  if (!model) return ''
  // Extract model name from full path
  const parts = model.split('/')
  const name = parts[parts.length - 1].replace(':free', '')
  return name.charAt(0).toUpperCase() + name.slice(1)
}
</script>

<style scoped>
/* Custom scrollbar */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: transparent;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: var(--outline-gray-2);
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: var(--outline-gray-3);
}

/* Prose styling for markdown */
.prose h1, .prose h2, .prose h3 {
  @apply font-semibold text-ink-gray-9 mt-3 mb-2;
}

.prose h1 { @apply text-lg; }
.prose h2 { @apply text-base; }
.prose h3 { @apply text-sm; }

.prose p {
  @apply my-1.5;
}

.prose ul, .prose ol {
  @apply my-2 ml-4;
}

.prose li {
  @apply my-0.5;
}

.prose code {
  @apply bg-surface-gray-3 px-1 py-0.5 rounded text-xs;
}

.prose pre {
  @apply bg-surface-gray-6 text-ink-gray-1 p-3 rounded-lg overflow-x-auto my-2 text-xs;
}

.prose strong {
  @apply font-semibold;
}

/* Textarea auto-resize */
textarea {
  field-sizing: content;
  min-height: 40px;
}
</style>
