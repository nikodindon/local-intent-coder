# Planner Bug Analysis — Wrong File Targeting (2026-04-11)

## The Bug

During Tic-Tac-Toe v5 run, the pipeline entered an **infinite loop** during Phase 4 (Designer visual audit).

### What Happened

```
Designer POST: "no borders on board/cells" → score 2/10 → NEEDS_VISUAL_FIXES
    ↓
Planner: "Fix index.html"  ← WRONG FILE
    ↓
Coder: modifies HTML (adds <h1>) but CSS still has no borders
    ↓
Designer POST: "no borders on board/cells" → score 2/10 → NEEDS_VISUAL_FIXES
    ↓
PLANNER AGAIN: "Fix index.html"  ← STILL WRONG FILE
    ↓
(loop repeats indefinitely until manual kill)
```

### Root Cause

The Planner is a **text-to-JSON LLM call**. It receives the Designer's issues and produces a fix plan. But it has **no understanding of which file type corresponds to which issue**:

- "no borders" → should target `styles.css` (borders are CSS properties)
- "no title on page" → should target `index.html` (missing DOM element)
- "no background color" → should target `styles.css` (CSS property)
- "no hover state" → should target `styles.css` (CSS pseudo-class)

The LLM-as-Planner guesses based on the text description. It frequently guesses wrong.

### Why It's Critical

This is **Finding #7 revisited**. The Critic couldn't catch runtime bugs (text-only). The Planner can't catch file-type mapping (text-only too). Both need **context-aware routing** to work.

### The Fix

Two approaches:

**A. Rule-based file mapper (simple, reliable)**
Before sending Designer output to the LLM Planner, run a keyword-based file router:
- Keywords: `border`, `background-color`, `color`, `font-size`, `margin`, `padding`, `hover`, `transition`, `box-shadow`, `border-radius` → target `*.css`
- Keywords: `title`, `heading`, `status`, `indicator`, `element`, `div`, `button` → target `*.html`
- Keywords: `logic`, `handler`, `event`, `function`, `state` → target `*.js`

**B. Designer returns structured fix plan (architectural change)**
Instead of free-text audit, the Designer returns:
```json
{
  "score": 2,
  "issues": [
    {"description": "No borders on board/cells", "file": "styles.css"},
    {"description": "No page title", "file": "index.html"}
  ]
}
```

This eliminates the Planner's guessing entirely for visual issues.

### Recommendation

Implement **A first** (quick fix, 20 lines of code), then **B later** (cleaner architecture).

---

## External Reviews Summary (2026-04-11)

Three AI models independently reviewed the project. Here's what all 3 agreed on:

### Unanimous Praise
1. **This is real research, not a toy project** — The Kolmogorov/LLM angle is original
2. **Empirical findings are the strongest asset** — 13 documented findings with concrete bugs
3. **The 5-phase pipeline architecture is mature** — modular, logical, well-sequenced
4. **Functional hashing is innovative** — correct solution to CPU/GPU determinism problem

### Unanimous Criticisms
1. **Compression ratio never measured** — The core research question is unvalidated
2. **Coder ignores visual guidelines** — Post-render audit is a workaround, not a fix
3. **No "wow moment"** — Needs a concrete demo: "250-byte seed regenerates a game"
4. **Planner doesn't map issues to correct files** — Causes infinite loops (confirmed by our v5 bug)

### Priority Recommendations (Consensus)
1. Measure compression ratio NOW (Tic-Tac-Toe v4 has all the data)
2. Fix the Planner file-mapping bug
3. Add win-timing fix (setTimeout before alert)
4. Add Snake as third benchmark
5. Simplify the narrative: "300-byte seed → full app"
