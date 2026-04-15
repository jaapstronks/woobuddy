/**
 * Shared `Command` interface for the undo/redo store (#08).
 *
 * Every editing action in the review page is wrapped in a `Command` with
 * `forward()` and `reverse()`, pushed onto the undo stack, and from then
 * on `Ctrl+Z` walks it back. Concrete implementations live alongside this
 * file in `./commands/*.ts`; the store state is in `../undo.svelte.ts`.
 */
export interface Command {
	/** Short Dutch label for debugging / future toasts. */
	readonly label: string;
	/** IDs of detections this command affects — used to flash overlays on (un)redo. */
	readonly affectedDetectionIds: string[];
	/** Apply the command (initial run) — used for `push` and `redo`. */
	forward(): Promise<void>;
	/** Roll the command back — used for `undo`. */
	reverse(): Promise<void>;
}
