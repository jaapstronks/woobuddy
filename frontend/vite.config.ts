import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
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

// The release version, read from package.json — which release-please keeps in
// step with `VERSION` in the repository root, so there is no second place to
// bump. See docs/reference/versioning.md.
function resolveVersion(): string {
  const path = fileURLToPath(new URL('./package.json', import.meta.url));
  return JSON.parse(readFileSync(path, 'utf8')).version as string;
}

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  optimizeDeps: {
    exclude: ['pdfjs-dist'],
  },
  define: {
    __WOOBUDDY_BUILD_COMMIT__: JSON.stringify(resolveBuildCommit()),
    __WOOBUDDY_VERSION__: JSON.stringify(resolveVersion()),
  },
});
