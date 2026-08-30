# Parametric Modelling Review

## 1. Architecture & Engine Design
* **SysML v2 Alignment**: The distinction between declarative models (`Parameter`, `Constraint`) and their derived states (`EvaluatedParameter`) is a robust, scalable pattern.
* **Separation of Concerns**: Offloading the mathematical AST parsing and DAG resolution to `backend/app/services/evaluation.py` while using `WhatIfContext` on the frontend for speculative overrides is the correct architectural choice for a heavy solver.
* **Tokenizer**: `exprTokens.ts` is elegantly simple, correctly prioritizing round-tripping and non-destructive rendering over rigid AST validation.

## 2. Data Entry & Editing (The `ExpressionField`)
* **Current State**: Uses an auto-growing `<textarea>` combined with a custom fuzzy-search dropdown for variable resolution. 
* **Critique**:
  * **Syntax Blindness**: Users type into plain text. The tokenized syntax highlighting (`Expr` component) only appears *after* saving. This creates a disconnect during complex formula entry.
  * **Layout Jumps**: Switching a row into `ParameterEditRow` causes minor layout shifts because the input fields don't perfectly match the dimensions of the read-only text spans.
* **Proposed Upgrade**: Implement a "transparent textarea over highlighted div" pattern so syntax highlighting happens in real-time as the user types. Use Framer Motion's `layout` prop to smooth the transition between read and edit states.

## 3. Data Visualization & Feedback
* **Current State**: Constraints use `VerdictBadge` and `MarginTag` (e.g., `margin +15%`). The `WhatIfPanel` provides a linear, step-by-step playback of cascading failures.
* **Critique**:
  * **Missing Spatial Context**: A numeric margin (`+15%`) requires cognitive load to interpret. Parametrics benefit massively from visual "bullet charts" or threshold bars that show *how close* a value is to failing a constraint.
  * **Playback Abruptness**: The `WhatIfPanel` simply slices an array (`impact.steps.slice(0, stepIndex + 1)`). The steps blink into existence abruptly, which diminishes the "cascade" feel of the simulation.
* **Proposed Upgrade**: 
  * Add visual margin bars behind the constraint expressions, turning the row itself into a subtle gauge.
  * Apply `AnimatePresence` to the `WhatIfPanel` steps so they slide and fade down sequentially, making the cascading impact physically intuitive.

## 4. Accessibility & Polish
* **Combobox ARIA**: The custom autocomplete dropdown in `ExpressionField` lacks `aria-activedescendant` management, making it opaque to screen readers.
* **Overrides**: The beaker icon for "What-If" overrides is clever, but the inline input field that appears could benefit from a clearer visual connection to the original value it's masking.

