<script setup lang="ts">
import { Breadcrumbs, Button, call } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { Brain, Send, RefreshCw, Sparkles, TrendingUp, AlertTriangle, Lightbulb, Loader2, MessageSquare, X } from 'lucide-vue-next'
import { ref, onMounted, nextTick } from 'vue'
import { createToast } from '../helpers/toasts'

interface Message {
	type: 'user' | 'ai'
	content: string
	metadata?: {
		model_used?: string
		processing_time?: number
		cached?: boolean
		module?: string
	}
	timestamp: Date
}

interface ModuleInsight {
	name: string
	title: string
	description: string
	icon: string
	color: string
}

const messages = ref<Message[]>([])
const currentQuestion = ref('')
const selectedComplexity = ref('simple')
const isLoading = ref(false)
const showModelStatus = ref(false)
const chatContainer = ref<HTMLElement | null>(null)

const suggestions = [
	'What were our top selling items last month?',
	'Show me customer payment trends',
	'Which suppliers have the best performance?',
	'What is our inventory turnover rate?',
	'How is our cash flow looking?'
]

const erpNextModules: ModuleInsight[] = [
	{ name: 'financial', title: 'Financial Analytics', description: 'Revenue, expenses, cash flow', icon: '💰', color: 'bg-surface-green-1 hover:bg-surface-green-2' },
	{ name: 'sales', title: 'Sales Intelligence', description: 'Customer trends, sales performance', icon: '📈', color: 'bg-surface-blue-1 hover:bg-surface-blue-2' },
	{ name: 'procurement', title: 'Procurement Analytics', description: 'Supplier performance, costs', icon: '🛒', color: 'bg-surface-violet-1' },
	{ name: 'inventory', title: 'Inventory Insights', description: 'Stock levels, turnover rates', icon: '📦', color: 'bg-surface-orange-1' },
	{ name: 'production', title: 'Production Analytics', description: 'Efficiency, resource planning', icon: '🏭', color: 'bg-surface-violet-1' },
	{ name: 'customer', title: 'Customer Intelligence', description: 'Lead conversion, customer journey', icon: '👥', color: 'bg-surface-pink-1' }
]

const recentInsights = ref<{id: string, title: string, time: string}[]>([])

function scrollToBottom() {
	nextTick(() => {
		if (chatContainer.value) {
			chatContainer.value.scrollTop = chatContainer.value.scrollHeight
		}
	})
}

async function askQuestion(question: string) {
	if (!question || !question.trim()) return
	
	messages.value.push({
		type: 'user',
		content: question,
		timestamp: new Date()
	})
	
	currentQuestion.value = ''
	isLoading.value = true
	scrollToBottom()
	
	try {
		const response = await apiCall('insights.api.ai_insights.get_ai_insights', {
			query: question,
			complexity: selectedComplexity.value
		})
		
		messages.value.push({
			type: 'ai',
			content: response.response?.content || 'I received your question but couldn\'t generate a response.',
			metadata: {
				model_used: response.model_used,
				processing_time: response.processing_time,
				cached: response.cached
			},
			timestamp: new Date()
		})
	} catch (error: any) {
		messages.value.push({
			type: 'ai',
			content: error.message || 'Sorry, I\'m having trouble connecting to the AI service. Please try again.',
			timestamp: new Date()
		})
	}
	
	isLoading.value = false
	scrollToBottom()
}

async function getBIInsights(module: string) {
	isLoading.value = true
	
	try {
		const response = await call('insights.analytics.ml_engine.get_dashboard', {
			dashboard_type: module
		})
		
		if (response?.ai_insights?.insights) {
			const moduleInfo = erpNextModules.find(m => m.name === module)
			messages.value.push({
				type: 'ai',
				content: `**${moduleInfo?.title || module} Insights:**\n\n${response.ai_insights.insights}`,
				metadata: {
					module: module,
					model_used: response.ai_insights.model_used
				},
				timestamp: new Date()
			})
			
			// Add to recent insights
			recentInsights.value.unshift({
				id: Date.now().toString(),
				title: moduleInfo?.title || module,
				time: new Date().toLocaleTimeString()
			})
			if (recentInsights.value.length > 5) {
				recentInsights.value.pop()
			}
		} else if (response?.ai_insights?.error) {
			messages.value.push({
				type: 'ai',
				content: `Error getting ${module} insights: ${response.ai_insights.error}`,
				timestamp: new Date()
			})
		}
	} catch (error: any) {
		messages.value.push({
			type: 'ai',
			content: `Error: ${error.message || 'Failed to get insights'}`,
			timestamp: new Date()
		})
	}
	
	isLoading.value = false
	scrollToBottom()
}

function handleEnter(event: KeyboardEvent) {
	if (!event.shiftKey) {
		event.preventDefault()
		askQuestion(currentQuestion.value)
	}
}

function formatContent(content: string) {
	// Simple markdown-like formatting
	return content
		.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
		.replace(/\n/g, '<br>')
}

function clearChat() {
	messages.value = []
}

onMounted(() => {
	document.title = 'AI Insights | Insights'
})
</script>

<template>
	<div class="flex h-full flex-col bg-surface-white">
		<!-- Header -->
		<header class="flex h-14 items-center justify-between border-b px-6 py-3">
			<div>
				<h1 class="text-xl font-semibold text-ink-gray-9 flex items-center gap-2">
					<Brain class="h-6 w-6 text-accent" />
					AI-Powered Insights
				</h1>
				<p class="text-sm text-ink-gray-6">Ask natural language questions about your business data</p>
			</div>
			<div class="flex items-center gap-3">
				<div class="flex items-center gap-1 text-sm text-ink-gray-6">
					<div class="w-2 h-2 rounded-full bg-pos-fill"></div>
					<span>AI Online</span>
				</div>
				<Button v-if="messages.length > 0" variant="outline" size="sm" @click="clearChat">
					Clear Chat
				</Button>
			</div>
		</header>

		<!-- Main Content -->
		<div class="flex flex-1 overflow-hidden">
			<!-- Chat Interface -->
			<div class="flex flex-1 flex-col">
				<!-- Chat Messages -->
				<div ref="chatContainer" class="flex-1 overflow-y-auto p-6 space-y-4">
					<!-- Welcome Message -->
					<div v-if="messages.length === 0" class="text-center py-12">
					<div class="text-ink-gray-2 mb-4">
							<MessageSquare class="w-16 h-16 mx-auto" />
						</div>
						<h3 class="text-lg font-medium text-ink-gray-9 mb-2">Welcome to AI Insights</h3>
						<p class="text-ink-gray-6 mb-6">Ask questions about your business data in natural language</p>
						<div class="flex flex-wrap justify-center gap-2 max-w-2xl mx-auto">
							<button
								v-for="suggestion in suggestions"
								:key="suggestion"
								@click="askQuestion(suggestion)"
								class="px-3 py-2 text-sm bg-surface-gray-2 hover:bg-surface-gray-3 rounded-md transition-colors text-ink-gray-6 motion-reduce:transition-none"
							>
								{{ suggestion }}
							</button>
						</div>
					</div>

					<!-- Messages -->
					<div
						v-for="(message, index) in messages"
						:key="index"
						class="flex"
						:class="message.type === 'user' ? 'justify-end' : 'justify-start'"
					>
						<div
							class="max-w-3xl px-4 py-3 rounded-lg"
						:class="message.type === 'user' 
							? 'bg-accent text-ink-white' 
							: 'bg-surface-gray-2 text-ink-gray-9'"
						>
							<div v-if="message.type === 'ai'" class="prose prose-sm max-w-none">
								<div v-html="formatContent(message.content)"></div>
							<div v-if="message.metadata?.model_used" class="text-xs text-ink-gray-6 mt-3 pt-2 border-t border-outline-gray-1">
									Model: {{ message.metadata.model_used }}
									<span v-if="message.metadata.processing_time"> | Time: {{ message.metadata.processing_time }}s</span>
									<span v-if="message.metadata.cached"> | Cached</span>
								</div>
							</div>
							<div v-else>{{ message.content }}</div>
						</div>
					</div>

					<!-- Loading Indicator -->
					<div v-if="isLoading" class="flex justify-start">
					<div class="max-w-3xl px-4 py-3 bg-surface-gray-2 rounded-lg">
							<div class="flex items-center gap-2">
							<Loader2 class="h-4 w-4 animate-spin text-accent motion-reduce:animate-none" />
							<span class="text-ink-gray-6">AI is thinking...</span>
							</div>
						</div>
					</div>
				</div>

				<!-- Input Area -->
				<div class="border-t p-4">
					<div class="flex gap-3">
						<div class="flex-1">
							<textarea
								v-model="currentQuestion"
								@keydown.enter="handleEnter"
								placeholder="Ask a question about your business data..."
							class="w-full p-3 border border-outline-gray-2 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent resize-none text-sm"
								rows="2"
							></textarea>
						</div>
						<div class="flex flex-col gap-2">
							<Button
								variant="solid"
								theme="blue"
								@click="askQuestion(currentQuestion)"
								:disabled="!currentQuestion.trim() || isLoading"
							>
								<template #prefix>
									<Send class="h-4 w-4" />
								</template>
								Send
							</Button>
							<select
								v-model="selectedComplexity"
							class="px-3 py-2 border border-outline-gray-2 rounded-md text-sm"
							>
								<option value="simple">Simple</option>
								<option value="medium">Medium</option>
								<option value="complex">Complex</option>
							</select>
						</div>
					</div>
				</div>
			</div>

			<!-- Quick Insights Sidebar -->
			<div class="w-80 border-l bg-surface-gray-1 p-4 overflow-y-auto hidden lg:block">
				<h3 class="text-lg font-medium text-ink-gray-9 mb-4">Quick Insights</h3>
				
				<div class="space-y-3">
					<div
						v-for="module in erpNextModules"
						:key="module.name"
					:class="['rounded-lg p-4 border border-outline-gray-1 cursor-pointer transition-all', module.color, 'motion-reduce:transition-none']"
						@click="getBIInsights(module.name)"
					>
						<div class="flex items-center justify-between">
							<div>
								<h4 class="font-medium text-ink-gray-9">{{ module.title }}</h4>
								<p class="text-sm text-ink-gray-6">{{ module.description }}</p>
							</div>
							<div class="text-2xl">{{ module.icon }}</div>
						</div>
					</div>
				</div>

				<!-- Recent Insights -->
				<div v-if="recentInsights.length > 0" class="mt-6">
					<h4 class="text-md font-medium text-ink-gray-9 mb-3">Recent Insights</h4>
					<div class="space-y-2">
						<div
							v-for="insight in recentInsights"
							:key="insight.id"
							class="p-3 bg-surface-white rounded border text-sm"
						>
							<p class="text-ink-gray-9 font-medium">{{ insight.title }}</p>
							<p class="text-ink-gray-4 text-xs">{{ insight.time }}</p>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.prose strong {
	font-weight: 600;
}
</style>
