import { useState, useEffect, useRef, useCallback } from 'react';
import MESSAGES from '../lib/loadingMessages';

const MIN_INTERVAL_MS = 3000;
const MAX_INTERVAL_MS = 5000;

function randomBetween(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1) + min);
}

function chooseNext(currentId: number | null, currentSeq: number | null) {
  // If we were playing a sequence, advance to the next in that sequence
  if (currentSeq !== null && currentId !== null) {
    const current = MESSAGES.find((m) => m.id === currentId);
    if (current?.seq !== undefined && current.seqPos !== undefined && current.seqLen !== undefined) {
      const nextPos = current.seqPos + 1;
      if (nextPos < current.seqLen) {
        const next = MESSAGES.find(
          (m) => m.seq === current.seq && m.seqPos === nextPos,
        );
        if (next) return next;
      }
    }
    // Sequence ended — fall through to random
  }

  // Pick a random message that either starts a sequence (pos 0) or has no seq
  const candidates = MESSAGES.filter(
    (m) => m.seqPos === undefined || m.seqPos === 0,
  );
  const picked = candidates[Math.floor(Math.random() * candidates.length)];
  return picked;
}

export default function useLoadingMessage(): string {
  const [current, setCurrent] = useState(() => {
    const first = chooseNext(null, null);
    return { id: first.id, text: first.text, seq: first.seq ?? null };
  });

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentRef = useRef(current);
  currentRef.current = current;

  const schedule = useCallback(() => {
    const nextMsg = chooseNext(currentRef.current.id, currentRef.current.seq);
    setCurrent({ id: nextMsg.id, text: nextMsg.text, seq: nextMsg.seq ?? null });
    timerRef.current = setTimeout(schedule, randomBetween(MIN_INTERVAL_MS, MAX_INTERVAL_MS));
  }, []);

  useEffect(() => {
    timerRef.current = setTimeout(schedule, randomBetween(MIN_INTERVAL_MS, MAX_INTERVAL_MS));
    return () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    };
  }, [schedule]);

  return current.text;
}
