"""
Designer agent — ensures generated artifacts look polished, not bare-bones.

Two phases:
1. DESIGNER_PRE  — Before coding: adds visual guidelines to the spec
2. DESIGNER_POST — After Executor: audits actual rendered styles via Playwright
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

        guidelines = self.client.call(messages, label="DESIGNER (PRE-CODE)", max_tokens=1200)

        if not guidelines.strip():
            print("  ⚠️  Designer pre-code produced empty output, skipping enrichment.")
            return spec_md

        # Append guidelines to spec
        enriched = spec_md.rstrip() + "\n\n## Visual Guidelines\n" + guidelines.strip()
        return enriched

    def audit_styles(self, spec_md: str, output_dir: str) -> dict:
        """
        Phase final: Open the page in Playwright, audit computed styles,
        and ask the Designer LLM to evaluate visual quality.
        Returns dict with: {score, verdict, issues, passed: bool}
        """
        from playwright.sync_api import sync_playwright

        html_file = os.path.join(os.path.abspath(output_dir), "index.html")
        if not os.path.exists(html_file):
            return {"score": 0, "verdict": "NEEDS_VISUAL_FIXES",
                    "issues": ["index.html not found"], "passed": False}

        # Extract visual guidelines from spec
        guidelines_match = re.search(
            r'## Visual Guidelines\n(.*?)(?=##|$)',
            spec_md, re.DOTALL
        )
        guidelines_text = guidelines_match.group(1).strip() if guidelines_match else "(No pre-code visual guidelines provided)"

        # Gather computed style data via Playwright
        style_audit = self._audit_computed_styles(html_file)

        # Build audit request
        audit_context = (
            f"Original visual guidelines:\n{guidelines_text}\n\n"
            f"Computed style audit of the rendered page:\n{json.dumps(style_audit, indent=2)}"
        )

        messages = [
            {"role": "system", "content": DESIGNER_POST},
            {"role": "user", "content": audit_context},
        ]

        review = self.client.call(messages, label="DESIGNER (POST-RENDER)", max_tokens=900)

        # Parse verdict
        score = 0
        score_match = re.search(r'SCORE[:\s]*(\d+)/10', review)
        if score_match:
            score = int(score_match.group(1))

        verdict = "NEEDS_VISUAL_FIXES"  # default
        if "VISUALLY_COMPLETE" in review.upper():
            verdict = "VISUALLY_COMPLETE"

        # Extract issues
        issues = []
        if verdict == "NEEDS_VISUAL_FIXES":
            # Grab lines after verdict that look like issues
            lines = review.split('\n')
            capture = False
            for line in lines:
                stripped = line.strip()
                if capture and stripped and not stripped.startswith('='):
                    issues.append(stripped)
                if 'NEEDS_VISUAL_FIXES' in stripped.upper():
                    capture = True

        return {
            "score": score,
            "verdict": verdict,
            "issues": issues[:3],  # max 3
            "review_text": review.strip(),
            "passed": verdict == "VISUALLY_COMPLETE",
        }

    def _audit_computed_styles(self, html_file: str) -> dict:
        """
        Open the HTML in headless Chromium and extract computed styles
        of key elements to give the Designer LLM concrete data.
        """
        from playwright.sync_api import sync_playwright

        audit = {
            "title": {},
            "body": {},
            "board": {},
            "cells_sample": [],
            "reset_button": {},
            "has_border_on_board": False,
            "has_border_on_cells": False,
            "has_background_color": False,
        }

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                file_url = f"file:///{html_file.replace(os.sep, '/')}"
                page.goto(file_url)
                page.wait_for_load_state("networkidle")

                # Title style
                title_style = page.evaluate("""() => {
                    const el = document.querySelector('h1, .title, #title');
                    if (!el) return { exists: false };
                    const s = getComputedStyle(el);
                    return {
                        exists: true,
                        textAlign: s.textAlign,
                        fontSize: s.fontSize,
                        fontWeight: s.fontWeight,
                        color: s.color,
                        margin: s.margin,
                    };
                }""")
                audit["title"] = title_style

                # Body style
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
                audit["has_background_color"] = (
                    body_style.get("backgroundColor", "transparent") not in
                    ("transparent", "rgba(0, 0, 0, 0)", "rgb(255, 255, 255)", "#fff", "#ffffff", "white", "")
                )

                # Board style
                board_style = page.evaluate("""() => {
                    const el = document.querySelector('.board, #board, .grid, .game-board');
                    if (!el) return { exists: false };
                    const s = getComputedStyle(el);
                    return {
                        exists: true,
                        display: s.display,
                        width: s.width,
                        margin: s.margin,
                        padding: s.padding,
                        border: s.border,
                        borderTop: s.borderTop,
                        borderRight: s.borderRight,
                        borderBottom: s.borderBottom,
                        borderLeft: s.borderLeft,
                        borderRadius: s.borderRadius,
                        boxShadow: s.boxShadow,
                        backgroundColor: s.backgroundColor,
                        gap: s.gap,
                    };
                }""")
                audit["board"] = board_style
                if board_style.get("exists"):
                    border_val = (board_style.get("border", "") +
                                  board_style.get("borderTop", "") +
                                  board_style.get("borderBottom", "") +
                                  board_style.get("borderLeft", ""))
                    audit["has_border_on_board"] = "none" not in border_val.lower() and len(border_val.strip()) > 0

                # Cell styles (sample first 3)
                cells = page.evaluate("""() => {
                    const els = document.querySelectorAll('.cell, [data-index], td');
                    if (!els.length) return [];
                    return Array.from(els).slice(0, 3).map(el => {
                        const s = getComputedStyle(el);
                        return {
                            width: s.width,
                            height: s.height,
                            border: s.border,
                            borderTop: s.borderTop,
                            borderLeft: s.borderLeft,
                            borderRadius: s.borderRadius,
                            backgroundColor: s.backgroundColor,
                            boxShadow: s.boxShadow,
                            fontSize: s.fontSize,
                            color: s.color,
                            cursor: s.cursor,
                            transition: s.transition,
                        };
                    });
                }""")
                audit["cells_sample"] = cells
                if cells:
                    for cell in cells:
                        border_val = (cell.get("border", "") +
                                      cell.get("borderTop", "") +
                                      cell.get("borderLeft", ""))
                        if "none" not in border_val.lower() and len(border_val.strip()) > 0:
                            audit["has_border_on_cells"] = True
                            break

                # Reset button style
                btn_style = page.evaluate("""() => {
                    const el = document.querySelector('#reset, button, .reset, .btn');
                    if (!el) return { exists: false };
                    const s = getComputedStyle(el);
                    return {
                        exists: true,
                        display: s.display,
                        padding: s.padding,
                        border: s.border,
                        borderRadius: s.borderRadius,
                        backgroundColor: s.backgroundColor,
                        color: s.color,
                        fontSize: s.fontSize,
                        fontWeight: s.fontWeight,
                        cursor: s.cursor,
                        margin: s.margin,
                    };
                }""")
                audit["reset_button"] = btn_style

                browser.close()
        except Exception as e:
            audit["error"] = str(e)[:300]

        return audit
