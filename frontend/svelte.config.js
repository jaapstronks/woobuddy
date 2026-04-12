import adapter from '@sveltejs/adapter-node';

// Shoelace web components (<sl-*>) don't declare ARIA roles that Svelte's
// a11y checker recognizes, so it flags every <sl-button onclick={...}> as a
// "static element with click handler". The components themselves are
// keyboard-accessible — suppress those two rules when the offending element
// is a Shoelace custom element.
const SHOELACE_A11Y_WARNINGS = new Set([
	'a11y_click_events_have_key_events',
	'a11y_no_static_element_interactions'
]);

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true),
		warningFilter: (warning) => {
			if (SHOELACE_A11Y_WARNINGS.has(warning.code) && warning.frame?.includes('<sl-')) {
				return false;
			}
			return true;
		}
	},
	kit: {
		adapter: adapter()
	}
};

export default config;
