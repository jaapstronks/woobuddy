import { execSync } from 'node:child_process';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// Resolve the short git commit hash at build time so the
// onderbouwingsrapport (#64) can stamp a verifiable WOO Buddy version
// into its provenance block. Falls back to "dev" when git isn't
// available (e.g. in a slim production container that copies just the
// build output) — the report still renders, the version line just
// reads "WOO Buddy (dev)".
function resolveBuildCommit(): string {
  if (process.env.WOOBUDDY_BUILD_COMMIT) {
    return process.env.WOOBUDDY_BUILD_COMMIT;
  }
  try {
    return execSync('git rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim();
  } catch {
    return 'dev';
  }
}

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  optimizeDeps: {
    exclude: ['pdfjs-dist'],
  },
  define: {
    __WOOBUDDY_BUILD_COMMIT__: JSON.stringify(resolveBuildCommit()),
  },
});
