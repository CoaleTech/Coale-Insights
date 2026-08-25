<script setup lang="tsx">
// AI Knowledge Base detail page. Mirrors the shape of the doc pages in
// `data_source/` and the list pages in `data_store/`: header with
// Breadcrumbs + Reindex action, child-table CRUD for `documents`, a
// status badge and last-processed timestamp.
//
// File upload follows the pattern from `data_source/UploadCSVFileDialog.vue`
// (frappe-ui `FileUploader` with `uploadArgs: { private: true }`). On
// success we push a row into the parent's `documents` child table and
// `save()` the parent — Frappe rejects orphan child inserts, so children
// must be saved through the parent document.

import {
	Badge,
	Breadcrumbs,
	Button,
	Dialog,
	FileUploader,
	FormControl,
	call,
} from 'frappe-ui'
import {
	BookOpen,
	FileUp,
	PlusIcon,
	RefreshCcw,
	Trash2,
} from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { confirmDialog } from '../helpers/confirm_dialog'
import { createToast } from '../helpers/toasts'
import {
	reindexKnowledgeBase,
	useKnowledgeBaseResource,
	type AIKnowledgeBase,
	type AIKnowledgeDocument,
	type KnowledgeBaseStatus,
} from './knowledge_base'

const props = defineProps<{ name: string }>()
const router = useRouter()

// `useKnowledgeBaseResource` keeps a single live `AI Knowledge Base` doc
// reactive. After every save (incl. child-table mutation + save) we read
// `resource.doc` and the embedded `documents` array refreshes on its own.
const resource = useKnowledgeBaseResource(props.name)

const kb = computed<AIKnowledgeBase>(
	() => (resource.doc as AIKnowledgeBase) || ({} as AIKnowledgeBase)
)
const documents = computed<AIKnowledgeDocument[]>(() => kb.value.documents || [])

const STATUS_THEME: Record<KnowledgeBaseStatus, string> = {
	Queue: 'gray',
	'In Progress': 'orange',
	Completed: 'green',
	Failed: 'red',
}

const reindexing = ref(false)
async function onReindex() {
	if (reindexing.value) return
	reindexing.value = true
	try {
		await reindexKnowledgeBase(props.name)
		await resource.reload()
	} catch {
		// toast already raised
	} finally {
		reindexing.value = false
	}
}

function extractErrorMessage(err: unknown, fallback: string): string {
	if (err && typeof err === 'object' && 'message' in err) {
		const candidate = (err as { message?: unknown }).message
		if (typeof candidate === 'string' && candidate.length > 0) return candidate
	}
	if (err instanceof Error) return err.message
	return fallback
}

// Per-row delete: confirm, remove from in-memory array, save parent.
const deleting = ref<string | null>(null)
function deleteDocument(row: AIKnowledgeDocument) {
	if (!row.name) return
	confirmDialog({
		title: 'Delete Document',
		message: `Remove "${row.title || row.name}" from this knowledge base? The embedded vectors will be deleted on save.`,
		primaryActionLabel: 'Delete',
		theme: 'red',
		onSuccess: async () => {
			deleting.value = row.name
			try {
				const next = (kb.value.documents || []).filter((r) => r.name !== row.name)
				await resource.setValue.submit({ documents: next })
				await resource.reload()
				createToast({
					title: 'Document Removed',
					message: row.title || row.name,
					variant: 'success',
				})
			} catch (error: unknown) {
				createToast({
					title: 'Delete Failed',
					message: extractErrorMessage(error, 'Delete failed'),
					variant: 'error',
				})
			} finally {
				deleting.value = null
			}
		},
	})
}

// Upload dialog: title + a single `Attach` upload. The frontend mirrors the
// `AI Knowledge Document` shape: `title` (required) + `file` (required
// file_url from the uploader). On success, append a row to the parent's
// `documents` array and save the parent — `on_update` on the parent
// auto-enqueues any Queue/Failed row.
const showUpload = ref(false)
const uploadForm = reactive({
	title: '',
	file_url: '',
	file_name: '',
	uploading: false,
	saving: false,
})
const uploadDisabled = computed(
	() => !uploadForm.title.trim() || !uploadForm.file_url || uploadForm.saving
)

function resetUploadForm() {
	uploadForm.title = ''
	uploadForm.file_url = ''
	uploadForm.file_name = ''
	uploadForm.uploading = false
	uploadForm.saving = false
}

// `FileUploader` `@success` payload from frappe-ui looks like
// `{ file_url, file_name, ... }`. We capture the URL and let the admin
// supply a human-readable title separately (or default to file_name).
type FileUploaderSuccess = { file_url?: string; file_name?: string; name?: string }
function onFileUploaded(file: FileUploaderSuccess) {
	uploadForm.file_url = file.file_url || ''
	uploadForm.file_name = file.file_name || file.name || ''
	if (!uploadForm.title.trim()) {
		uploadForm.title = (file.file_name || file.name || 'Untitled').replace(/\.[^.]+$/, '')
	}
	uploadForm.uploading = false
}

async function addDocument() {
	if (uploadDisabled.value) return
	uploadForm.saving = true
	try {
		const newRow: Partial<AIKnowledgeDocument> = {
			doctype: 'AI Knowledge Document',
			title: uploadForm.title.trim(),
			file: uploadForm.file_url,
			status: 'Queue',
		}
		const next = [...(kb.value.documents || []), newRow as AIKnowledgeDocument]
		await resource.setValue.submit({ documents: next })
		await resource.reload()
		createToast({
			title: 'Document Queued',
			message: `${uploadForm.title} will be chunked, embedded, and indexed in the background.`,
			variant: 'success',
		})
		showUpload.value = false
		resetUploadForm()
	} catch (error: unknown) {
		createToast({
			title: 'Add Document Failed',
			message: extractErrorMessage(error, 'Failed to add document'),
			variant: 'error',
		})
	} finally {
		uploadForm.saving = false
	}
}

// Last-processed label fallback
const lastProcessedLabel = computed(() => kb.value.last_processed || 'Never')
const statusTheme = computed(
	() => STATUS_THEME[(kb.value.status as KnowledgeBaseStatus) || 'Queue'] || 'gray'
)

// Keep title in sync
watch(
	() => props.name,
	() => {
		document.title = `${kb.value.title || props.name} | AI Knowledge Base`
	},
	{ immediate: true }
)

function deleteKnowledgeBase() {
	confirmDialog({
		title: 'Delete Knowledge Base',
		message: `Delete "${kb.value.title || props.name}" and all its embedded documents? This cannot be undone.`,
		primaryActionLabel: 'Delete',
		theme: 'red',
		onSuccess: async () => {
			try {
				await call('frappe.client.delete', {
					doctype: 'AI Knowledge Base',
					name: props.name,
				})
				createToast({
					title: 'Knowledge Base Deleted',
					message: kb.value.title || props.name,
					variant: 'success',
				})
				router.push({ path: '/knowledge-base' })
			} catch (error: unknown) {
				createToast({
					title: 'Delete Failed',
					message: extractErrorMessage(error, 'Delete failed'),
					variant: 'error',
				})
			}
		},
	})
}
</script>

<template>
	<header class="flex h-12 items-center justify-between border-b py-2.5 pl-5 pr-2">
		<Breadcrumbs
			:items="[
				{ label: 'AI Knowledge Base', route: '/knowledge-base' },
				{ label: kb.title || name, route: `/knowledge-base/${name}` },
			]"
		/>
		<div class="flex items-center gap-2">
			<Button label="Add Document" variant="solid" @click="showUpload = true">
				<template #prefix>
					<PlusIcon class="w-4" />
				</template>
			</Button>
			<Button
				label="Reindex"
				variant="outline"
				:loading="reindexing"
				@click="onReindex"
			>
				<template #prefix>
					<RefreshCcw class="w-4" />
				</template>
			</Button>
			<Button variant="outline" theme="red" @click="deleteKnowledgeBase">
				<template #prefix>
					<Trash2 class="w-4" />
				</template>
				Delete
			</Button>
		</div>
	</header>

	<div class="mb-4 flex h-full flex-col gap-4 overflow-auto px-5 py-3">
		<!-- Header / metadata card -->
		<div class="flex items-start justify-between gap-4 rounded border border-outline-gray-2 bg-surface-white p-4">
			<div class="flex items-start gap-3">
				<div class="rounded bg-surface-gray-2 p-2">
					<BookOpen class="h-5 w-5 text-ink-gray-6" stroke-width="1.5" />
				</div>
				<div>
					<div class="text-lg font-semibold text-ink-gray-9">
						{{ kb.title || name }}
					</div>
					<p v-if="kb.description" class="mt-1 max-w-2xl text-sm text-ink-gray-6">
						{{ kb.description }}
					</p>
					<div class="mt-2 flex flex-wrap items-center gap-3 text-sm text-ink-gray-6">
						<span>Last processed: <span class="text-ink-gray-8">{{ lastProcessedLabel }}</span></span>
						<span>Chunk size: <span class="text-ink-gray-8">{{ kb.chunk_size ?? 1000 }}</span></span>
						<span>Overlap: <span class="text-ink-gray-8">{{ kb.chunk_overlap ?? 200 }}</span></span>
						<span>Documents: <span class="text-ink-gray-8">{{ documents.length }}</span></span>
					</div>
					<div
						v-if="kb.error"
						class="mt-2 max-w-2xl rounded border border-outline-red-2 bg-surface-red-1 p-2 text-xs text-ink-red-2"
					>
						{{ kb.error }}
					</div>
				</div>
			</div>
			<Badge :theme="statusTheme" variant="subtle" size="md" :label="kb.status || 'Queue'" />
		</div>

		<!-- Documents child table -->
		<div class="rounded border border-outline-gray-2 bg-surface-white">
			<div class="border-b border-outline-gray-1 px-4 py-2 text-sm font-medium text-ink-gray-7">
				Documents
			</div>
			<div v-if="documents.length === 0" class="flex flex-col items-center gap-2 p-6 text-sm text-ink-gray-6">
				<div>No documents yet.</div>
				<Button label="Add Document" variant="outline" @click="showUpload = true" />
			</div>
			<table v-else class="w-full text-sm">
				<thead>
					<tr class="border-b border-outline-gray-1 text-left text-xs uppercase tracking-wide text-ink-gray-6">
						<th class="px-4 py-2">Title</th>
						<th class="px-4 py-2">File</th>
						<th class="px-4 py-2">Status</th>
						<th class="px-4 py-2 text-right">Chunks</th>
						<th class="px-4 py-2">Error</th>
						<th class="px-4 py-2 text-right"></th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="row in documents"
						:key="row.name"
						class="border-b border-outline-gray-1 last:border-b-0"
					>
						<td class="px-4 py-2 font-medium text-ink-gray-8">{{ row.title || '—' }}</td>
						<td class="px-4 py-2 text-ink-gray-7">
							<a
								v-if="row.file"
								:href="row.file"
								target="_blank"
								rel="noreferrer"
								class="text-ink-blue-3 hover:underline"
							>
								{{ row.file.split('/').pop() }}
							</a>
							<span v-else>—</span>
						</td>
						<td class="px-4 py-2">
							<Badge
								:theme="STATUS_THEME[(row.status as KnowledgeBaseStatus) || 'Queue']"
								variant="subtle"
								size="sm"
								:label="row.status || 'Queue'"
							/>
						</td>
						<td class="px-4 py-2 text-right tnum text-ink-gray-7">
							{{ row.chunk_count ?? 0 }}
						</td>
						<td class="px-4 py-2 max-w-md truncate text-xs text-ink-red-2" :title="row.error || ''">
							{{ row.error || '' }}
						</td>
						<td class="px-4 py-2 text-right">
							<Button
								variant="ghost"
								theme="red"
								:loading="deleting === row.name"
								@click="deleteDocument(row)"
							>
								<template #icon>
									<Trash2 class="h-4 w-4" stroke-width="1.5" />
								</template>
							</Button>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>

	<!-- Upload dialog -->
	<Dialog
		v-model="showUpload"
		:options="{ title: 'Add Document', size: 'md' }"
		@after-leave="resetUploadForm"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<FormControl
					label="Title"
					v-model="uploadForm.title"
					placeholder="e.g. GST Filing Guide 2025"
					required
				/>
				<div>
					<label class="mb-1 block text-sm font-medium text-ink-gray-7">File</label>
					<FileUploader
						:upload-args="{ private: true, folder: 'Home/Attachments' }"
						:file-types="['.pdf', '.docx', '.md', '.txt', '.csv', '.xlsx']"
						@success="onFileUploaded"
						@failure="uploadForm.uploading = false"
					>
						<template #default="{ progress, uploading, openFileSelector }">
							<div
								v-if="!uploadForm.file_url"
								class="flex cursor-pointer flex-col items-center justify-center gap-3 rounded border border-dashed border-outline-gray-3 p-8 text-base"
								@click="openFileSelector"
							>
								<FileUp
									v-if="!uploading"
									class="h-6 w-6 text-ink-gray-6"
									stroke-width="1.2"
								/>
								<div class="text-center">
									<p v-if="!uploading" class="text-sm font-medium text-ink-gray-8">
										Select a PDF, DOCX, Markdown, or text file
									</p>
									<p v-if="!uploading" class="mt-1 text-xs text-ink-gray-6">
										or drag and drop it here
									</p>
									<div v-else class="flex w-[15rem] flex-col gap-2">
										<div class="h-2 w-full rounded-full bg-surface-gray-3">
											<div
												class="h-2 rounded-full bg-accent transition-all motion-reduce:transition-none"
												:style="{ width: `${progress}%` }"
											></div>
										</div>
										<p class="text-xs">Uploading...</p>
									</div>
								</div>
							</div>
							<div
								v-else
								class="flex items-center justify-between rounded border border-outline-gray-2 bg-surface-gray-1 p-3 text-sm"
							>
								<span class="truncate text-ink-gray-8">{{ uploadForm.file_name }}</span>
								<Button variant="ghost" @click="uploadForm.file_url = ''">Replace</Button>
							</div>
						</template>
					</FileUploader>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end gap-2">
				<Button @click="showUpload = false">Cancel</Button>
				<Button
					variant="solid"
					:loading="uploadForm.saving"
					:disabled="uploadDisabled"
					@click="addDocument"
				>
					Add
				</Button>
			</div>
		</template>
	</Dialog>
</template>
