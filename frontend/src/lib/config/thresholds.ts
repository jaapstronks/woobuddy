/**
 * Shared numeric thresholds used across the detection review UI.
 *
 * Keep these in one place so "high confidence" means the same thing in
 * `confidenceToLevel`, the sidebar's bulk-accept action, the detection
 * store's `tier2HighConfidencePendingCount` counter, and the review
 * page's "Accepteer hoge-zekerheid Tier 2" button.
 */

/**
 * Minimum confidence for a detection to be considered "high" by the
 * sidebar confidence badge (`confidenceToLevel`) and by the bulk-accept
 * action that sweeps Tier 2 pending detections.
 */
export const HIGH_CONFIDENCE_THRESHOLD = 0.85;

/**
 * Upper bound of the "low" confidence bucket — below this a detection
 * is shown with a warning badge.
 */
export const LOW_CONFIDENCE_THRESHOLD = 0.6;
