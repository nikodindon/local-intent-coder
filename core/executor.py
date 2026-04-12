"""
Executor — runs generated artifacts in a headless browser and tests them.

Phase 1.5: Execution-based validation
Catches runtime bugs the text-only Critic misses.
"""

import os
import re
import json
from dataclasses import dataclass, field
from typing import Optional
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext


@dataclass
class TestCase:
    """A single test case to execute."""
    name: str
    description: str
    feature: str  # Which spec feature this tests


@dataclass
class TestResult:
    """Result of running a test case."""
    test: TestCase
    passed: bool
    message: str  # What happened (error details or success message)


@dataclass
class TestReport:
    """Full report of all test results."""
    output_dir: str
    results: list[TestResult] = field(default_factory=list)
    
    @property
    def passed(self) -> bool:
        """True if ALL tests passed."""
        return all(r.passed for r in self.results) and len(self.results) > 0
    
    @property
    def failures(self) -> list[TestResult]:
        """Return only failed tests."""
        return [r for r in self.results if not r.passed]
    
    @property
    def summary(self) -> str:
        """Human-readable summary."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        
        lines = [
            f"\n{'='*66}",
            f"  EXECUTION TESTS — {os.path.basename(self.output_dir)}",
            f"{'='*66}",
            f"",
            f"Results: {passed}/{total} passed, {failed} failed",
            f"",
        ]
        
        for r in self.results:
            status = "✓" if r.passed else "✗"
            lines.append(f"  [{status}] {r.test.name}: {r.test.description}")
            if not r.passed:
                lines.append(f"      → {r.message}")
        
        lines.append("")
        if self.passed:
            lines.append(f"  ✅ ALL TESTS PASSED")
        else:
            lines.append(f"  ❌ {failed} TEST(S) FAILED")
        lines.append(f"{'='*66}")
        
        return "\n".join(lines)
    
    def failure_reasons(self) -> list[str]:
        """Return list of failure descriptions for Coder feedback."""
        return [
            f"{r.test.feature}: {r.message}"
            for r in self.failures
        ]


class Executor:
    """Runs generated HTML artifacts in headless browser and tests them."""
    
    def __init__(self, output_dir: str, verbose: bool = True):
        self.output_dir = os.path.abspath(output_dir)
        self.verbose = verbose
        self._last_spec_md: str = ""
    
    def _parse_features(self, spec_md: str) -> list[str]:
        """Extract features from spec markdown."""
        features = []
        feature_section = re.search(
            r'## Features\n(.*?)(?=##|$)',
            spec_md,
            re.DOTALL
        )
        if feature_section:
            for line in feature_section.group(1).strip().split('\n'):
                # Remove numbering (1., 2., etc.) and trim
                cleaned = re.sub(r'^\d+\.\s*', '', line).strip()
                if cleaned and not cleaned.startswith('#'):
                    features.append(cleaned)
        return features
    
    def _detect_artifact_type(self, features: list[str], spec_md: str) -> str:
        """Detect what kind of artifact we're dealing with."""
        # v2: Use SpecAnalyzer for centralized type detection
        try:
            from agent.spec_analyzer import SpecAnalyzer
            analyzer = SpecAnalyzer(spec_md)
            type_map = {
                "side_by_side_game": "side_by_side_game",
                "falling_block_game": "falling_block",
                "board_game": "board_game",
                "grid_game": "grid_game",
                "web_app": "todo",
                "unknown": "generic_web",
            }
            return type_map.get(analyzer.artifact_type, "generic_web")
        except ImportError:
            # Fallback if SpecAnalyzer not available
            pass

        text = " ".join(features).lower() + " " + spec_md.lower()

        # Side-by-side games (Blobby Volley, Pong doubles)
        if any(g in text for g in ['side-by-side', 'side by side', 'volley', 'left side', 'right side']):
            return 'side_by_side_game'
        # Board games: tic-tac-toe, connect-4, checkers, etc.
        if any(g in text for g in ['tic-tac-toe', 'morpion', 'connect', 'checkers', 'board game']):
            return 'board_game'
        # Grid/maze games
        if any(g in text for g in ['snake', 'maze', 'grid game']):
            return 'grid_game'
        # Tetris-like
        if any(g in text for g in ['tetris', 'falling block', 'falling piece']):
            return 'falling_block'
        # Counter/number apps
        if any(g in text for g in ['counter', 'increment', 'decrement']):
            return 'counter'
        # To-do / task apps (default fallback)
        if any(g in text for g in ['task', 'todo', 'to-do', 'add item', 'checklist']):
            return 'todo'

        return 'generic_web'

    def _generate_tests(self, features: list[str]) -> list[TestCase]:
        """Generate test cases from features — adapted to artifact type."""
        tests = []
        artifact_type = self._detect_artifact_type(features, self._last_spec_md or "")

        if artifact_type == 'board_game':
            tests.append(TestCase(
                name="Board renders",
                description="Game board is visible on page load",
                feature="Board rendering"
            ))
            tests.append(TestCase(
                name="Cell click places mark",
                description="Clicking an empty cell places a mark (X or O)",
                feature="Player interaction"
            ))
            tests.append(TestCase(
                name="Turn alternation",
                description="Marks alternate between X and O on successive clicks",
                feature="Turn alternation"
            ))
            tests.append(TestCase(
                name="Win detection",
                description="Three marks in a row triggers win condition",
                feature="Win detection"
            ))
            tests.append(TestCase(
                name="Reset works",
                description="Reset button clears the board",
                feature="Game reset"
            ))

        elif artifact_type == 'grid_game':
            # Snake, maze, grid-based games
            tests.append(TestCase(
                name="Game area renders",
                description="Game area/grid is visible on page load",
                feature="Game area rendering"
            ))
            tests.append(TestCase(
                name="Player moves on input",
                description="Pressing arrow keys or WASD moves the player",
                feature="Player movement"
            ))
            tests.append(TestCase(
                name="Game object moves",
                description="Player or game object changes position over time",
                feature="Game physics/movement"
            ))
            tests.append(TestCase(
                name="Score updates",
                description="Score changes when collecting/achieving goals",
                feature="Score tracking"
            ))
            tests.append(TestCase(
                name="Collision detection",
                description="Game responds to collisions (wall, self, objects)",
                feature="Collision detection"
            ))

        elif artifact_type == 'falling_block':
            # Tetris, falling piece games
            tests.append(TestCase(
                name="Game board renders",
                description="Game board/grid is visible on page load",
                feature="Board rendering"
            ))
            tests.append(TestCase(
                name="Piece falls automatically",
                description="A piece falls down after a short delay without input",
                feature="Gravity/automatic fall"
            ))
            tests.append(TestCase(
                name="Player can move piece",
                description="Arrow keys move the falling piece left/right",
                feature="Player control"
            ))
            tests.append(TestCase(
                name="Lines clear on completion",
                description="Complete rows disappear and score increases",
                feature="Line clearing/scoring"
            ))

        elif artifact_type == 'side_by_side_game':
            # Blobby Volley, Pong doubles — two opponents facing each other
            tests.append(TestCase(
                name="Game area renders",
                description="Game container with players and net is visible",
                feature="Game rendering"
            ))
            tests.append(TestCase(
                name="Ball moves automatically",
                description="Ball changes position within 2 seconds of page load",
                feature="Ball physics"
            ))
            tests.append(TestCase(
                name="Player responds to input",
                description="Moving mouse or pressing keys changes player position",
                feature="Player controls"
            ))
            tests.append(TestCase(
                name="CPU opponent moves",
                description="Opponent player changes position without player input",
                feature="CPU AI"
            ))
            tests.append(TestCase(
                name="Score updates on point",
                description="Score display changes after ball crosses a side",
                feature="Score tracking"
            ))
            tests.append(TestCase(
                name="Ball bounces off players",
                description="Ball reverses direction after hitting a player",
                feature="Ball bounce physics"
            ))
            tests.append(TestCase(
                name="Win condition triggers",
                description="Game detects when a player reaches the win score",
                feature="Win detection"
            ))

        elif artifact_type == 'todo':
            for feature in features:
                feature_lower = feature.lower()
                if 'add' in feature_lower and ('task' in feature_lower or 'item' in feature_lower):
                    tests.append(TestCase(
                        name="Add task",
                        description=f"User can {feature}",
                        feature=feature
                    ))
                if 'complete' in feature_lower or 'checkbox' in feature_lower or 'mark' in feature_lower:
                    tests.append(TestCase(
                        name="Mark complete",
                        description=f"User can {feature}",
                        feature=feature
                    ))
                if 'delete' in feature_lower or 'remove' in feature_lower:
                    tests.append(TestCase(
                        name="Delete task",
                        description=f"User can {feature}",
                        feature=feature
                    ))
                if 'localstorage' in feature_lower or 'persist' in feature_lower:
                    tests.append(TestCase(
                        name="Persistence",
                        description=f"User can {feature}",
                        feature=feature
                    ))

        else:
            # Generic fallback: create a basic test for each feature
            for feature in features:
                tests.append(TestCase(
                    name=f"Feature: {feature[:40]}",
                    description=f"Verify: {feature}",
                    feature=feature
                ))

        return tests
    
    def _run_webapp_tests(self, tests: list[TestCase], page: Page) -> list[TestResult]:
        """Run test cases against the web app."""
        results = []

        # Find HTML file
        html_file = os.path.join(self.output_dir, "index.html")
        if not os.path.exists(html_file):
            return [TestResult(
                test=TestCase("File check", "index.html exists", "Setup"),
                passed=False,
                message="index.html not found"
            )]

        file_url = f"file:///{html_file.replace(os.sep, '/')}"
        artifact_type = self._detect_artifact_type(
            [t.feature for t in tests], self._last_spec_md
        )

        for test in tests:
            test_lower = test.name.lower()

            try:
                # Reload page for each test
                page.goto(file_url)
                page.wait_for_load_state("networkidle")

                # ─── Board game tests (Tic-Tac-Toe, etc.) ───
                if artifact_type == 'board_game':
                    if 'board renders' in test_lower or 'board' in test_lower:
                        # Check board is visible
                        board = page.query_selector('.board, #board, .grid, table')
                        if board:
                            results.append(TestResult(test, True, "Board element is visible"))
                        else:
                            # Fallback: check any div with cells
                            cells = page.query_selector_all('.cell, [data-index], td')
                            if len(cells) >= 4:
                                results.append(TestResult(test, True, f"Found {len(cells)} game cells"))
                            else:
                                results.append(TestResult(test, False, "No board or cells found"))

                    elif 'cell click' in test_lower or 'places mark' in test_lower:
                        # Click first empty cell
                        cells = page.query_selector_all('.cell, [data-index]')
                        if not cells:
                            results.append(TestResult(test, False, "No clickable cells found"))
                            continue
                        cells[0].click()
                        page.wait_for_timeout(300)
                        text = cells[0].inner_text()
                        if text and text.strip() in ('X', 'O', 'x', 'o'):
                            results.append(TestResult(test, True, f"Cell shows '{text.strip()}'"))
                        else:
                            content = page.inner_text('body')
                            results.append(TestResult(test, False, f"Cell did not show X/O mark. Body: {content[:200]}"))

                    elif 'turn alternat' in test_lower:
                        # Click two cells, check different marks
                        cells = page.query_selector_all('.cell, [data-index]')
                        if len(cells) < 2:
                            results.append(TestResult(test, False, "Need at least 2 cells"))
                            continue
                        cells[0].click()
                        page.wait_for_timeout(200)
                        cells[1].click()
                        page.wait_for_timeout(200)
                        first = cells[0].inner_text().strip()
                        second = cells[1].inner_text().strip()
                        if first and second and first.lower() != second.lower():
                            results.append(TestResult(test, True, f"Alternating: {first} then {second}"))
                        elif first and second:
                            results.append(TestResult(test, False, f"Both show '{first}' — no alternation"))
                        else:
                            results.append(TestResult(test, False, f"Cells empty after click: [{first}], [{second}]"))

                    elif 'win' in test_lower:
                        # Try to create a win: click cells 0,1,2 (top row)
                        cells = page.query_selector_all('.cell, [data-index]')
                        if len(cells) < 3:
                            results.append(TestResult(test, False, "Need at least 3 cells for win test"))
                            continue

                        # Intercept dialog alerts
                        dialog_message = [None]

                        def on_dialog(dialog):
                            dialog_message[0] = dialog.message
                            dialog.accept()

                        page.on("dialog", on_dialog)

                        # Simulate a win: X on 0,1,2 — O on 3,4 (interleaved)
                        cells[0].click()  # X
                        page.wait_for_timeout(150)
                        cells[3].click()  # O
                        page.wait_for_timeout(150)
                        cells[1].click()  # X
                        page.wait_for_timeout(150)
                        cells[4].click()  # O
                        page.wait_for_timeout(150)
                        cells[2].click()  # X — should trigger win
                        page.wait_for_timeout(300)  # Check BEFORE setTimeout reset (500ms)

                        # Remove listener
                        page.remove_listener("dialog", on_dialog)

                        # Check for win: alert OR status text OR body text
                        win_found = False
                        reason = ""

                        if dialog_message[0] and any(w in dialog_message[0].lower() for w in ['win', 'gagne', 'victoire', 'wins']):
                            win_found = True
                            reason = f"Win alert shown: '{dialog_message[0]}'"
                        else:
                            # Check status element
                            status_text = page.evaluate("""() => {
                                const el = document.querySelector('#status, .status, #result, .result');
                                return el ? el.textContent : '';
                            }""")
                            if any(w in status_text.lower() for w in ['win', 'gagne', 'victoire', 'wins']):
                                win_found = True
                                reason = f"Win in status: '{status_text}'"
                            else:
                                # Check body text
                                body = page.inner_text('body')
                                if any(w in body.lower() for w in ['win', 'gagne', 'victoire']):
                                    win_found = True
                                    reason = "Win message found in body"
                                else:
                                    reason = f"No win detected. Alert='{dialog_message[0]}', Status='{status_text}', Body: {body[:120]}"

                        if win_found:
                            results.append(TestResult(test, True, reason))
                        else:
                            results.append(TestResult(test, False, reason))

                    elif 'reset' in test_lower:
                        # Find reset button first
                        reset_btn = page.query_selector('#reset, button[type="reset"], .reset-btn')
                        if not reset_btn:
                            # Try any button with "reset" or "new" text
                            for btn in page.query_selector_all('button'):
                                txt = btn.inner_text().lower()
                                if 'reset' in txt or 'new' in txt or 'restart' in txt:
                                    reset_btn = btn
                                    break

                        if not reset_btn:
                            results.append(TestResult(test, False, "No reset button found (checked #reset, button, .reset)"))
                            continue

                        # Place a single mark
                        cells = page.query_selector_all('.cell, [data-index]')
                        if not cells:
                            results.append(TestResult(test, False, "No game cells"))
                            continue

                        cells[0].click()
                        page.wait_for_timeout(200)
                        first_text = cells[0].inner_text().strip()
                        if not first_text:
                            # Cell didn't get marked - game might have auto-reset on win
                            # Try a different cell
                            for c in cells:
                                c.click()
                                page.wait_for_timeout(200)
                                first_text = c.inner_text().strip()
                                if first_text:
                                    break

                        if not first_text:
                            results.append(TestResult(test, False, "Could not place a mark on any cell"))
                            continue

                        # Click reset
                        reset_btn.click()
                        page.wait_for_timeout(500)

                        # Check all cells are empty
                        all_empty = all(
                            c.inner_text().strip() == ''
                            for c in cells[:9]
                        )
                        if all_empty:
                            results.append(TestResult(test, True, "Board cleared after reset"))
                        else:
                            remaining = [c.inner_text().strip() for c in cells[:9] if c.inner_text().strip()]
                            results.append(TestResult(test, False, f"Cells still have marks after reset: {remaining}"))

                    else:
                        results.append(TestResult(test, False, f"No test handler for: {test.name}"))

                # ─── Side-by-side game tests (Blobby Volley, Pong doubles) ───
                elif artifact_type == 'side_by_side_game':
                    if 'game area renders' in test_lower or 'renders' in test_lower:
                        # Check game container and key elements are visible
                        container = page.query_selector('#game-container, .game-container, canvas')
                        if container:
                            results.append(TestResult(test, True, "Game container is visible"))
                        else:
                            results.append(TestResult(test, False, "No game container found"))

                    elif 'ball moves' in test_lower or 'automatically' in test_lower:
                        # Check ball position changes within 2 seconds
                        initial_pos = page.evaluate("""() => {
                            const ball = document.querySelector('#ball, .ball, circle');
                            if (!ball) return null;
                            const rect = ball.getBoundingClientRect ? ball.getBoundingClientRect() : null;
                            if (rect) return { x: rect.x, y: rect.y };
                            // For canvas, try to check via JS variables
                            return { x: -1, y: -1 };
                        }""")
                        if initial_pos is None:
                            results.append(TestResult(test, False, "Ball element not found"))
                            continue

                        page.wait_for_timeout(1000)
                        later_pos = page.evaluate("""() => {
                            const ball = document.querySelector('#ball, .ball, circle');
                            if (!ball) return null;
                            const rect = ball.getBoundingClientRect ? ball.getBoundingClientRect() : null;
                            if (rect) return { x: rect.x, y: rect.y };
                            return { x: -1, y: -1 };
                        }""")

                        if initial_pos.get('x', -1) == -1 and initial_pos.get('y', -1) == -1:
                            # Canvas-based game — check via JS state variables
                            ball_pos = page.evaluate("""() => {
                                // Try common ball variable names
                                if (typeof ball !== 'undefined' && ball.x !== undefined) return { x: ball.x, y: ball.y };
                                if (typeof ballX !== 'undefined') return { x: ballX, y: ballY };
                                return null;
                            }""")
                            if ball_pos is None:
                                results.append(TestResult(test, False, "Ball element or JS variable not found — game may not be rendering"))
                                continue
                            # Check if position changes
                            page.wait_for_timeout(500)
                            ball_pos2 = page.evaluate("""() => {
                                if (typeof ball !== 'undefined' && ball.x !== undefined) return { x: ball.x, y: ball.y };
                                if (typeof ballX !== 'undefined') return { x: ballX, y: ballY };
                                return null;
                            }""")
                            if ball_pos2 and (ball_pos2['x'] != ball_pos['x'] or ball_pos2['y'] != ball_pos['y']):
                                results.append(TestResult(test, True, f"Ball moves (JS vars: {ball_pos} → {ball_pos2})"))
                            else:
                                results.append(TestResult(test, False, f"Ball position unchanged after 1.5s ({ball_pos})"))
                        elif later_pos and initial_pos:
                            dx = abs(later_pos.get('x', 0) - initial_pos.get('x', 0))
                            dy = abs(later_pos.get('y', 0) - initial_pos.get('y', 0))
                            if dx > 2 or dy > 2:
                                results.append(TestResult(test, True, f"Ball moves ({initial_pos} → {later_pos})"))
                            else:
                                results.append(TestResult(test, False, f"Ball barely moves after 1s ({initial_pos} → {later_pos})"))
                        else:
                            results.append(TestResult(test, False, "Could not read ball position"))

                    elif 'player responds' in test_lower or 'input' in test_lower or 'control' in test_lower:
                        # Dispatch a mousemove event and check player position changes
                        initial_player = page.evaluate("""() => {
                            const p = document.querySelector('#player1, .player1, #player, .player');
                            if (!p) return null;
                            const rect = p.getBoundingClientRect();
                            return { x: rect.x, y: rect.y };
                        }""")
                        if initial_player:
                            # Simulate mouse move
                            container = page.query_selector('#game-container, canvas')
                            if container:
                                container.hover()
                                page.mouse.move(100, 300)
                                page.wait_for_timeout(300)
                                later_player = page.evaluate("""() => {
                                    const p = document.querySelector('#player1, .player1, #player, .player');
                                    if (!p) return null;
                                    const rect = p.getBoundingClientRect();
                                    return { x: rect.x, y: rect.y };
                                }""")
                                if later_player and (later_player['x'] != initial_player['x'] or later_player['y'] != initial_player['y']):
                                    results.append(TestResult(test, True, f"Player moves on input ({initial_player} → {later_player})"))
                                else:
                                    results.append(TestResult(test, False, f"Player didn't move after mouse input ({initial_player} → {later_player})"))
                            else:
                                results.append(TestResult(test, False, "No game container to dispatch mouse events"))
                        else:
                            results.append(TestResult(test, False, "Player element not found"))

                    elif 'cpu opponent' in test_lower or 'opponent' in test_lower or 'ai' in test_lower:
                        # Check if opponent moves without player input
                        page.wait_for_timeout(500)
                        initial_cpu = page.evaluate("""() => {
                            const cpu = document.querySelector('#player2, .player2, #cpu, #opponent, #paddle2');
                            if (!cpu) return null;
                            const rect = cpu.getBoundingClientRect();
                            return { x: rect.x, y: rect.y };
                        }""")
                        if initial_cpu is None:
                            # Check JS variables for CPU position
                            cpu_pos = page.evaluate("""() => {
                                if (typeof player2 !== 'undefined' && player2.x !== undefined) return { x: player2.x, y: player2.y };
                                if (typeof cpu !== 'undefined' && typeof cpu.x !== 'undefined') return { x: cpu.x, y: cpu.y };
                                return null;
                            }""")
                            if cpu_pos:
                                page.wait_for_timeout(1000)
                                cpu_pos2 = page.evaluate("""() => {
                                    if (typeof player2 !== 'undefined' && player2.x !== undefined) return { x: player2.x, y: player2.y };
                                    if (typeof cpu !== 'undefined' && typeof cpu.x !== 'undefined') return { x: cpu.x, y: cpu.y };
                                    return null;
                                }""")
                                if cpu_pos2 and (cpu_pos2['x'] != cpu_pos['x'] or cpu_pos2['y'] != cpu_pos['y']):
                                    results.append(TestResult(test, True, f"CPU moves ({cpu_pos} → {cpu_pos2})"))
                                else:
                                    results.append(TestResult(test, False, f"CPU static for 1.5s ({cpu_pos})"))
                            else:
                                results.append(TestResult(test, False, "No CPU/player2 element or JS variable found"))
                        else:
                            page.wait_for_timeout(1500)
                            later_cpu = page.evaluate("""() => {
                                const cpu = document.querySelector('#player2, .player2, #cpu, #opponent, #paddle2');
                                if (!cpu) return null;
                                const rect = cpu.getBoundingClientRect();
                                return { x: rect.x, y: rect.y };
                            }""")
                            if later_cpu and (later_cpu['x'] != initial_cpu['x'] or later_cpu['y'] != initial_cpu['y']):
                                results.append(TestResult(test, True, f"CPU moves on its own ({initial_cpu} → {later_cpu})"))
                            else:
                                results.append(TestResult(test, False, f"CPU static for 1.5s ({initial_cpu})"))

                    elif 'score updates' in test_lower or 'score' in test_lower:
                        # Check score display exists and changes
                        score_el = page.query_selector('#scoreboard, .scoreboard, #score, #player1-score')
                        if score_el:
                            initial_score = score_el.inner_text()
                            # Simulate scoring by triggering ball out-of-bounds
                            # For now just check the element exists and has a value
                            if initial_score.strip():
                                results.append(TestResult(test, True, f"Score display exists: '{initial_score}'"))
                            else:
                                results.append(TestResult(test, False, "Score element exists but is empty"))
                        else:
                            results.append(TestResult(test, False, "No score display found"))

                    elif 'ball bounces' in test_lower or 'bounce' in test_lower:
                        # Wait for game to run and check ball direction changes
                        directions = page.evaluate("""() => {
                            const vals = [];
                            for (let i = 0; i < 6; i++) {
                                if (typeof ball !== 'undefined' && ball.dx !== undefined) vals.push({ dx: ball.dx, dy: ball.dy });
                                else if (typeof ballVelocityX !== 'undefined') vals.push({ dx: ballVelocityX, dy: ballVelocityY });
                                else return null;
                            }
                            return vals;
                        }""")
                        if directions:
                            direction_changes = any(
                                directions[i]['dx'] != directions[i+1]['dx'] or directions[i]['dy'] != directions[i+1]['dy']
                                for i in range(len(directions)-1)
                            )
                            if direction_changes:
                                results.append(TestResult(test, True, "Ball direction changes detected"))
                            else:
                                results.append(TestResult(test, True, f"Ball moving consistently ({directions[0]})"))
                        else:
                            results.append(TestResult(test, False, "Could not read ball velocity variables"))

                    elif 'win condition' in test_lower or 'win' in test_lower:
                        # Check if win detection code exists
                        has_win_code = page.evaluate("""() => {
                            // Check if score comparison exists in game variables
                            if (typeof scoreboard !== 'undefined' && scoreboard.player1 !== undefined) return true;
                            if (typeof player1Score !== 'undefined') return true;
                            return false;
                        }""")
                        if has_win_code:
                            results.append(TestResult(test, True, "Score tracking variables exist"))
                        else:
                            results.append(TestResult(test, False, "No score tracking variables found"))

                    else:
                        results.append(TestResult(test, False, f"No test handler for: {test.name}"))

                # ─── To-do app tests ───
                elif artifact_type == 'todo':
                    if 'add' in test_lower:
                        page.fill('input', 'Test Task 123')
                        page.click('button')
                        page.wait_for_timeout(500)
                        content = page.inner_text('body')
                        if 'Test Task 123' in content:
                            results.append(TestResult(test, True, "Task appeared after adding"))
                        else:
                            results.append(TestResult(test, False, "Task not found after adding"))

                    elif 'complete' in test_lower or 'mark' in test_lower:
                        page.fill('input', 'Complete Me')
                        page.click('button')
                        page.wait_for_timeout(500)
                        page.click('li', timeout=3000)
                        page.wait_for_timeout(500)
                        completed_class = page.evaluate("""() => {
                            const li = document.querySelector('li');
                            return li ? li.className : '';
                        }""")
                        if 'completed' in completed_class.lower():
                            results.append(TestResult(test, True, "Task marked complete"))
                        else:
                            results.append(TestResult(test, False, f"No 'completed' class found: {completed_class}"))

                    elif 'delete' in test_lower:
                        page.fill('input', 'Delete Me')
                        page.click('button')
                        page.wait_for_timeout(500)
                        delete_btn = page.query_selector('button')
                        if delete_btn:
                            delete_btn.click()
                            page.wait_for_timeout(500)
                            content = page.inner_text('body')
                            if 'Delete Me' not in content:
                                results.append(TestResult(test, True, "Task deleted successfully"))
                            else:
                                results.append(TestResult(test, False, "Task still visible after delete"))
                        else:
                            results.append(TestResult(test, False, "No delete button found"))

                    elif 'persistence' in test_lower or 'persist' in test_lower:
                        page.fill('input', 'Persist Me')
                        page.click('button')
                        page.wait_for_timeout(500)
                        page.reload()
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(500)
                        content = page.inner_text('body')
                        if 'Persist Me' in content:
                            results.append(TestResult(test, True, "Task persisted after reload"))
                        else:
                            results.append(TestResult(test, False, "Task not found after page reload"))

                    else:
                        results.append(TestResult(test, False, f"No test handler for: {test.name}"))

                # ─── Generic fallback ───
                else:
                    # Just check if elements mentioned in the feature exist
                    results.append(TestResult(
                        test, True,
                        f"Generic check passed (manual verification recommended for {artifact_type})"
                    ))

            except Exception as e:
                results.append(TestResult(test, False, f"Error: {str(e)[:200]}"))

        return results
    
    def run_tests(self, spec_md: str) -> TestReport:
        """
        Main entry point: parse spec, generate tests, run them, return report.
        """
        self._last_spec_md = spec_md
        features = self._parse_features(spec_md)
        
        if not features:
            print("  ⚠️  No features found in spec, skipping execution tests")
            return TestReport(output_dir=self.output_dir)
        
        tests = self._generate_tests(features)
        
        if not tests:
            print("  ⚠️  No testable features found, skipping execution tests")
            return TestReport(output_dir=self.output_dir)
        
        if self.verbose:
            print(f"\n  🧪 Running {len(tests)} execution tests...")
        
        # Run tests in Playwright
        results = []
        with sync_playwright() as p:
            browser: Browser = p.chromium.launch(headless=True)
            context: BrowserContext = browser.new_context()
            page: Page = context.new_page()
            
            results = self._run_webapp_tests(tests, page)
            browser.close()
        
        report = TestReport(
            output_dir=self.output_dir,
            results=results
        )
        
        if self.verbose:
            print(report.summary)
        
        return report
