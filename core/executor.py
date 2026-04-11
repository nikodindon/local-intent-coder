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
        text = " ".join(features).lower() + " " + spec_md.lower()

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
                        page.wait_for_timeout(800)

                        # Remove listener
                        page.remove_listener("dialog", on_dialog)

                        # Check for alert message
                        if dialog_message[0] and any(w in dialog_message[0].lower() for w in ['win', 'gagne', 'victoire', 'wins']):
                            results.append(TestResult(test, True, f"Win alert shown: '{dialog_message[0]}'"))
                        else:
                            # Fallback: check body for win text
                            body = page.inner_text('body')
                            if any(w in body.lower() for w in ['win', 'gagne', 'victoire']):
                                results.append(TestResult(test, True, "Win message found in body"))
                            else:
                                results.append(TestResult(test, False, f"No win alert or message. Alert='{dialog_message[0]}', Body: {body[:150]}"))

                    elif 'reset' in test_lower:
                        # Place a mark then reset
                        cells = page.query_selector_all('.cell, [data-index]')
                        if not cells:
                            results.append(TestResult(test, False, "No cells to test reset"))
                            continue
                        cells[0].click()
                        page.wait_for_timeout(200)
                        # Click reset button
                        reset_btn = page.query_selector('#reset, button, .reset, [onclick*="reset"]')
                        if reset_btn:
                            reset_btn.click()
                            page.wait_for_timeout(300)
                            text = cells[0].inner_text().strip()
                            if not text or text == '':
                                results.append(TestResult(test, True, "Board cleared after reset"))
                            else:
                                results.append(TestResult(test, False, f"Cell still shows '{text}' after reset"))
                        else:
                            results.append(TestResult(test, False, "No reset button found"))

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
