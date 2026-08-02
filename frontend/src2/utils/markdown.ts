import DOMPurify from 'dompurify'
import { marked } from 'marked'

/**
 * The only sanctioned way to turn model-authored markdown into HTML for
 * `v-html` on this surface.
 *
 * This exists as a module rather than a component-local helper for one reason:
 * the sanitization policy must have exactly one home. When it lived inline in
 * `DashboardChatButton.vue` the next `v-html` site had nothing to import and
 * would have re-derived an unsanitized `marked()` call.
 *
 * ## Why sanitizing is mandatory, not defensive
 *
 * `marked` removed its `sanitize` option in v5; this codebase runs v17, so it
 * emits raw HTML by design and its own documentation delegates sanitization to
 * the caller. The chat sink is reachable by untrusted data:
 *
 *   ERPNext record text (customer/supplier names, invoice remarks)
 *     -> `compressContext(dashboardContext)` in DashboardChatButton
 *     -> model prompt
 *     -> assistant reply
 *     -> persisted server-side against the chat session
 *     -> `v-html`
 *
 * That is a stored, data-driven XSS: one poisoned record name executes in the
 * browser of every user who later opens that thread. Sessions persist, so the
 * payload outlives the request that planted it.
 *
 * `marked` is called first and the *output* is purified, never the input:
 * escaping before parsing would double-encode (`&lt;` becomes `&amp;lt;`) and
 * corrupt legitimate code fences.
 */
export function renderMarkdown(content: string): string {
	if (!content) return ''
	try {
		return DOMPurify.sanitize(marked(content, { breaks: true, gfm: true }) as string)
	} catch {
		// Sanitized on this path too. Returning raw `content` when parsing fails
		// would reopen the identical hole through the error branch.
		return DOMPurify.sanitize(content)
	}
}
