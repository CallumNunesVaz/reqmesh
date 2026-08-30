# Frontend Architecture & UX Review Recommendations

This document outlines the recommended architectural, UX, and accessibility improvements for the `reqmesh` frontend. The recommendations are sorted by impact (largest to smallest) and include the estimated level of effort (LoE) required to implement them.

## 1. Global Accessibility Fix: Respect OS "Reduced Motion" Settings
* **Impact:** High (Accessibility, Compliance, User Comfort)
* **Level of Effort:** Low
* **Description:** The codebase includes a `useReducedMotion.ts` hook intended to disable animations for users with vestibular motion disorders. However, internal comments state that ~55 page-entry animations using `motion.div` ignore this hook. Currently, users who request reduced motion at the OS level are still subjected to slide-in and staggered animations across the app.
* **Suggested Fix:** Instead of passing the hook manually to every component, wrap the application root (in `main.tsx` or `App.tsx`) with Framer Motion's `<MotionConfig reducedMotion="user" />`. This globally forces Framer Motion to respect the user's OS preference, disabling transform-based animations automatically without refactoring 55 individual files.

## 2. Dynamic Theme Updating in Charts
* **Impact:** High (Visual Polish, UX consistency)
* **Level of Effort:** Low
* **Description:** In `ActivityChart.tsx`, chart segment colors are computed once on component mount by reading CSS variables via `getComputedStyle(document.documentElement)` inside a `useMemo` with an empty dependency array. If a user toggles the theme between Dark and Light mode, the charts remain stuck with the original theme's colors until the user performs a hard browser refresh.
* **Suggested Fix:** Recharts natively supports CSS variables in the `fill` and `stroke` properties. Remove the `getComputedStyle` JS-based extraction and pass the CSS variables directly to the chart components (e.g., `fill="var(--chart-change)"`). This allows the browser's CSS engine to instantly swap the colors when the `.dark`/`.light` class changes on the root element.

## 3. Responsive Breakpoints for Navigation Labels
* **Impact:** Medium (Usability, Scannability)
* **Level of Effort:** Low
* **Description:** The top navigation bar in `Layout.tsx` hides text labels and relies purely on icons on screens narrower than `1536px` (using the `hidden 2xl:inline` Tailwind utility). This means users on standard 1080p desktop and laptop screens lose valuable text context for buttons like "Export", "System", "Settings", and "Users" far too early.
* **Suggested Fix:** Lower the hiding breakpoint from `2xl` to `xl` (1280px) or `lg` (1024px) for critical text labels. Given the horizontal scrolling fallback (`overflow-x-auto`) already implemented on the header container, preserving text on 1080p screens will significantly improve discoverability without breaking the layout.

## 4. Centralization of Framer Motion Variants
* **Impact:** Medium (Maintainability, Code Consistency)
* **Level of Effort:** Medium
* **Description:** Across the `src/pages/` directory, there are dozens of inline Framer Motion definitions (e.g., `initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}`). This causes repetition, makes sweeping animation tweaks difficult, and bloats the JSX.
* **Suggested Fix:** Create a central `lib/animations.ts` file that exports standard variants (e.g., `pageFadeIn`, `staggerContainer`, `listItemSlide`). Replace inline objects with the `variants` prop on `motion.div`. This will enforce visual consistency across the app and make future animation adjustments a single-line change.

## 5. CSS Modularity for Canvas Interactions
* **Impact:** Low/Medium (Maintainability, Scalability)
* **Level of Effort:** High
* **Description:** `styles/index.css` contains highly specific, imperative styling rules for the React Flow canvas (e.g., `.rt-dimming`, `.rt-perf`, `.rt-drift`). While placing them in a central stylesheet works, it couples global CSS to internal component logic from `GraphPane.tsx`. 
* **Suggested Fix:** Migrate these specific graph/canvas interaction classes into a CSS Module (e.g., `GraphPane.module.css`) or use Tailwind's arbitrary variants if strictly utilizing the utility-first paradigm. This encapsulates the logic, reducing the global CSS footprint and preventing potential naming collisions as the application scales.

## 6. Deprecate the Redundant Context Wrapper `useContextPane`
* **Impact:** Low (Code Cleanup)
* **Level of Effort:** Low
* **Description:** In `Layout.tsx`, `ContextPaneCtx` handles opening/closing the side inspector. This could be integrated into the existing `useStore` Zustand store. Mixing Zustand for global state and React Context for layout toggles creates a fragmented state management architecture.
* **Suggested Fix:** Move `contextOpen` and `toggleContext` into the primary Zustand store, eliminating the need for `ContextPaneCtx.Provider` and reducing the depth of the React component tree.