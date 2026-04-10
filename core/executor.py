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
    
    def _generate_tests(self, features: list[str]) -> list[TestCase]:
        """Generate test cases from features."""
        tests = []
        
        for feature in features:
            feature_lower = feature.lower()
            
            # Add task tests
            if 'add' in feature_lower and ('task' in feature_lower or 'item' in feature_lower):
                tests.append(TestCase(
                    name="Add task",
                    description=f"User can {feature}",
                    feature=feature
                ))
            
            # Completion/checkbox tests
            if 'complete' in feature_lower or 'checkbox' in feature_lower or 'mark' in feature_lower:
                tests.append(TestCase(
                    name="Mark complete",
                    description=f"User can {feature}",
                    feature=feature
                ))
            
            # Delete tests
            if 'delete' in feature_lower or 'remove' in feature_lower:
                tests.append(TestCase(
                    name="Delete task",
                    description=f"User can {feature}",
                    feature=feature
                ))
            
            # Persistence tests
            if 'localstorage' in feature_lower or 'persist' in feature_lower:
                tests.append(TestCase(
                    name="Persistence",
                    description=f"User can {feature}",
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
        
        for test in tests:
            test_lower = test.name.lower()
            
            try:
                # Reload page for each test
                page.goto(file_url)
                page.wait_for_load_state("networkidle")
                
                # Test: Add task
                if 'add' in test_lower:
                    page.fill('input', 'Test Task 123')
                    page.click('button')
                    page.wait_for_timeout(500)
                    
                    content = page.inner_text('body')
                    if 'Test Task 123' in content:
                        results.append(TestResult(test, True, "Task appeared after adding"))
                    else:
                        results.append(TestResult(test, False, "Task not found after adding"))
                
                # Test: Mark complete
                elif 'complete' in test_lower or 'mark' in test_lower:
                    # First add a task
                    page.fill('input', 'Complete Me')
                    page.click('button')
                    page.wait_for_timeout(500)
                    
                    # Try to click (should toggle complete)
                    page.click('li', timeout=3000)
                    page.wait_for_timeout(500)
                    
                    # Check if class was added
                    completed_class = page.evaluate("""() => {
                        const li = document.querySelector('li');
                        return li ? li.className : '';
                    }""")
                    
                    if 'completed' in completed_class.lower():
                        results.append(TestResult(test, True, "Task marked complete"))
                    else:
                        results.append(TestResult(test, False, f"No 'completed' class found: {completed_class}"))
                
                # Test: Delete
                elif 'delete' in test_lower:
                    # Add task first
                    page.fill('input', 'Delete Me')
                    page.click('button')
                    page.wait_for_timeout(500)
                    
                    # Look for delete button
                    page.wait_for_selector('button', timeout=3000)
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
                
                # Test: Persistence
                elif 'persistence' in test_lower or 'persist' in test_lower:
                    # Add task
                    page.fill('input', 'Persist Me')
                    page.click('button')
                    page.wait_for_timeout(500)
                    
                    # Reload page
                    page.reload()
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(500)
                    
                    content = page.inner_text('body')
                    if 'Persist Me' in content:
                        results.append(TestResult(test, True, "Task persisted after reload"))
                    else:
                        results.append(TestResult(test, False, "Task not found after page reload"))
                
            except Exception as e:
                results.append(TestResult(test, False, f"Error: {str(e)[:200]}"))
        
        return results
    
    def run_tests(self, spec_md: str) -> TestReport:
        """
        Main entry point: parse spec, generate tests, run them, return report.
        """
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
