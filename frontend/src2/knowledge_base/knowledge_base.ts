// Thin wrapper around the `AI Knowledge Base` doctype + its documents child
// table. The backend already exposes all CRUD via standard Frappe doctype
// REST; the only bespoke endpoint we need is `reindex_knowledge_base` for
// the manual retry/reindex action on the detail page.

import { call, createDocumentResource, createListResource } from 'frappe-ui'
import { createToast } from '../helpers/toasts'

export type KnowledgeBaseStatus = 'Queue' | 'In Progress' | 'Completed' | 'Failed'

export type AIKnowledgeBase = {
	name: string
	title: string
	status: KnowledgeBaseStatus
	description?: string
	chunk_size?: number
	chunk_overlap?: number
	last_processed?: string
	error?: string
	documents?: AIKnowledgeDocument[]
	owner?: string
	creation?: string
	modified?: string
}

export type AIKnowledgeDocument = {
	name: string
	title: string
	file: string
	status: KnowledgeBaseStatus
	chunk_count?: number
	error?: string
	parent?: string
	parentfield?: string
	parenttype?: string
	doctype?: string
}

export type KnowledgeBaseListItem = Pick<
	AIKnowledgeBase,
	'name' | 'title' | 'status' | 'description' | 'last_processed' | 'error'
> & {
	document_count: number
	owner?: string
	creation?: string
	modified?: string
}

// `createListResource` returns a reactive `.list.data` array. The default
// backend payload for a child table does not include the child row count on
// the parent list, so we project it client-side off the embedded `documents`
// length that Frappe returns for `frappe.client.get_list` on this doctype.
export function useKnowledgeBaseList() {
	return createListResource({
		cache: 'insights_ai_knowledge_base_list',
		doctype: 'AI Knowledge Base',
		fields: [
			'name',
			'title',
			'status',
			'description',
			'last_processed',
			'error',
			'documents',
			'owner',
			'creation',
			'modified',
		],
		pageLength: 100,
		auto: true,
		transform(rows: AIKnowledgeBase[]): KnowledgeBaseListItem[] {
			return (rows || []).map((row) => ({
				name: row.name,
				title: row.title,
				status: row.status,
				description: row.description,
				last_processed: row.last_processed,
				error: row.error,
				owner: row.owner,
				creation: row.creation,
				modified: row.modified,
				document_count: Array.isArray(row.documents) ? row.documents.length : 0,
			}))
		},
	})
}

// Detail-page resource: one full `AI Knowledge Base` document, with the
// embedded `documents` child table kept live so the per-row status updates
// in place after each background chunk/embed/upsert completes.
export function useKnowledgeBaseResource(name: string) {
	return createDocumentResource({
		doctype: 'AI Knowledge Base',
		name,
		auto: true,
	})
}

// Child table CRUD is intentionally done by mutating the parent document's
// `documents` array in place and calling `save()` on the parent — Frappe's
// REST layer rejects orphan child inserts (children must be saved through
// their parent). The detail page owns that flow; see `KnowledgeBaseDetail.vue`.

type FrappeCallError = { message?: string; exc?: string; _server_messages?: string }

function extractErrorMessage(err: unknown): string {
	if (err && typeof err === 'object' && 'message' in err) {
		const candidate = (err as FrappeCallError).message
		if (typeof candidate === 'string' && candidate.length > 0) return candidate
	}
	if (err instanceof Error) return err.message
	return 'Unknown error'
}

export async function reindexKnowledgeBase(kbName: string): Promise<void> {
	try {
		const result = (await call('insights.api.knowledge_base.reindex_knowledge_base', {
			kb_name: kbName,
		})) as { success?: boolean; message?: string } | undefined
		createToast({
			title: 'Reindex Started',
			message: result?.message || 'Reindexing queued in the background.',
			variant: 'success',
		})
	} catch (error: unknown) {
		createToast({
			title: 'Reindex Failed',
			message: extractErrorMessage(error),
			variant: 'error',
		})
		throw error
	}
}
