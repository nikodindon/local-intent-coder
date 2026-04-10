# Phase 1.5 — Execution-Based Validation

## The Problem

The Critic can only **read** code. It cannot **run** it.

### Example: To-Do App (2026-04-10)

The Critic approved a to-do app with these features in the spec:
- ✅ Add tasks → code exists
- ✅ Mark complete → code exists  
- ✅ Delete tasks → code exists
- ✅ localStorage persistence → code exists

**Critic verdict: ALL_COMPLETE** ✅

**Reality when tested:**
- ❌ Delete buttons don't appear (created on wrong event)
- ❌ Tasks don't persist (saveTasks() never called)
- ❌ Multiple conflicting event handlers

The **code was there** but the **logic was broken**. The Critic couldn't catch it because it doesn't execute code.

## The Solution

Add an **execution layer** after the Critic that actually runs the generated artifact and tests it.

### Architecture

```
Coder generates files
    ↓
Critic reviews code (text-only)
    ↓
[NEW] Executor runs tests (browser automation)
    ↓
If tests fail → feed results to Coder as concrete errors
    ↓
Repeat until ALL_COMPLETE + all tests pass
```

### How It Works

1. **Generate test plan from spec features**
   - Parse spec's "Features" section
   - For each feature, create a test case
   - Example: "Tasks persist in localStorage" → test plan:
     ```
     1. Add task "Test 123"
     2. Close/reload page  
     3. Verify "Test 123" is still visible
     ```

2. **Execute in headless browser**
   - Use Playwright (Python) to automate browser
   - Run each test case
   - Capture pass/fail with screenshots on failure

3. **Feed results back to Coder**
   - Success: `localStorage test PASSED`
   - Failure: `localStorage test FAILED: Expected "Test 123" found 0 tasks`
   - Coder gets concrete error, not vague "fix localStorage"

4. **Loop until pass**
   - Critic says ALL_COMPLETE **AND**
   - All execution tests pass

### Test Plan Generation

For common artifact types:

**Web Apps (HTML/CSS/JS):**
- Element existence tests (h1, buttons, inputs)
- Interaction tests (click buttons, enter text)
- State tests (localStorage, DOM changes)
- Visual tests (element styles, visibility)

**Games (Tetris, Snake):**
- Element rendering (canvas, game board)
- Input handling (key presses, arrow keys)
- Game state (score, pieces, collision)
- Win/lose conditions

### Example Test Output

```
EXECUTION TESTS — To-Do App
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[✓] Test 1: Add task → element with text "Test" appears
[✓] Test 2: Mark complete → element has class "completed"  
[✗] Test 3: Delete task → no delete button found
[✗] Test 4: Persistence → 0 tasks found after refresh (expected 3)

FAILURES: 2/4 tests failed
```

## Implementation Plan

### Step 1: Add Playwright dependency
```bash
pip install playwright
playwright install chromium
```

### Step 2: Create `executor.py`
```python
class Executor:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
    
    def run_tests(self, spec_md: str) -> TestReport:
        # Parse features from spec
        # Generate test cases
        # Run in Playwright browser
        # Return pass/fail report
        pass
```

### Step 3: Integrate into loop.py
```python
# After Critic says ALL_COMPLETE
executor = Executor(session.output_dir)
test_report = executor.run_tests(session.spec_md)

if not test_report.passed():
    # Feed failures back to Coder as fix reasons
    for failed_test in test_report.failures():
        coder.write(file_to_fix, path, session, reason=failed_test.description)
```

### Step 4: Update success criteria
Phase 1 success = Critic ALL_COMPLETE + all execution tests pass

## Why This Matters for Tetris

The to-do app showed us that **LLM-generated code has logic bugs**, not just missing features. For Tetris:

- Critic can verify "collision detection code exists" ✅
- **Only execution** can verify "pieces actually stop at bottom" ✅
- Critic can verify "line clear code exists" ✅  
- **Only execution** can verify "filled lines actually disappear" ✅

Without execution testing, we'll never know if the generated Tetris actually **works** — only if the code **exists**.

## Dependencies

- `playwright` (Python browser automation)
- Chromium browser (installed via `playwright install chromium`)
- No changes to LLM server or config

## Expected Challenges

1. **Test generation** — How do we auto-generate good tests from a spec?
2. **Game testing** — How do we verify canvas rendering (Tetris board)?
3. **Flaky tests** — Browser automation can be unreliable
4. **Context size** — Test results add more tokens to Coder context

## Success Criteria

Phase 1.5 is complete when:
- [ ] Executor can test a to-do app and catch the localStorage bug
- [ ] Executor can test a simple game (Snake) and verify gameplay
- [ ] Pipeline produces artifacts that actually work when opened
- [ ] Results documented in `results/phase1-5-results.md`

## Files to Create

```
agent/
  └── executor.py         # Playwright-based test runner
core/
  └── test_report.py      # Test result dataclass
results/
  └── phase1-5-results.md # Experiment results
```
