/**
 * Provenance hashing for the onderbouwingsrapport (#64).
 *
 * Computes SHA-256 over PDF bytes entirely in the browser via
 * `crypto.subtle.digest`. The hash ends up in the report's provenance
 * block as `sha256:<lowercase-hex>` so a recipient can verify
 * out-of-band that the file in their dossier matches the one this
 * report describes.
 *
 * Client-first: nothing is sent to the server. The original PDF
 * already lives in the review-page memory; the redacted PDF is the
 * blob returned by `exportRedactedPdf`. Both are hashed locally.
 */

function toHex(bytes: ArrayBuffer): string {
	const view = new Uint8Array(bytes);
	let out = '';
	for (let i = 0; i < view.length; i++) {
		out += view[i].toString(16).padStart(2, '0');
	}
	return out;
}

/**
 * SHA-256 of the given bytes, formatted as `sha256:<lowercase-hex>`.
 *
 * Throws when WebCrypto is unavailable (very old browsers, or a
 * non-secure context); the caller treats that as "hash not
 * available" and the report omits the field with explicit copy.
 *
 * We always copy into a fresh `ArrayBuffer` because `Uint8Array.buffer`
 * may be a `SharedArrayBuffer` (e.g. in cross-origin-isolated contexts),
 * which `crypto.subtle.digest` does not accept.
 */
export async function sha256Hex(bytes: ArrayBuffer | Uint8Array): Promise<string> {
	const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
	const copy = new Uint8Array(view.byteLength);
	copy.set(view);
	const digest = await crypto.subtle.digest('SHA-256', copy.buffer);
	return `sha256:${toHex(digest)}`;
}
