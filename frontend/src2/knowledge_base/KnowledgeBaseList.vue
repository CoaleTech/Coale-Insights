<script setup lang="tsx">
// AI Knowledge Base list page. Mirrors `DataSourceList.vue` / `DataStoreList.vue`:
// header with Breadcrumbs + New action, search bar, ListView over the
// `AI Knowledge Base` doctype. New flow opens a dialog for title/description
// and immediately routes to the new detail page.

import { Badge, Breadcrumbs, Button, Dialog, FormControl, ListView, Textarea, call } from 'frappe-ui'
import { BookOpen, PlusIcon, SearchIcon } from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createToast } from '../helpers/toasts'
import {
	reindexKnowledgeBase,
	useKnowledgeBaseList,
	type KnowledgeBaseListItem,
	type KnowledgeBaseStatus,
} from './knowledge_base'

// frappe-ui's `ListView` column callbacks receive a generic row payload;
// the column object has no exported TS type so we declare the minimal
// shape we actually use here.
type ListColumn = {
	label: string
	key: string
	prefix?: (props: { row: KnowledgeBaseListItem }) => unknown
	getLabel?: (props: { row: KnowledgeBaseListItem }) => string
}

const router = useRouter()
const knowledgeBases = useKnowledgeBaseList()

const searchQuery = ref('')
const filteredKnowledgeBases = computed<KnowledgeBaseListItem[]>(() => {
	const all = (knowledgeBases.list.data as KnowledgeBaseListItem[] | undefined) || []
	if (!searchQuery.value) return all
	const needle = searchQuery.value.toLowerCase()
	return all.filter((kb) => (kb.title || '').toLowerCase().includes(needle))
})

const STATUS_THEME: Record<KnowledgeBaseStatus, string> = {
	Queue: 'gray',
	'In Progress': 'orange',
	Completed: 'green',
	Failed: 'red',
}

const listOptions = ref({
	columns: [
		{
			label: 'Title',
			key: 'title',
			prefix: (props: { row: KnowledgeBaseListItem }) => (
				<BookOpen class="h-4 w-4 text-ink-gray-6" stroke-width="1.5" />
			),
		},
		{
			label: 'Status',
			key: 'status',
			prefix: (props: { row: KnowledgeBaseListItem }) => {
				const theme = STATUS_THEME[props.row.status as KnowledgeBaseStatus] || 'gray'
				return (
					<Badge theme={theme} variant="subtle" size="sm" label={props.row.status} />
				)
			},
		},
		{
			label: 'Documents',
			key: 'document_count',
		},
		{
			label: 'Last Processed',
			key: 'last_processed',
			getLabel(props: { row: KnowledgeBaseListItem }) {
				return props.row.last_processed || '—'
			},
		},
	] as ListColumn[],
	rows: filteredKnowledgeBases,
	rowKey: 'name',
	options: {
		showTooltip: false,
		getRowRoute: (row: KnowledgeBaseListItem) => ({
			path: `/knowledge-base/${row.name}`,
		}),
		emptyState: {
			title: 'No knowledge bases yet.',
			description: 'Create one to ground your agents in your internal documents.',
			button: {
				label: 'New Knowledge Base',
				iconLeft: 'plus',
				variant: 'solid',
				onClick: () => (showNewDialog.value = true),
			},
		},
	},
})

// New KB dialog: title (required, unique) + description. On save we POST a
// fresh `AI Knowledge Base` record via `frappe.client.insert`, then route
// to its detail page. The child `documents` table starts empty.
const showNewDialog = ref(false)
const newForm = reactive({
	title: '',
	description: '',
	saving: false,
})

function resetNewForm() {
	newForm.title = ''
	newForm.description = ''
	newForm.saving = false
}

type FrappeInsertError = { message?: string; exc?: string; _server_messages?: string }
function extractErrorMessage(err: unknown): string {
	if (err && typeof err === 'object' && 'message' in err) {
		const candidate = (err as FrappeInsertError).message
		if (typeof candidate === 'string' && candidate.length > 0) return candidate
	}
	if (err instanceof Error) return err.message
	return 'Failed to create knowledge base'
}

async function createKnowledgeBase() {
	if (!newForm.title.trim() || newForm.saving) return
	newForm.saving = true
	try {
		const insertResult = (await call('frappe.client.insert', {
			doc: {
				doctype: 'AI Knowledge Base',
				title: newForm.title.trim(),
				description: newForm.description || '',
			},
		})) as { name: string }

		createToast({
			title: 'Knowledge Base Created',
			message: insertResult.name,
			variant: 'success',
		})
		showNewDialog.value = false
		resetNewForm()
		await knowledgeBases.reload()
		router.push({ path: `/knowledge-base/${insertResult.name}` })
	} catch (error: unknown) {
		createToast({ title: 'Create Failed', message: extractErrorMessage(error), variant: 'error' })
	} finally {
		newForm.saving = false
	}
}

async function reindexAll() {
	// Per-row reindex on the list page is awkward without a current detail
	// doc loaded. The existing whitelisted endpoint takes a single kb_name.
	// Reindex the first failing KB if any, otherwise no-op (the detail
	// page owns per-doc reindex).
	const failed = filteredKnowledgeBases.value.find((kb) => kb.status === 'Failed')
	if (!failed) {
		createToast({
			title: 'Nothing to Reindex',
			message: 'Open a knowledge base to reindex its documents.',
			variant: 'info',
		})
		return
	}
	await reindexKnowledgeBase(failed.name)
}

document.title = 'AI Knowledge Base | Insights'
</script>

<template>
	<header class="flex h-12 items-center justify-between border-b py-2.5 pl-5 pr-2">
		<Breadcrumbs :items="[{ label: 'AI Knowledge Base', route: '/knowledge-base' }]" />
		<div class="flex items-center gap-2">
			<Button label="New Knowledge Base" variant="solid" @click="showNewDialog = true">
				<template #prefix>
					<PlusIcon class="w-4" />
				</template>
			</Button>
		</div>
	</header>

	<div class="mb-4 flex h-full flex-col gap-3 overflow-auto px-5 py-3">
		<div class="flex items-center justify-between gap-2 overflow-visible py-1">
			<FormControl placeholder="Search by Title" v-model="searchQuery" :debounce="300">
				<template #prefix>
					<SearchIcon class="h-4 w-4 text-ink-gray-4" />
				</template>
			</FormControl>
			<Button label="Reindex Failed" variant="outline" @click="reindexAll" />
		</div>
		<ListView class="h-full" v-bind="listOptions" />
	</div>

	<Dialog
		v-model="showNewDialog"
		:options="{ title: 'New Knowledge Base', size: 'md' }"
		@after-leave="resetNewForm"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<FormControl
					label="Title"
					v-model="newForm.title"
					placeholder="e.g. Tax Reference Library"
					required
				/>
				<Textarea
					label="Description"
					v-model="newForm.description"
					placeholder="What is this KB for? Shown to admins wiring it into a dashboard agent."
					:rows="3"
				/>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end gap-2">
				<Button @click="showNewDialog = false">Cancel</Button>
				<Button
					variant="solid"
					:loading="newForm.saving"
					:disabled="!newForm.title.trim()"
					@click="createKnowledgeBase"
				>
					Create
				</Button>
			</div>
		</template>
	</Dialog>
</template>
