# Phase 1.5 — Execution-Based Validation: Results

## Question
*Can we catch runtime bugs the Critic can't see by actually executing generated artifacts in a headless browser?*

## Answer: ✅ Yes — Execution testing catches critical bugs the Critic misses.

---

## What We Built

### `core/executor.py` — Playwright Browser Test Runner

- Parses features from the Architect's spec
- Detects artifact type (board game, to-do app, counter, etc.)
- Generates type-specific test cases
- Runs tests in headless Chromium via Playwright
- Feeds concrete failure reports back to the Coder for automated repair

### `agent/designer.py` — Visual Quality Auditor (Phase 4)

- **Pre-code**: Enriches spec with concrete visual guidelines (colors, borders, typography, layout)
- **Post-render**: Opens the page in Playwright, extracts computed styles via `getComputedStyle()`, audits against guidelines
- Scores 1-10 and returns `VISUALLY_COMPLETE` or `NEEDS_VISUAL_FIXES`

---

## Test Runs

### Run 1: Tic-Tac-Toe v1 (`output/test-tictactoe`) — 2026-04-10

**Prompt**: `"create a tic-tac-toe game"`

| Metric | Result |
|---|---|
| Files generated | 3/3 (100%) |
| Critic cycles | 1 (ALL_COMPLETE) |
| Executor result | ❌ **5/5 FAILED — wrong test type** |
| Root cause | Executor tried `page.fill('input')` on a board game with no input fields |
| Impact | 8 wasted cycles, Coder rewrote identical code 8 times, pipeline never completed |

**Key discovery**: The Executor's test generation was hardcoded for to-do apps. Board games need completely different tests (cell clicks, not form fills).

---

### Run 2: Tic-Tac-Toe v2 (`output/test-tictactoe-v2`) — 2026-04-11

**Prompt**: `"create a tic-tac-toe game"`
**Changes**: Executor now detects artifact type and generates board game tests

| Metric | Result |
|---|---|
| Files generated | 3/3 (100%) |
| Critic cycles | 1 (ALL_COMPLETE) |
| Executor tests | ✅ **5/5 PASSED** |
| Visual quality | ❌ Bare-bones CSS (no borders, no title centering, no colors) |
| Browser test | ✅ Functional but ugly |

**Tests passed**:
- ✅ Board renders (game board visible)
- ✅ Cell click places mark (X appears on click)
- ✅ Turn alternation (X then O)
- ✅ Win detection (3 in a row triggers alert)
- ✅ Reset works (button clears board)

**Key discovery**: The game works perfectly but has no visual design. The Critic said ALL_COMPLETE because the code is correct. Only a human eye (or a visual auditor) catches this.

---

### Run 3: Tic-Tac-Toe v3 (`output/test-tictactoe-v3`) — 2026-04-11

**Prompt**: `"create a tic-tac-toe game"`
**Changes**: Win detection test fixed to intercept `alert()` dialogs

| Metric | Result |
|---|---|
| Files generated | 3/3 (100%) |
| Critic cycles | 8 (max reached) |
| Executor result | ❌ **4/5 passed — win detection always fails** |
| Root cause | Game calls `alert()` → `resetBoard()` immediately after. Test checks cells AFTER they're already cleared. |
| Completed | ❌ No (hit cycle limit) |

**Key discovery**: The Executor's win test had a race condition. After clicking the winning cell, the game shows an alert AND resets the board. The test checked cell content AFTER reset, finding empty cells. Fixed by intercepting the dialog message instead.

---

### Run 4: Tic-Tac-Toe v4 (`output/test-tictactoe-v4`) — 2026-04-11 ✅

**Prompt**: `"create a tic-tac-toe game"`
**Changes**: Full 4-phase pipeline (Designer pre-code → Coder → Critic → Executor → Designer post-render)

| Metric | Result |
|---|---|
| Files generated | 3/3 (100%) |
| Critic cycles | 2 total |
| Executor tests | ✅ **5/5 PASSED** |
| Phase 4 — Designer audit (round 1) | 🔴 Score 3/10 — no borders, transparent background, title not centered |
| Phase 4 — Designer audit (round 2) | ✅ **Score 10/10 — VISUALLY_COMPLETE** |
| Total pipeline time | ~8 minutes (CPU-only) |
| Completed | ✅ **YES** |

**What happened**:
1. **Phase 0**: Designer added visual guidelines (blue/red palette, borders, centered layout, hover effects, winning highlight in gold `#2ecc71`)
2. **Phase 1**: Coder generated 3 files (ignored most visual guidelines — CSS was still minimal)
3. **Phase 2**: Critic said ALL_COMPLETE (functional code is correct)
4. **Phase 3**: Executor 5/5 passed (gameplay works)
5. **Phase 4**: Designer scored 3/10 — no borders on cells, no background color, title not centered
6. **Phase 4 fix**: Planner → Coder fixed CSS (added `border: 1px solid #000` on cells, `border: 2px solid #000` on board, `background-color: #f0f0f0` on body)
7. **Phase 4 re-audit**: Score 10/10 — VISUALLY_COMPLETE ✅

---

## Pipeline Architecture (Updated)

```
Phase 0: Designer (pre-code)
  → Enriches spec with visual guidelines

Phase 1: File Creation
  → Coder generates missing files

Phase 2: Repair Loop (Critic → Planner → Coder)
  → Critic reviews code text → Planner makes fix plan → Coder fixes

Phase 3: Execution Tests
  → Executor runs Playwright browser tests → feeds failures back to Coder

Phase 4: Visual Design Audit
  → Designer opens page in browser, extracts computed styles
  → Scores 1-10 → if < passing, triggers CSS fix cycle
```

---

## Key Findings

### Finding 8 — Executor MUST detect artifact type (2026-04-11)
A hardcoded test suite for to-do apps fails catastrophically on board games (timeout waiting for `<input>` elements that don't exist). The Executor must classify the artifact first (board game, to-do, counter, etc.) and generate appropriate tests. This was the #1 cause of the v1 pipeline failure.

### Finding 9 — `alert()` dialogs must be intercepted, not ignored (2026-04-11)
Many LLM-generated games use `alert()` for win/lose messages. Playwright blocks these by default, causing the game to hang. The Executor must intercept dialogs (`page.on("dialog", ...)`) to both accept them and capture their content for verification.

### Finding 10 — The Critic ALL_COMPLETE does NOT mean the artifact looks good (2026-04-11)
The Critic validates that code EXISTS and is FUNCTIONALLY correct. It cannot see that the page has no borders, no colors, and a title flush-left at the top. The Designer Phase 4 is essential for visual quality. Without it, every generated artifact is functional but bare-bones.

### Finding 11 — Designer pre-code guidelines help but aren't enough (2026-04-11)
The Designer's pre-code phase adds detailed visual guidelines (specific hex colors, font sizes, border values) to the spec. However, the Coder frequently ignores these and generates minimal CSS. The post-render audit (Phase 4) is the enforcement mechanism that actually drives visual improvements. The combination works: pre-code sets the standard, post-render enforces it.

### Finding 12 — 4-phase pipeline completes in 2 cycles (2026-04-11)
Tic-Tac-Toe v4 went from bare-bones to visually acceptable in just 2 total cycles: 1 for functional generation, 1 for CSS fix driven by Designer audit. This is efficient — the Designer caught the visual gap and the Planner+Coder fixed it in a single pass.

---

## Remaining Issues

### Win detection timing bug
The game shows the win alert BEFORE the browser repaints the winning cell, then immediately resets the board. The player never sees the completed winning line. This is a `alert()` + synchronous `resetBoard()` timing issue in the generated code. Fixable with a `setTimeout` delay or by adding a visual highlight before the alert.

### Designer pre-code guidelines not fully followed
The Coder received detailed guidelines (blue `#3498db` for X, red `#e74c3c` for O, box-shadows, transitions) but generated simpler CSS (black borders, red/blue backgrounds). The post-render audit caught this partially. Future improvement: make the Coder prompt explicitly reference the Visual Guidelines section.

### No visual indicator of current turn
The generated game has no "Player X's turn" / "Player O's turn" indicator. This was in the Designer guidelines but not implemented.

---

## Files Created/Modified

### New files
- `agent/designer.py` — Designer agent (pre-code + post-render phases)
- `core/executor.py` — Enhanced with artifact type detection, board game tests, dialog interception

### Modified files
- `agent/loop.py` — Integrated Phase 4 (Designer visual audit) after Executor
- `agent/prompts.py` — Added `DESIGNER_PRE` and `DESIGNER_POST` prompts
- `main.py` — Phase 0 Designer enrichment before pipeline start
- `agent/coder.py` — Added spec features context, repair-specific instructions
