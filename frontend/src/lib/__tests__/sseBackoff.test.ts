import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { SseBackoff } from '../sseBackoff';

describe('SseBackoff', () => {
  beforeEach(() => {
    // jitter term is Math.random() * raw; pin it to 0 so delays are the exact
    // doubling sequence and the ordering/cap assertions are deterministic.
    vi.spyOn(Math, 'random').mockReturnValue(0);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('increases the delay on each failed reconnect', () => {
    const b = new SseBackoff();
    const delays = [0, 1, 2, 3, 4].map(() => b.nextDelayMs());
    for (let i = 1; i < delays.length; i += 1) {
      expect(delays[i]).toBeGreaterThan(delays[i - 1]);
    }
  });

  it('caps the delay at 30s', () => {
    const b = new SseBackoff();
    let delay = 0;
    for (let i = 0; i < 20; i += 1) delay = b.nextDelayMs();
    expect(delay).toBe(30000);
  });

  it('resets to the base 1s delay after a successful connection', () => {
    const b = new SseBackoff();
    b.nextDelayMs();
    b.nextDelayMs();
    b.reset();
    expect(b.nextDelayMs()).toBe(1000);
  });

  it('schedules reconnects at the backoff delays via fake timers', () => {
    vi.useFakeTimers();
    const b = new SseBackoff();
    const scheduled: number[] = [];

    const connect = () => {
      const delay = b.nextDelayMs();
      scheduled.push(delay);
      setTimeout(connect, delay);
    };

    connect();
    for (let i = 0; i < 7; i += 1) vi.runOnlyPendingTimers();

    // 1000, 2000, 4000, 8000, 16000, then pinned at the 30s ceiling.
    expect(scheduled.slice(0, 5)).toEqual([1000, 2000, 4000, 8000, 16000]);
    expect(scheduled.slice(5).every((d) => d === 30000)).toBe(true);

    vi.useRealTimers();
  });
});
