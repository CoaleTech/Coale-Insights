<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { call } from 'frappe-ui'
import SettingItem from './SettingItem.vue'
import useSettings from './settings'
import { createToast } from '../helpers/toasts'

const settings = useSettings()
settings.load()

const isTesting = ref(false)
const ollamaModels = ref<string[]>([])

const aiStatus = ref({
	enabled: false,
	configured: false,
	provider: 'openrouter',
	quota_used: 0,
	daily_quota: 100,
	last_refresh: null as string | null
})

async function fetchAIStatus() {
	try {
		const response = await call('insights.ai.openrouter_client.get_ai_status')
		if (response) aiStatus.value = response
	} catch (error) {
		console.error('Failed to fetch AI status:', error)
	}
}

const selectedProvider = computed(() => settings.doc.ai_provider || 'openrouter')

const providerOptions = [
	{ value: 'openrouter', label: 'OpenRouter', icon: 'cloud', desc: 'Cloud AI gateway with free & paid models' },
	{ value: 'openai', label: 'OpenAI', icon: 'zap', desc: 'Direct OpenAI / ChatGPT API' },
	{ value: 'nvidia', label: 'NVIDIA NIM', icon: 'cpu', desc: 'NVIDIA-hosted Llama & Nemotron models' },
	{ value: 'ollama', label: 'Ollama', icon: 'server', desc: 'Local AI, no API key needed' },
	{ value: 'ollama_cloud', label: 'Ollama Cloud', icon: 'cloud-lightning', desc: 'Remote Ollama instance' },
	{ value: 'moonshot', label: 'Kimi (Moonshot)', icon: 'sparkles', desc: 'Moonshot AI Kimi models' },
]

const modelOptions = [
	{ group: 'Free Models', options: [
		{ value: 'nvidia/nemotron-3-super-120b-a12b:free', label: 'Nemotron 3 Super 120B' },
		{ value: 'nvidia/nemotron-3-ultra-550b-a55b:free', label: 'Nemotron 3 Ultra 550B (1M ctx)' },
		{ value: 'google/gemma-4-31b-it:free', label: 'Gemma 4 31B' },
		{ value: 'google/gemma-4-26b-a4b-it:free', label: 'Gemma 4 26B' },
		{ value: 'nvidia/nemotron-3-nano-30b-a3b:free', label: 'Nemotron 3 Nano 30B' },
		{ value: 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free', label: 'Nemotron 3 Nano Omni (reasoning)' },
		{ value: 'inclusionai/ling-3.0-flash:free', label: 'Ling 3.0 Flash' },
		{ value: 'cohere/north-mini-code:free', label: 'North Mini Code' },
		{ value: 'openai/gpt-oss-20b:free', label: 'GPT-OSS 20B' },
		{ value: 'nvidia/nemotron-nano-9b-v2:free', label: 'Nemotron Nano 9B v2' },
	]},
	{ group: 'Paid Models', options: [
		{ value: 'openai/gpt-5.6-terra', label: 'GPT-5.6 Terra (balanced)' },
		{ value: 'openai/gpt-5.6-luna', label: 'GPT-5.6 Luna (cheapest)' },
		{ value: 'openai/gpt-5.6-sol', label: 'GPT-5.6 Sol (frontier)' },
		{ value: 'anthropic/claude-sonnet-5', label: 'Claude Sonnet 5' },
		{ value: 'anthropic/claude-haiku-4.5', label: 'Claude Haiku 4.5' },
		{ value: 'google/gemini-3.5-flash', label: 'Gemini 3.5 Flash' },
		{ value: 'moonshotai/kimi-k3', label: 'Kimi K3' },
		{ value: 'deepseek/deepseek-v4-pro', label: 'DeepSeek V4 Pro' },
	]}
]

const scheduleOptions = [
	{ value: 'Disabled', label: 'Disabled' },
	{ value: 'Daily', label: 'Daily' },
	{ value: 'Weekly', label: 'Weekly' },
	{ value: 'Monthly', label: 'Monthly' },
]

const quotaPercent = computed(() => {
	const used = aiStatus.value.quota_used || 0
	const total = settings.doc.daily_ai_quota || 100
	return Math.min(100, (used / total) * 100)
})

const quotaColor = computed(() => {
	if (quotaPercent.value >= 90) return 'bg-neg-fill'
	if (quotaPercent.value >= 70) return 'bg-warn-fill'
	return 'bg-info-fill'
})

function formatDate(dateStr: string | null) {
	if (!dateStr) return 'Never'
	const date = new Date(dateStr)
	return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

async function testConnection() {
	const provider = settings.doc.ai_provider || 'openrouter'

	if (provider === 'openrouter' && !settings.doc.openrouter_api_key) {
		createToast({ title: 'API Key Required', message: 'Enter your OpenRouter API key first', variant: 'warning' })
		return
	}

	// Subscription mode carries an OAuth token instead of a key.
	if (provider === 'openai' && !usesSubscription.value && !settings.doc.openai_api_key) {
		createToast({ title: 'API Key Required', message: 'Enter your OpenAI API key first', variant: 'warning' })
		return
	}

	if (provider === 'nvidia' && !settings.doc.nvidia_api_key) {
		createToast({ title: 'API Key Required', message: 'Enter your NVIDIA API key first', variant: 'warning' })
		return
	}

	// Subscription mode carries an OAuth token instead of a key.
	if (provider === 'moonshot' && !usesKimiSubscription.value && !settings.doc.moonshot_api_key) {
		createToast({ title: 'API Key Required', message: 'Enter your Moonshot API key first', variant: 'warning' })
		return
	}

	isTesting.value = true
	try {
		const response = await call('insights.ai.openrouter_client.test_connection', { provider })

		if (response?.success) {
			const isOllama = provider === 'ollama' || provider === 'ollama_cloud'
			const msg = isOllama
				? `Connected. ${response.data?.model_count || 0} models available.`
				: 'Connection successful'

			// If Ollama, populate discovered models
			if (isOllama && response.data?.models) {
				ollamaModels.value = response.data.models
			}

			createToast({ title: 'Connected', message: msg, variant: 'success' })
		} else {
			createToast({ title: 'Connection Failed', message: response?.error || 'Unable to connect', variant: 'error' })
		}
	} catch (error: any) {
		createToast({ title: 'Error', message: error.message || 'Connection test failed', variant: 'error' })
	} finally {
		isTesting.value = false
	}
}

async function fetchOllamaModels() {
	try {
		const provider = selectedProvider.value === 'ollama_cloud' ? 'ollama_cloud' : 'ollama'
		const response = await call('insights.ai.openrouter_client.test_connection', { provider })
		if (response?.success && response.data?.models) {
			ollamaModels.value = response.data.models
		}
	} catch { /* silent */ }
}

const OLLAMA_CLOUD_URL = 'https://ollama.com'
const LOOPBACK_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '::1']

const isOllamaCloud = computed(() => selectedProvider.value === 'ollama_cloud')

/** Mirrors OllamaClient._is_loopback so the UI shows what the server will use. */
function isLoopbackUrl(url: string) {
	if (!url) return true
	const host = url.replace(/^\w+:\/\//, '').split('/')[0].split(':')[0].replace(/[[\]]/g, '')
	return LOOPBACK_HOSTS.includes(host.toLowerCase())
}

/**
 * `ollama_base_url` ships pointing at localhost, which is meaningless for
 * Ollama Cloud. Present it as empty there so the cloud placeholder shows, while
 * still letting a genuine remote override through.
 */
const ollamaBaseUrl = computed({
	get() {
		const stored = settings.doc.ollama_base_url || ''
		if (isOllamaCloud.value && isLoopbackUrl(stored)) return ''
		return stored
	},
	set(value: string) {
		settings.doc.ollama_base_url = value
	},
})

const effectiveOllamaUrl = computed(() => {
	const stored = settings.doc.ollama_base_url || ''
	if (isOllamaCloud.value) {
		return isLoopbackUrl(stored) ? OLLAMA_CLOUD_URL : stored
	}
	return stored || 'http://localhost:11434'
})

type DeviceAuthStatus = {
	connected: boolean
	account_label: string
	expired: boolean
}

type DeviceLoginEndpoints = {
	label: string
	start: string
	poll: string
	disconnect: string
	status: string
}

/**
 * RFC 8628 device-login driver. Both ChatGPT and Kimi expose the same
 * start/poll/disconnect shape, so the cadence and error handling live here once.
 */
function createDeviceLogin(api: DeviceLoginEndpoints) {
	const status = ref<DeviceAuthStatus>({ connected: false, account_label: '', expired: false })
	const code = ref('')
	const url = ref('')
	const state = ref<'idle' | 'waiting' | 'error'>('idle')
	const error = ref('')
	let timer: ReturnType<typeof setTimeout> | undefined

	function stop() {
		if (timer) {
			clearTimeout(timer)
			timer = undefined
		}
	}

	async function refresh() {
		try {
			const r: any = await call(api.status)
			if (r) status.value = r
		} catch { /* silent */ }
	}

	async function poll(intervalMs: number) {
		try {
			const r: any = await call(api.poll)
			if (r?.status === 'connected') {
				state.value = 'idle'
				code.value = ''
				await refresh()
				createToast({ title: `${api.label} connected`, message: status.value.account_label, variant: 'success' })
				return
			}
			if (r?.status === 'pending') {
				timer = setTimeout(() => poll(intervalMs), intervalMs)
				return
			}
			state.value = 'error'
			error.value = r?.error || 'Login failed'
		} catch (e: any) {
			state.value = 'error'
			error.value = e?.message || String(e)
		}
	}

	async function start() {
		error.value = ''
		stop()
		try {
			const r: any = await call(api.start)
			if (!r?.success) {
				state.value = 'error'
				error.value = r?.error || 'Could not start login'
				return
			}
			code.value = r.user_code
			url.value = r.verification_url
			state.value = 'waiting'
			window.open(r.verification_url, '_blank')
			const interval = Math.max(3, Number(r.interval) || 5) * 1000
			timer = setTimeout(() => poll(interval), interval)
		} catch (e: any) {
			state.value = 'error'
			error.value = e?.message || String(e)
		}
	}

	async function disconnect() {
		stop()
		try {
			await call(api.disconnect)
			state.value = 'idle'
			code.value = ''
			await refresh()
			createToast({ title: 'Disconnected', message: `${api.label} subscription removed`, variant: 'success' })
		} catch (e: any) {
			createToast({ title: 'Disconnect failed', message: e?.message || String(e), variant: 'error' })
		}
	}

	return { status, code, url, state, error, start, poll, disconnect, refresh, stop }
}

const chatgpt = createDeviceLogin({
	label: 'ChatGPT',
	start: 'insights.ai.openai_codex_auth.start_chatgpt_login',
	poll: 'insights.ai.openai_codex_auth.poll_chatgpt_login',
	disconnect: 'insights.ai.openai_codex_auth.disconnect_chatgpt',
	status: 'insights.ai.openai_codex_auth.chatgpt_auth_status',
})

const kimi = createDeviceLogin({
	label: 'Kimi',
	start: 'insights.ai.kimi_code_auth.start_kimi_login',
	poll: 'insights.ai.kimi_code_auth.poll_kimi_login',
	disconnect: 'insights.ai.kimi_code_auth.disconnect_kimi',
	status: 'insights.ai.kimi_code_auth.kimi_auth_status',
})

const usesSubscription = computed(() => settings.doc.openai_auth_mode === 'ChatGPT Subscription')
const usesKimiSubscription = computed(() => settings.doc.moonshot_auth_mode === 'Kimi Subscription')

onUnmounted(() => {
	chatgpt.stop()
	kimi.stop()
})

watch(selectedProvider, (val) => {
	if (val === 'ollama' || val === 'ollama_cloud') {
		// Local and cloud serve different catalogs — never show one for the other.
		ollamaModels.value = []
		fetchOllamaModels()
	}
	if (val === 'openai') chatgpt.refresh()
	if (val === 'moonshot') kimi.refresh()
})

onMounted(() => {
	fetchAIStatus()
	if (selectedProvider.value === 'ollama' || selectedProvider.value === 'ollama_cloud') {
		fetchOllamaModels()
	}
	if (selectedProvider.value === 'openai') chatgpt.refresh()
	if (selectedProvider.value === 'moonshot') kimi.refresh()
})
</script>

<template>
	<div class="flex w-full flex-col gap-6 overflow-y-scroll p-8 px-10">
		<!-- Header -->
		<div class="flex items-center justify-between">
			<div>
				<h1 class="text-xl font-semibold text-ink-gray-9">AI Analytics</h1>
				<p class="text-sm text-ink-gray-6 mt-1">Configure AI-powered insights for your dashboards</p>
			</div>
			<Badge
				v-if="settings.doc.enable_ai_analytics"
				variant="subtle"
				theme="green"
				size="md"
			>Active</Badge>
			<Badge v-else variant="subtle" theme="gray" size="md">Inactive</Badge>
		</div>

		<!-- Enable Toggle -->
		<SettingItem
			label="Enable AI Analytics"
			description="Use AI to generate insights, narratives, and recommendations across dashboards."
		>
			<FormControl
				type="checkbox"
				v-model="settings.doc.enable_ai_analytics"
				:label="settings.doc.enable_ai_analytics ? 'On' : 'Off'"
			/>
		</SettingItem>

		<template v-if="settings.doc.enable_ai_analytics">
			<!-- Provider Selection -->
			<div class="border-t pt-6">
				<h2 class="text-base font-medium text-ink-gray-8 mb-3">Provider</h2>
				<div class="grid grid-cols-2 gap-3">
					<label
						v-for="p in providerOptions"
						:key="p.value"
						class="relative flex items-start gap-3 p-4 border rounded-lg cursor-pointer transition-all motion-reduce:transition-none"
					:class="selectedProvider === p.value
						? 'border-accent bg-surface-blue-1 ring-1 ring-outline-blue-1'
						: 'border-outline-gray-1 hover:border-outline-gray-2 hover:bg-surface-gray-1'"
					>
						<input
							type="radio"
							:value="p.value"
							v-model="settings.doc.ai_provider"
						class="mt-0.5 text-accent"
						/>
						<div class="flex-1 min-w-0">
						<div class="font-medium text-sm text-ink-gray-9">{{ p.label }}</div>
						<div class="text-xs text-ink-gray-6 mt-0.5">{{ p.desc }}</div>
						</div>
					</label>
				</div>
			</div>

			<!-- OpenRouter Config -->
			<div v-if="selectedProvider === 'openrouter'" class="border-t pt-6 space-y-5">
				<h2 class="text-base font-medium text-ink-gray-8">OpenRouter Settings</h2>

				<div>
					<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">API Key</label>
					<div class="flex gap-2">
						<FormControl
							type="password"
							v-model="settings.doc.openrouter_api_key"
							placeholder="sk-or-v1-..."
							class="flex-1"
						/>
						<Button
							variant="outline"
							:loading="isTesting"
							@click="testConnection"
						>Test</Button>
					</div>
					<p class="text-xs text-ink-gray-3 mt-1">Get your key at openrouter.ai/keys</p>
				</div>

				<div class="grid grid-cols-2 gap-4">
					<div>
					<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Primary Model</label>
						<select
							v-model="settings.doc.ai_model"
							class="w-full rounded-md border border-outline-gray-2 px-3 py-[7px] text-sm bg-surface-white focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
						>
							<optgroup v-for="group in modelOptions" :key="group.group" :label="group.group">
								<option v-for="opt in group.options" :key="opt.value" :value="opt.value">
									{{ opt.label }}
								</option>
							</optgroup>
						</select>
					</div>
					<div>
					<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Fallback Model</label>
						<select
							v-model="settings.doc.ai_model_fallback"
							class="w-full rounded-md border border-outline-gray-2 px-3 py-[7px] text-sm bg-surface-white focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
						>
							<optgroup v-for="group in modelOptions" :key="group.group" :label="group.group">
								<option v-for="opt in group.options" :key="opt.value" :value="opt.value">
									{{ opt.label }}
								</option>
							</optgroup>
						</select>
					</div>
				</div>
			</div>

			<!-- OpenAI Config -->
			<div v-if="selectedProvider === 'openai'" class="border-t pt-6 space-y-5">
				<h2 class="text-base font-medium text-ink-gray-8">OpenAI Settings</h2>

				<div>
					<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Authentication</label>
					<select
						v-model="settings.doc.openai_auth_mode"
						class="w-full rounded-md border border-outline-gray-2 px-3 py-[7px] text-sm bg-surface-white focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
					>
						<option value="API Key">API Key — metered, billed per token</option>
						<option value="ChatGPT Subscription">ChatGPT Subscription — Plus/Pro account</option>
					</select>
				</div>

				<!-- ChatGPT subscription login -->
				<div v-if="usesSubscription" class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4 space-y-3">
					<div v-if="chatgpt.status.value.connected" class="flex items-center justify-between gap-3">
						<div>
							<p class="text-sm font-medium text-ink-gray-8">Connected</p>
							<p class="text-xs text-ink-gray-6 mt-0.5">
								{{ chatgpt.status.value.account_label }}
								<span v-if="chatgpt.status.value.expired" class="text-ink-red-3"> · token expired, will refresh on next call</span>
							</p>
						</div>
						<Button variant="subtle" theme="red" @click="chatgpt.disconnect()">Disconnect</Button>
					</div>

					<div v-else-if="chatgpt.state.value === 'waiting'" class="space-y-2">
						<p class="text-sm text-ink-gray-8">
							Enter this code at
							<a :href="chatgpt.url.value" target="_blank" rel="noopener" class="text-ink-blue-3 underline">{{ chatgpt.url.value }}</a>
						</p>
						<p class="font-mono text-2xl font-semibold tracking-widest text-ink-gray-9">{{ chatgpt.code.value }}</p>
						<p class="text-xs text-ink-gray-5">Waiting for approval…</p>
					</div>

					<div v-else class="flex items-center justify-between gap-3">
						<div>
							<p class="text-sm font-medium text-ink-gray-8">Not connected</p>
							<p class="text-xs text-ink-gray-6 mt-0.5">Sign in with a ChatGPT Plus/Pro account instead of an API key.</p>
						</div>
						<Button variant="solid" @click="chatgpt.start()">Connect ChatGPT</Button>
					</div>

					<p v-if="chatgpt.error.value" class="text-xs text-ink-red-3">{{ chatgpt.error.value }}</p>
				</div>

				<div class="grid grid-cols-2 gap-4">
					<div v-if="!usesSubscription">
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">API Key</label>
						<div class="flex gap-2">
							<FormControl
								type="password"
								v-model="settings.doc.openai_api_key"
								placeholder="sk-..."
								class="flex-1"
							/>
							<Button
								variant="outline"
								:loading="isTesting"
								@click="testConnection"
							>Test</Button>
						</div>
						<p class="text-xs text-ink-gray-3 mt-1">API key from platform.openai.com/api-keys, or the bearer token of your gateway.</p>
					</div>
					<div :class="usesSubscription ? 'col-span-2' : ''">
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Model</label>
						<select
							v-model="settings.doc.openai_model"
							class="w-full rounded-md border border-outline-gray-2 px-3 py-[7px] text-sm bg-surface-white focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
						>
							<optgroup label="GPT-5.6 (recommended)">
								<option value="gpt-5.6-terra">GPT-5.6 Terra — balanced</option>
								<option value="gpt-5.6-sol">GPT-5.6 Sol — frontier</option>
								<option value="gpt-5.6-luna">GPT-5.6 Luna — cheapest</option>
							</optgroup>
							<optgroup label="GPT-5.x">
								<option value="gpt-5.5">GPT-5.5</option>
								<option value="gpt-5.4">GPT-5.4</option>
								<option value="gpt-5.4-mini">GPT-5.4 Mini</option>
								<option value="gpt-5.4-nano">GPT-5.4 Nano</option>
							</optgroup>
							<optgroup label="Non-reasoning (legacy)">
								<option value="gpt-4.1">GPT-4.1</option>
								<option value="gpt-4.1-mini">GPT-4.1 Mini</option>
								<option value="gpt-4o">GPT-4o</option>
								<option value="gpt-4o-mini">GPT-4o Mini</option>
							</optgroup>
						</select>
					</div>
				</div>

				<div v-if="!usesSubscription">
					<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Base URL</label>
					<FormControl
						type="text"
						v-model="settings.doc.openai_base_url"
						placeholder="https://api.openai.com/v1"
					/>
					<p class="text-xs text-ink-gray-3 mt-1">
						Leave as-is for a metered OpenAI API key. To bill against a ChatGPT Plus/Pro
						subscription instead, run an OpenAI-compatible gateway that holds the
						subscription OAuth token and point this at it (e.g. http://127.0.0.1:4000/v1).
					</p>
				</div>
			</div>

			<!-- NVIDIA Config -->
			<div v-if="selectedProvider === 'nvidia'" class="border-t pt-6 space-y-5">
				<h2 class="text-base font-medium text-ink-gray-8">NVIDIA NIM Settings</h2>

				<div class="grid grid-cols-2 gap-4">
					<div>
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">API Key</label>
						<div class="flex gap-2">
							<FormControl
								type="password"
								v-model="settings.doc.nvidia_api_key"
								placeholder="nvapi-..."
								class="flex-1"
							/>
							<Button
								variant="outline"
								:loading="isTesting"
								@click="testConnection"
							>Test</Button>
						</div>
						<p class="text-xs text-ink-gray-3 mt-1">Get your key at build.nvidia.com</p>
					</div>
					<div>
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Model</label>
						<select
							v-model="settings.doc.nvidia_model"
							class="w-full rounded-md border border-outline-gray-2 px-3 py-[7px] text-sm bg-surface-white focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
						>
							<optgroup label="Nemotron 3">
								<option value="nvidia/nemotron-3-super-120b-a12b">Nemotron 3 Super 120B</option>
								<option value="nvidia/nemotron-3-ultra-550b-a55b">Nemotron 3 Ultra 550B</option>
								<option value="nvidia/nemotron-3-nano-30b-a3b">Nemotron 3 Nano 30B</option>
								<option value="nvidia/llama-3.3-nemotron-super-49b-v1.5">Llama 3.3 Nemotron Super 49B</option>
							</optgroup>
							<optgroup label="Other publishers">
								<option value="meta/llama-3.3-70b-instruct">Llama 3.3 70B Instruct</option>
								<option value="deepseek-ai/deepseek-v4-pro">DeepSeek V4 Pro</option>
								<option value="minimaxai/minimax-m3">MiniMax M3</option>
								<option value="moonshotai/kimi-k2.6">Kimi K2.6</option>
								<option value="openai/gpt-oss-120b">GPT-OSS 120B</option>
								<option value="mistralai/mistral-nemotron">Mistral Nemotron</option>
							</optgroup>
						</select>
					</div>
				</div>
			</div>

			<!-- Ollama Config -->
			<div v-if="selectedProvider === 'ollama' || selectedProvider === 'ollama_cloud'" class="border-t pt-6 space-y-5">
				<div>
					<h2 class="text-base font-medium text-ink-gray-8">
						{{ selectedProvider === 'ollama_cloud' ? 'Ollama Cloud Settings' : 'Ollama Settings' }}
					</h2>
					<p class="text-xs text-ink-gray-6 mt-1">
						{{ selectedProvider === 'ollama_cloud' ? 'Remote Ollama instance. Enter the URL of your hosted Ollama server.' : 'Runs locally on your machine. Make sure Ollama is running before testing.' }}
					</p>
				</div>

				<div v-if="selectedProvider === 'ollama_cloud'">
					<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">API Key</label>
					<FormControl
						type="password"
						v-model="settings.doc.ollama_api_key"
						placeholder="ollama-..."
					/>
					<p class="text-xs text-ink-gray-3 mt-1">Required for ollama.com. Get your key from your Ollama account.</p>
				</div>

				<div class="grid grid-cols-2 gap-4">
					<div>
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Base URL</label>
						<div class="flex gap-2">
							<FormControl
								type="text"
								v-model="ollamaBaseUrl"
								:placeholder="isOllamaCloud ? 'https://ollama.com' : 'http://localhost:11434'"
								class="flex-1"
							/>
							<Button
								variant="outline"
								:loading="isTesting"
								@click="testConnection"
							>Test</Button>
						</div>
						<p class="text-xs text-ink-gray-3 mt-1">
							Requests go to <span class="font-mono">{{ effectiveOllamaUrl }}</span>.
							<template v-if="isOllamaCloud"> A localhost address is ignored for Ollama Cloud.</template>
						</p>
					</div>
					<div>
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Model</label>
						<FormControl
							v-if="ollamaModels.length === 0"
							type="text"
							v-model="settings.doc.ollama_model"
							placeholder="llama3.1"
						/>
						<select
							v-else
							v-model="settings.doc.ollama_model"
							class="w-full rounded-md border border-outline-gray-2 px-3 py-[7px] text-sm bg-surface-white focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
						>
							<option v-for="m in ollamaModels" :key="m" :value="m">{{ m }}</option>
						</select>
						<p class="text-xs text-ink-gray-3 mt-1">
							{{ ollamaModels.length > 0 ? `${ollamaModels.length} models detected` : 'Test connection to discover models' }}
						</p>
					</div>
				</div>
			</div>

			<!-- Kimi / Moonshot Config -->
			<div v-if="selectedProvider === 'moonshot'" class="border-t pt-6 space-y-5">
				<h2 class="text-base font-medium text-ink-gray-8">Kimi (Moonshot) Settings</h2>

				<div>
					<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Authentication</label>
					<select
						v-model="settings.doc.moonshot_auth_mode"
						class="w-full rounded-md border border-outline-gray-2 px-3 py-[7px] text-sm bg-surface-white focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
					>
						<option value="API Key">API Key — Moonshot Open Platform, billed per token</option>
						<option value="Kimi Subscription">Kimi Subscription — Kimi Code plan</option>
					</select>
					<p class="text-xs text-ink-gray-3 mt-1">
						These are separate services. A Moonshot Open Platform key is rejected by the
						Kimi Code endpoint, and a subscription serves the kimi-for-coding models.
					</p>
				</div>

				<!-- Kimi subscription login -->
				<div v-if="usesKimiSubscription" class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4 space-y-3">
					<div v-if="kimi.status.value.connected" class="flex items-center justify-between gap-3">
						<div>
							<p class="text-sm font-medium text-ink-gray-8">Connected</p>
							<p class="text-xs text-ink-gray-6 mt-0.5">
								{{ kimi.status.value.account_label }}
								<span v-if="kimi.status.value.expired" class="text-ink-red-3"> · token expired, will refresh on next call</span>
							</p>
						</div>
						<Button variant="subtle" theme="red" @click="kimi.disconnect()">Disconnect</Button>
					</div>

					<div v-else-if="kimi.state.value === 'waiting'" class="space-y-2">
						<p class="text-sm text-ink-gray-8">
							Enter this code at
							<a :href="kimi.url.value" target="_blank" rel="noopener" class="text-ink-blue-3 underline">kimi.com/code/authorize_device</a>
						</p>
						<p class="font-mono text-2xl font-semibold tracking-widest text-ink-gray-9">{{ kimi.code.value }}</p>
						<p class="text-xs text-ink-gray-5">Waiting for approval…</p>
					</div>

					<div v-else class="flex items-center justify-between gap-3">
						<div>
							<p class="text-sm font-medium text-ink-gray-8">Not connected</p>
							<p class="text-xs text-ink-gray-6 mt-0.5">Sign in to a Kimi Code plan instead of using an API key.</p>
						</div>
						<Button variant="solid" @click="kimi.start()">Connect Kimi</Button>
					</div>

					<p v-if="kimi.error.value" class="text-xs text-ink-red-3">{{ kimi.error.value }}</p>
				</div>

				<div class="grid grid-cols-2 gap-4">
					<div v-if="!usesKimiSubscription">
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">API Key</label>
						<div class="flex gap-2">
							<FormControl
								type="password"
								v-model="settings.doc.moonshot_api_key"
								placeholder="sk-..."
								class="flex-1"
							/>
							<Button
								variant="outline"
								:loading="isTesting"
								@click="testConnection"
							>Test</Button>
						</div>
						<p class="text-xs text-ink-gray-3 mt-1">Get your key at platform.moonshot.ai</p>
					</div>
					<div v-if="!usesKimiSubscription">
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Model</label>
						<select
							v-model="settings.doc.moonshot_model"
							class="w-full rounded-md border border-outline-gray-2 px-3 py-[7px] text-sm bg-surface-white focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
						>
							<optgroup label="Kimi K3 (recommended)">
								<option value="kimi-k3">kimi-k3 — 1M context, vision</option>
							</optgroup>
							<optgroup label="Kimi K2">
								<option value="kimi-k2.7-code">kimi-k2.7-code</option>
								<option value="kimi-k2.7-code-highspeed">kimi-k2.7-code-highspeed</option>
								<option value="kimi-k2.6">kimi-k2.6</option>
							</optgroup>
						</select>
					</div>
				</div>
			</div>

			<!-- Schedule & Quota -->
			<div class="border-t pt-6 space-y-5">
				<h2 class="text-base font-medium text-ink-gray-8">Schedule & Limits</h2>

				<div class="grid grid-cols-2 gap-4">
					<div>
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Auto Refresh</label>
						<select
							v-model="settings.doc.refresh_schedule"
							class="w-full rounded-md border border-outline-gray-2 px-3 py-[7px] text-sm bg-surface-white focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
						>
							<option v-for="opt in scheduleOptions" :key="opt.value" :value="opt.value">
								{{ opt.label }}
							</option>
						</select>
					</div>
					<div>
						<label class="block text-sm font-medium text-ink-gray-6 mb-1.5">Daily Quota</label>
						<div class="flex items-center gap-2">
							<FormControl
								type="number"
								v-model="settings.doc.daily_ai_quota"
								:min="1"
								class="w-24"
							/>
							<span class="text-sm text-ink-gray-4">requests/day</span>
						</div>
					</div>
				</div>
			</div>

			<!-- Usage Status -->
			<div class="border-t pt-6">
				<h2 class="text-base font-medium text-ink-gray-8 mb-3">Usage</h2>
				<div class="grid grid-cols-3 gap-3">
					<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
						<p class="text-xs font-medium text-ink-gray-6 uppercase tracking-wide">Quota Today</p>
						<p class="text-lg font-semibold text-ink-gray-9 mt-1">
							{{ aiStatus.quota_used || 0 }}<span class="text-sm font-normal text-ink-gray-3"> / {{ settings.doc.daily_ai_quota || 100 }}</span>
						</p>
						<div class="mt-2 w-full bg-surface-gray-3 rounded-full h-1.5">
							<div
								:class="[quotaColor, 'h-1.5 rounded-full transition-all', 'motion-reduce:transition-none']"
								:style="`width: ${quotaPercent}%`"
							></div>
						</div>
					</div>
					<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
						<p class="text-xs font-medium text-ink-gray-6 uppercase tracking-wide">Last Refresh</p>
						<p class="text-sm font-medium text-ink-gray-9 mt-1">
							{{ formatDate(aiStatus.last_refresh) }}
						</p>
					</div>
					<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
						<p class="text-xs font-medium text-ink-gray-6 uppercase tracking-wide">Provider</p>
						<p class="text-sm font-medium text-ink-gray-9 mt-1">
							{{ providerOptions.find(p => p.value === selectedProvider)?.label || selectedProvider }}
						</p>
					</div>
				</div>
			</div>
		</template>

		<!-- Save Button -->
		<div class="flex justify-end border-t pt-4">
			<Button
				label="Save"
				variant="solid"
				:disabled="!settings.isdirty"
				:loading="settings.saving"
				@click="() => settings.save()"
			/>
		</div>
	</div>
</template>
