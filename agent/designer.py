"""
Designer agent — ensures generated artifacts look polished, not bare-bones.

Two phases:
1. DESIGNER_PRE  — Before coding: adds visual guidelines to the spec
2. DESIGNER_POST — After Executor: audits actual rendered styles via Playwright

v2 (2026-04-11): Fully generic — no hardcoded selectors, no game-specific
assumptions. All audit targets are derived from the spec's visual guidelines
and feature descriptions.
"""

import os
import re
import json

from core.llm import LLMClient
from agent.prompts import DESIGNER_PRE, DESIGNER_POST


class Designer:
    def __init__(self, client: LLMClient, config: dict):
        self.client = client
        self.config = config

    def enrich_spec(self, spec_md: str) -> str:
        """
        Phase 0: Add visual guidelines to the spec before coding begins.
        Returns the enriched spec (original + ## Visual Guidelines section).
        """
        messages = [
            {"role": "system", "content": DESIGNER_PRE},
            {"role": "user", "content": f"Project spec:\n\n{spec_md}"},
        ]

        guidelines = self.client.call(
            messages, label="DESIGNER (PRE-CODE)", max_tokens=1200
        )

        if not guidelines.strip():
            print(
                "  ⚠️  Designer pre-code produced empty output, skipping enrichment."
            )
            return spec_md

        # Append guidelines to spec
        enriched = (
            spec_md.rstrip() + "\n\n## Visual Guidelines\n" + guidelines.strip()
        )
        return enriched

    def audit_styles(self, spec_md: str, output_dir: str) -> dict:
        """
        Phase final: Open the page in Playwright, audit computed styles,
        and ask the Designer LLM to evaluate visual quality.

        v2: All audit targets are dynamically extracted from the spec's
        visual guidelines — no hardcoded selectors for "board", "cells", etc.

        Returns dict with: {score, verdict, issues, passed: bool}
        """
        from playwright.sync_api import sync_playwright

        # Find the HTML file dynamically
        html_file = self._find_html_file(output_dir)
        if not html_file:
            return {
                "score": 0,
                "verdict": "NEEDS_VISUAL_FIXES",
                "issues": ["No HTML file found in output directory"],
                "passed": False,
            }

        # Extract visual guidelines from spec
        guidelines_match = re.search(
            r"## Visual Guidelines\n(.*?)(?=##|$)", spec_md, re.DOTALL
        )
        guidelines_text = (
            guidelines_match.group(1).strip()
            if guidelines_match
            else "(No pre-code visual guidelines provided)"
        )

        # Extract expected elements from spec features
        expected_elements = self._extract_expected_elements(spec_md)

        # Gather computed style data via Playwright — GENERIC audit
        style_audit = self._audit_computed_styles(html_file, expected_elements)

        # Build audit context for the Designer LLM
        audit_context = (
            f"Original visual guidelines:\n{guidelines_text}\n\n"
            f"Computed style audit of the rendered page:\n{json.dumps(style_audit, indent=2)}"
        )

        messages = [
            {"role": "system", "content": DESIGNER_POST},
            {"role": "user", "content": audit_context},
        ]

        review = self.client.call(
            messages, label="DESIGNER (POST-RENDER)", max_tokens=900
        )

        # Parse verdict
        score = 0
        score_match = re.search(r"SCORE[:\s]*(\d+)/10", review)
        if score_match:
            score = int(score_match.group(1))

        verdict = "NEEDS_VISUAL_FIXES"  # default
        if "VISUALLY_COMPLETE" in review.upper():
            verdict = "VISUALLY_COMPLETE"

        # Extract issues
        issues = []
        if verdict == "NEEDS_VISUAL_FIXES":
            lines = review.split("\n")
            capture = False
            for line in lines:
                stripped = line.strip()
                if capture and stripped and not stripped.startswith("="):
                    issues.append(stripped)
                if "NEEDS_VISUAL_FIXES" in stripped.upper():
                    capture = True

        return {
            "score": score,
            "verdict": verdict,
            "issues": issues[:3],  # max 3
            "review_text": review.strip(),
            "passed": verdict == "VISUALLY_COMPLETE",
        }

    def _find_html_file(self, output_dir: str) -> str | None:
        """
        Find the main HTML file in the output directory.
        Prefers index.html, falls back to the first .html file found.
        """
        index_path = os.path.join(os.path.abspath(output_dir), "index.html")
        if os.path.exists(index_path):
            return index_path

        # Fallback: first .html file
        for fname in sorted(os.listdir(output_dir)):
            if fname.endswith(".html"):
                return os.path.join(os.path.abspath(output_dir), fname)

        return None

    def _extract_expected_elements(self, spec_md: str) -> list[str]:
        """
        Extract expected UI elements from the spec's features and visual guidelines.
        This replaces hardcoded selectors with spec-derived expectations.

        Returns a list of element descriptions like:
        ['game container', 'player indicators', 'score display', 'net/barrier', 'status indicator']
        """
        elements = []

        # Extract from Features section
        features_match = re.search(r"## Features\n(.*?)(?=##|$)", spec_md, re.DOTALL)
        if features_match:
            features_text = features_match.group(1).lower()

            # Detect common patterns and map to element types
            if any(
                kw in features_text
                for kw in ["score", "tracking", "points", "first to"]
            ):
                elements.append("score display")

            if any(
                kw in features_text
                for kw in ["player", "opponent", "cpu", "ai", "vs"]
            ):
                elements.append("player indicators")

            if any(kw in features_text for kw in ["net", "barrier", "divider", "wall"]):
                elements.append("net or barrier")

            if any(
                kw in features_text
                for kw in ["status", "turn", "state", "indicator", "message"]
            ):
                elements.append("status indicator")

            if any(
                kw in features_text
                for kw in ["ball", "piece", "projectile", "object"]
            ):
                elements.append("game object (ball/piece)")

            if any(
                kw in features_text
                for kw in ["button", "reset", "restart", "new game", "play again"]
            ):
                elements.append("action button")

            if any(kw in features_text for kw in ["title", "heading", "name"]):
                elements.append("page title")

            if any(kw in features_text for kw in ["board", "court", "field", "area"]):
                elements.append("game area")

        # Extract from Visual Guidelines
        guidelines_match = re.search(
            r"## Visual Guidelines\n(.*?)(?=##|$)", spec_md, re.DOTALL
        )
        if guidelines_match:
            guidelines_text = guidelines_match.group(1).lower()

            if "semicircle" in guidelines_text or "player 1" in guidelines_text:
                if "player indicators" not in elements:
                    elements.append("player semicircles")

            if "score display" not in elements and "score" in guidelines_text:
                elements.append("score display")

            if "net" in guidelines_text or "barrier" in guidelines_text:
                if "net or barrier" not in elements:
                    elements.append("net or barrier")

            if "background" in guidelines_text or "gradient" in guidelines_text:
                elements.append("background styling")

        # Always audit body and container as baseline
        if "game container" not in elements:
            elements.append("game container")
        if "body" not in elements:
            elements.append("page body")

        return elements

    def _audit_computed_styles(
        self, html_file: str, expected_elements: list[str]
    ) -> dict:
        """
        Open the HTML in headless Chromium and extract computed styles
        of key elements. v2: all selectors are derived from expected_elements,
        NOT hardcoded.

        Returns a dict that the Designer LLM can use to evaluate visual quality.
        """
        from playwright.sync_api import sync_playwright

        audit: dict = {
            "body": {},
            "container": {},
            "has_background": False,
            "elements": {},
        }

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                file_url = f"file:///{html_file.replace(os.sep, '/')}"
                page.goto(file_url)
                page.wait_for_load_state("networkidle")

                # ─── Body style (always audited) ───
                body_style = page.evaluate("""() => {
                    const s = getComputedStyle(document.body);
                    return {
                        display: s.display,
                        backgroundColor: s.backgroundColor,
                        margin: s.margin,
                        padding: s.padding,
                        justifyContent: s.justifyContent,
                        alignItems: s.alignItems,
                    };
                }""")
                audit["body"] = body_style
                audit["has_background"] = body_style.get(
                    "backgroundColor", "transparent"
                ) not in (
                    "transparent",
                    "rgba(0, 0, 0, 0)",
                    "rgb(255, 255, 255)",
                    "#fff",
                    "#ffffff",
                    "white",
                    "",
                )

                # ─── Main container (generic selectors) ───
                container_style = page.evaluate("""() => {
                    const el = document.querySelector(
                        '#game-container, #app, #main, .container, .game-area, .board, .court'
                    );
                    if (!el) return { exists: false, searched: '#game-container, #app, #main, .container, .game-area' };
                    const s = getComputedStyle(el);
                    return {
                        exists: true,
                        tag: el.tagName.toLowerCase(),
                        id: el.id,
                        className: el.className,
                        display: s.display,
                        width: s.width,
                        height: s.height,
                        border: s.border,
                        borderRadius: s.borderRadius,
                        boxShadow: s.boxShadow,
                        backgroundColor: s.backgroundColor,
                        background: s.background,
                        position: s.position,
                        overflow: s.overflow,
                    };
                }""")
                audit["container"] = container_style

                # ─── Audit each expected element ───
                for element_desc in expected_elements:
                    selectors = self._element_to_selectors(element_desc)
                    style_data = page.evaluate(
                        f"""(selectors) => {{
                        const el = document.querySelector(selectors);
                        if (!el) return {{ exists: false, searched: selectors }};
                        const s = getComputedStyle(el);
                        return {{
                            exists: true,
                            tag: el.tagName.toLowerCase(),
                            id: el.id,
                            className: el.className,
                            textContent: el.textContent ? el.textContent.trim().substring(0, 50) : '',
                            display: s.display,
                            width: s.width,
                            height: s.height,
                            border: s.border,
                            borderTop: s.borderTop,
                            borderLeft: s.borderLeft,
                            borderRadius: s.borderRadius,
                            boxShadow: s.boxShadow,
                            backgroundColor: s.backgroundColor,
                            background: s.background,
                            color: s.color,
                            fontSize: s.fontSize,
                            fontWeight: s.fontWeight,
                            textAlign: s.textAlign,
                            position: s.position,
                            top: s.top,
                            bottom: s.bottom,
                            left: s.left,
                            right: s.right,
                            margin: s.margin,
                            padding: s.padding,
                            opacity: s.opacity,
                            cursor: s.cursor,
                            transition: s.transition,
                            transform: s.transform,
                        }};
                    }}""",
                        selectors,
                    )
                    audit["elements"][element_desc] = style_data

                # ─── Also capture ALL buttons on page (for any action elements) ───
                buttons = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('button, [role="button"], .btn'))
                        .slice(0, 3)
                        .map(el => {{
                            const s = getComputedStyle(el);
                            return {{
                                tag: el.tagName.toLowerCase(),
                                id: el.id,
                                className: el.className,
                                text: el.textContent.trim().substring(0, 30),
                                display: s.display,
                                padding: s.padding,
                                border: s.border,
                                borderRadius: s.borderRadius,
                                backgroundColor: s.backgroundColor,
                                color: s.color,
                                fontSize: s.fontSize,
                                cursor: s.cursor,
                            }};
                        }});
                }}""")
                if buttons:
                    audit["buttons"] = buttons

                # ─── Also capture ALL headings ───
                headings = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('h1, h2, h3, .title, #title'))
                        .slice(0, 3)
                        .map(el => {{
                            const s = getComputedStyle(el);
                            return {{
                                tag: el.tagName.toLowerCase(),
                                text: el.textContent.trim().substring(0, 50),
                                fontSize: s.fontSize,
                                fontWeight: s.fontWeight,
                                color: s.color,
                                textAlign: s.textAlign,
                                margin: s.margin,
                            }};
                        }});
                }}""")
                if headings:
                    audit["headings"] = headings

                browser.close()

        except Exception as e:
            audit["error"] = str(e)[:300]

        return audit

    def _element_to_selectors(self, element_desc: str) -> str:
        """
        Convert a human-readable element description to CSS selectors.
        This is the mapping layer between spec language and DOM queries.
        """
        desc_lower = element_desc.lower()

        if "score" in desc_lower:
            return "#scoreboard, .scoreboard, #score, .score, #points, .points, #score-display, .score-display"

        if "player" in desc_lower and "indicator" in desc_lower:
            return "#player, .player, #player1, #player2, .player1, .player2, #opponent, .opponent"

        if "semicircle" in desc_lower or "player" in desc_lower:
            return "#player1, #player2, .player1, .player2, #player, .player, #paddle, .paddle"

        if "net" in desc_lower or "barrier" in desc_lower or "divider" in desc_lower:
            return "#net, .net, #barrier, .barrier, #divider, .divider, #wall, .wall"

        if "status" in desc_lower or "indicator" in desc_lower or "message" in desc_lower:
            return "#status, .status, #message, .message, #turn-indicator, .turn-indicator, #result, .result"

        if "ball" in desc_lower or "piece" in desc_lower or "object" in desc_lower:
            return "#ball, .ball, #piece, .piece, #projectile, .projectile, #puck, .puck"

        if "button" in desc_lower or "action" in desc_lower:
            return "#reset, .reset, #restart, .restart, #new-game, .new-game, button, .btn, #btn"

        if "title" in desc_lower or "heading" in desc_lower:
            return "h1, h2, .title, #title, h3"

        if "container" in desc_lower or "area" in desc_lower:
            return "#game-container, .game-container, #game-area, .game-area, #app, .app, #main, .main, #court, .court"

        if "board" in desc_lower or "court" in desc_lower or "field" in desc_lower:
            return "#board, .board, #court, .court, #field, .field, #grid, .grid, #game-board, .game-board"

        if "background" in desc_lower:
            return "body, #game-container, .game-container, #app, .app"

        # Fallback: try common patterns
        name = re.sub(r"[^a-z0-9]", "-", desc_lower).strip("-")
        return f"#{name}, .{name}, [data-{name}], #{name.replace('-', '')}, .{name.replace('-', '')}"
