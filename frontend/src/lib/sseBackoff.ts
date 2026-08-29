/** Base reconnect delay in milliseconds. */
const BASE_MS = 1000;
/** Ceiling on the reconnect delay — 30s. */
const MAX_MS = 30000;

/**
 * Exponential backoff for the SSE reconnect loop, with jitter.
 *
 * The old code retried after a fixed 3s, so N tabs reconnected in lockstep
 * during an outage and could trip the per-user (5) and global (100) connection
 * caps on their own. Each failed attempt doubles the delay from 1s up to a 30s
 * ceiling, and a jitter term of up to +100% spreads the retries so tabs stop
 * arriving together. A successful connection calls `reset()`, returning the
 * next delay to the 1s base.
 */
export class SseBackoff {
  private attempt = 0;

  /** Delay to wait before the next reconnect, in milliseconds. */
  nextDelayMs(): number {
    const raw = BASE_MS * 2 ** this.attempt;
    this.attempt += 1;
    return Math.min(raw + Math.random() * raw, MAX_MS);
  }

  /** Reset the sequence so the next reconnect waits for the base delay. */
  reset(): void {
    this.attempt = 0;
  }
}
