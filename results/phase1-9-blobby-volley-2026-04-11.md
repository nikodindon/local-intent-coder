# Phase 1.9 — Blobby Volley Pipeline Stress Test (2026-04-11)

## Question
*Can the Intent Engine pipeline generate a playable Blobby Volley game (player vs CPU, physics, sounds, scoring) autonomously using Qwen2.5-Coder-7B on CPU-only inference?*

## Objective
Not just "does it complete" but **"where does it break and why?"** — detailed monitoring of every step to identify pipeline weaknesses at higher complexity levels.

---

## Pipeline Improvements Applied

### 1. Max 3 files rule (Architect prompt)
**Before**: Architect produced 5 files (index.html, styles.css, game.js, audio.js, constants.js)
**After**: Explicit rule — "MAXIMUM 3 FILES — index.html, styles.css, game.js. ALL JavaScript logic in a SINGLE game.js file"
**Result**: ✅ Architect now produces exactly 3 files consistently

### 2. 5000 tokens for .js files (Coder)
**Before**: max_out_tokens = 3000 for all files → game.js truncated mid-generation
**After**: `file_max_tokens = max(config["max_out_tokens"], 5000)` for `.js` files
**Result**: ✅ game.js generated complete (3,538 chars vs previously truncated at ~1,200 chars)

### 3. Side-by-side layout specification (Architect + Designer prompts)
**Before**: LLM defaulted to top-vs-bottom Pong layout (CPU at top, player at bottom)
**After**: 
- Architect: "Player 1 on LEFT, Player 2/CPU on RIGHT. Both sit on GROUND. Net in CENTER."
- Designer pre-code: "Player 1 semicircle on LEFT, Player 2/CPU semicircle on RIGHT"
**Result**: ⚠️ Partially works — Architect describes it correctly, but CSS/JS often still produce Pong layout

### 4. HTTP timeout increased (llm.py)
**Before**: 120s timeout → game.js responses (>6 min) were killed
**After**: 300s timeout
**Result**: ✅ No more mid-stream disconnections

### 5. Critic setTimeout check (prompts.py)
**Before**: Critic didn't check for synchronous alert() → win timing bug passed review
**After**: "CRITICAL GAME LOGIC CHECK — verify win/end alerts use setTimeout"
**Result**: ✅ Critic correctly validates async alert pattern

### 6. File mapper CSS keywords expanded (planner.py)
**Before**: "layout is not side-by-side" → mapped to index.html instead of styles.css
**After**: Added keywords: `layout`, `positioning`, `centered`, `top/bottom/left/right:\d`, `semicircle`, `width`, `height`, `spacing`, `visual style`, `appearance`
**Result**: Pending verification (added mid-run)

### 7. Detailed logging with timestamps (loop.py, main.py)
**Before**: No timing data, hard to identify bottlenecks
**After**: Every phase, cycle, and file generation has ⏱️ timing + session auto-save
**Result**: ✅ Full observability — can tail log in real-time

---

## Run Data (First Complete Run)

### Phase 0 — Architecture & Design
| Step | Tokens | Time | Output Quality |
|---|---|---|---|
| Architect | 583 in → ~1500 out | 63.8s | ✅ 3 files, correct features |
| Designer pre-code | 713 in → ~1200 out | 174.3s | ✅ Good visual guidelines |

### Phase 1 — File Creation
| File | Tokens | Time | Size | Quality |
|---|---|---|---|---|
| index.html | 973 in → ~1000 out | 69.7s | 623 chars | ✅ Correct structure |
| styles.css | 1127 in → ~1000 out | 157.8s | 1,004 chars | ⚠️ Pong layout, not Volley |
| game.js | 1385 in → ~3500 out | 384.5s | 3,538 chars | ⚠️ Uses Canvas, DOM elements unused; mouse control wrong axis; basic AI |
| **Total Phase 1** | | **612.0s (10.2 min)** | 5,165 chars | |

### Phase 2 — Repair Loop
| Cycle | Step | Time | Outcome |
|---|---|---|---|
| 1 | Critic | 178.8s | ✅ Found 3/7 issues (layout, mouse, AI) |
| 1 | Planner | 70.4s | ⚠️ Wrong file target (index.html for CSS issue) |
| 1 | Fix index.html | 120.3s | ❌ No actual change (same output as before) |
| 1 | Fix game.js | 471.9s | ⚠️ Still wrong axis (clientY instead of clientX) |
| 1 | **Cycle total** | **841.4s (14.0 min)** | Issues not resolved |
| 2 | Critic | ~180s | ❌ Same 3 issues still present |

### Key Finding: The Coder Repeats the Same Bug
**Issue**: Critic says "Player 1 controlled by mouse horizontal movement" → Coder produces `event.clientY` (vertical) instead of `event.clientX` (horizontal).
**Root Cause**: The Coder doesn't "see" the specific axis correction in the fix reason. It reads the full snapshot and generates similar code to what was already there.
**Impact**: Each cycle takes 14 minutes but doesn't actually fix the core bugs.

---

## Timing Breakdown (CPU-only Qwen2.5-Coder-7B)
| Operation | Avg Time | % of Total |
|---|---|---|
| Architect | 64s | 4% |
| Designer pre-code | 174s | 11% |
| index.html generation | 70s | 5% |
| styles.css generation | 158s | 10% |
| game.js generation | 385s | 25% |
| Critic review | 179s | 12% |
| Planner | 70s | 5% |
| Coder fix (JS file) | 472s | 31% |
| **Full cycle (1 fix)** | **~841s** | **55%** |

**Total for 1 creation phase + 1 repair cycle: ~25 min**
**Estimated for 5 cycles: ~70 min**

---

## Conclusions

### ✅ What Works Well
1. **Architect produces correct specs** — 3 files, clear features, layout description
2. **Designer adds useful guidelines** — colors, layout, feedback
3. **Critic identifies real bugs** — layout mismatch, wrong input axis, missing AI
4. **setTimeout pattern is respected** — win timing bug caught by new Critic check
5. **File generation is reliable** — no parsing failures, proper <tool> format
6. **Logging is comprehensive** — full observability of every step

### ❌ What Doesn't Work
1. **CSS ignores Visual Guidelines** — Designer says "semicircles on ground" → CSS produces "centered circles"
2. **Coder can't fix axis bugs** — "horizontal movement" → still generates clientY
3. **Planner targets wrong files** — "layout is wrong" → index.html instead of styles.css
4. **Repair cycles are too slow** — 14 min per cycle, issues often persist
5. **Canvas vs DOM mismatch** — game.js uses `<canvas>` but HTML has `<div>` elements

### 🔧 Recommended Improvements (Priority Order)
1. **Force DOM-based rendering** — Tell Coder in prompt: "Use DOM elements, NOT canvas"
2. **Strengthen CSS enforcement** — Designer guidelines should be prefixed with "MUST" in CSS context
3. **Better file routing** — The CSS keyword expansion should help, but consider explicit file tags in issue descriptions
4. **Reduce cycles** — Focus on getting Phase 1 right rather than relying on repair loops
5. **Add explicit control spec** — "player1.x = event.clientX" should be in the Visual Guidelines

---

## Next Steps
1. Apply Canvas→DOM fix in Coder prompt
2. Re-run with max 5 cycles to observe completion boundary
3. Measure final artifact quality vs. time invested
4. Compare compression ratio with previous runs
