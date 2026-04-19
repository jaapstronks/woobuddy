import { json } from '@sveltejs/kit';

/**
 * Lightweight liveness endpoint for the Docker healthcheck and Caddy's
 * active load-balancer probe during rolling deploys. Intentionally does
 * no work — if the node process is accepting connections on port 3000
 * and responding with 200, the replica is ready to receive traffic.
 *
 * Kept separate from `/api/health` (FastAPI) so the frontend container
 * can be probed without a round-trip to the backend.
 */
export function GET() {
	return json({ status: 'ok' });
}
