import containerQueries from '@tailwindcss/container-queries'
import frappeUIPreset from 'frappe-ui/src/tailwind/preset.js'

export default {
	presets: [frappeUIPreset],
	content: [
		'./index.html',
		'./src/**/*.{vue,js,ts,jsx,tsx}',
		'./src2/**/*.{vue,js,ts,jsx,tsx}',
		'./node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}',
		'../node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}',
	],
	theme: {
		container: {
			center: true,
			padding: {
				DEFAULT: '1rem',
				sm: '2rem',
				lg: '2rem',
				xl: '4rem',
				'2xl': '4rem',
			},
		},
		extend: {
			// `extend`, never a replacement: the frappe-ui preset sets
			// `theme.colors = colorPalette` wholesale, and overwriting that is what
			// makes families like `indigo` silently emit zero CSS. Extending merges
			// these on top of the Espresso palette instead.
			//
			// Values resolve to the custom properties defined in src2/index.css, so
			// a `[data-theme="dark"]` switch retints the whole app with no `dark:`
			// variant on any call site.
			colors: {
				canvas: 'var(--app-canvas)',
				card: 'var(--app-card)',
				accent: {
					DEFAULT: 'var(--app-accent)',
					strong: 'var(--app-accent-strong)',
					soft: 'var(--app-accent-soft)',
				},
				// Secondary highlight (Neuform accent field). Sparing decorative /
				// secondary-CTA use only — never a risk-state colour.
				highlight: 'var(--app-highlight)',
				// Text-safe status. All clear WCAG AA on both canvas and card.
				pos: 'var(--app-pos)',
				warn: 'var(--app-warn)',
				neg: 'var(--app-neg)',
				// Non-text fills for bars, series, indicators. 3:1 graphics
				// threshold, NOT valid for text.
				'pos-fill': 'var(--app-pos-fill)',
				'warn-fill': 'var(--app-warn-fill)',
				'neg-fill': 'var(--app-neg-fill)',
				'info-fill': 'var(--app-info-fill)',
				'muted-fill': 'var(--app-muted-fill)',
			},
			fontFamily: {
				// JetBrains Mono for technical/tabular labels (KPI labels, metric
				// captions), matching the Neuform spec's label-md typography. Not
				// self-hosted like Inter is (no bundled woff2 yet), so it degrades
				// to the platform's native monospace stack rather than a network
				// fetch — this codebase self-hosts fonts deliberately (Inter ships
				// from the frappe-ui package, not a Google Fonts import).
				mono: [
					'"JetBrains Mono"',
					'ui-monospace',
					'SFMono-Regular',
					'Menlo',
					'Consolas',
					'monospace',
				],
			},
			maxWidth: {
				'main-content': '768px',
			},
			screens: {
				standalone: {
					raw: '(display-mode: standalone)',
				},
			},
		},
	},
	plugins: [containerQueries],
}
