import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx', 'src/**/*.test.ts', 'src/**/*.test.tsx'],
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'json-summary'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/**/__tests__/**',
        'src/lib/generated/**',   // generated from backend schemas; not hand-written
        'src/main.tsx',           // bootstrap only, no branches worth covering
        'src/vite-env.d.ts',
      ],
      // Baseline measured 2026-09-01: statements 18.92%, lines 18.92%,
      // functions 29.83%, branches 73.08%.
      //
      // Lines/statements floor to the whole number below; branches and
      // functions do not. v8 counts branches only in code that is actually
      // loaded, so the branch denominator (1505) is ~17x smaller than the line
      // one (25777) and a floored 73 leaves room for exactly *one* new
      // uncovered branch before CI goes red on unrelated work. These sit a few
      // points under the measurement so the gate catches a real regression
      // rather than ordinary churn: at 70, branches tolerate 66 new uncovered
      // ones; at 28, functions tolerate 50.
      thresholds: { lines: 18, statements: 18, functions: 28, branches: 70 },
    },
  },
});
