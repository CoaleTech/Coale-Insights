import useDocumentResource from '../helpers/resource'
import { createToast } from '../helpers/toasts'

let settings = undefined as Settings | undefined
export default function useSettings() {
	if (settings) return settings
	return makeSettings()
}

function makeSettings() {
	const doctype = 'Insights Settings'
	const _settings = useDocumentResource<InsightsSettings>(doctype, doctype, {
		initialDoc: {
			name: '',
			enable_permissions: false,
			allowed_origins: '',
			max_records_to_sync: 10_00_000,
			max_memory_usage: 512,
			fiscal_year_start: '2024-04-01',
			week_starts_on: 'Monday',
			enable_data_store: false,
			apply_user_permissions: false,
			// AI Analytics fields
			enable_ai_analytics: false,
			ai_provider: 'openrouter',
			openrouter_api_key: '',
			ai_model: 'nvidia/nemotron-3-super-120b-a12b:free',
			ai_model_fallback: 'nvidia/nemotron-3-ultra-550b-a55b:free',
			ollama_base_url: 'http://localhost:11434',
			ollama_model: 'qwen3.6',
			moonshot_auth_mode: 'API Key',
			moonshot_api_key: '',
			moonshot_model: 'kimi-k3',
			openai_auth_mode: 'API Key',
			openai_api_key: '',
			openai_base_url: 'https://api.openai.com/v1',
			openai_model: 'gpt-5.6-terra',
			nvidia_api_key: '',
			nvidia_model: 'nvidia/nemotron-3-super-120b-a12b',
			refresh_schedule: 'Daily',
			daily_ai_quota: 100,
			ai_quota_used: 0,
			last_ai_refresh: '',
		},
		disableLocalStorage: true,
	})
	_settings.onAfterSave(() =>
		createToast({
			title: 'Settings Updated',
			message: 'Your settings have been updated successfully',
			variant: 'success',
		})
	)
	settings = _settings
	return _settings
}

type Settings = ReturnType<typeof makeSettings>

type InsightsSettings = {
	name: string
	enable_permissions: boolean
	allowed_origins: string
	max_records_to_sync: number
	max_memory_usage: number
	fiscal_year_start: string
	week_starts_on: string
	enable_data_store: boolean
	apply_user_permissions: boolean
	// AI Analytics fields
	enable_ai_analytics: boolean
	ai_provider: string
	openrouter_api_key: string
	ai_model: string
	ai_model_fallback: string
	ollama_base_url: string
	ollama_api_key: string
	ollama_model: string
	moonshot_auth_mode: string
	moonshot_api_key: string
	moonshot_model: string
	openai_auth_mode: string
	openai_api_key: string
	openai_base_url: string
	openai_model: string
	nvidia_api_key: string
	nvidia_model: string
	refresh_schedule: string
	daily_ai_quota: number
	ai_quota_used: number
	last_ai_refresh: string
}
