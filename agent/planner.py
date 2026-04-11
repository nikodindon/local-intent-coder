"""
Planner agent — converts Critic/Designer output into a minimal fix plan.

The plan is a JSON array of at most 3 actions, each referencing one file.
Multiple problems in the same file are merged into a single action.

Phase 1.7 fix: Rule-based file routing maps issues to the correct file
(CSS keywords → styles.css, DOM keywords → index.html, etc.)
to prevent infinite loops when the LLM guesses the wrong file.
"""

import json
import os
import re

from core.llm import LLMClient
from core.session import Session
from agent.prompts import PLANNER

# Keywords that strongly indicate which file type owns the issue
CSS_KEYWORDS = re.compile(
    r'\b(border|background|color|font[-\s]?size|font[-\s]?weight|margin|padding|'
    r'hover|transition|box[-\s]?shadow|border[-\s]?radius|display|flex|grid|'
    r'text[-\s]?align|cursor|opacity|gradient|animation|transform|z[-\s]?index|'
    r'overflow|visibility|decoration|letter[-\s]?spacing|line[-\s]?height|'
    r'white[-\s]?space|text[-\s]?shadow|outline|placeholder|scrollbar|'
    r'responsive|breakpoint|stylesheet|style|css|layout|positioning|centered|'
    r'top\s*:\s*\d|bottom\s*:\s*\d|left\s*:\s*\d|right\s*:\s*\d|semicircle|'
    r'border-radius|width|height|size|spacing|visual\s*style|appearance)\b',
    re.IGNORECASE
)

HTML_KEYWORDS = re.compile(
    r'\b(element|div|button|title|heading|heading.*?tag|tag|missing.*?element|'
    r'structure|semantic|attribute|input|form|link.*?href|img|image.*?src|'
    r'meta.*?tag|script.*?src|canvas|section|article|nav|header|footer|'
    r'accessibility|aria|alt.*?text|placeholder.*?text)\b',
    re.IGNORECASE
)

JS_KEYWORDS = re.compile(
    r'\b(function|handler|event|click|state|variable|algorithm|calculation|'
    r'async|setTimeout|Promise|logic|handler|listener|callback|render.*?loop|'
    r'game.*?loop|update|frame|timing|repaint|re-render|localStorage|'
    r'fetch|API|request|response|parse|JSON|TypeError|ReferenceError)\b',
    re.IGNORECASE
)


def _guess_file_for_issue(issue_text: str, file_list: list[str]) -> str | None:
    """
    Given an issue description, guess which file it belongs to.
    Returns the best matching filename from file_list, or None.
    """
    css_score = len(CSS_KEYWORDS.findall(issue_text))
    html_score = len(HTML_KEYWORDS.findall(issue_text))
    js_score = len(JS_KEYWORDS.findall(issue_text))

    # Determine target type
    if css_score >= html_score and css_score >= js_score and css_score > 0:
        target_type = 'css'
    elif html_score >= css_score and html_score >= js_score and html_score > 0:
        target_type = 'html'
    elif js_score > 0:
        target_type = 'js'
    else:
        return None  # No strong signal

    # Find matching file in the allowed list
    for fname in file_list:
        if target_type == 'css' and fname.endswith('.css'):
            return fname
        if target_type == 'html' and fname.endswith('.html'):
            return fname
        if target_type == 'js' and fname.endswith('.js'):
            return fname

    return None


class Planner:
    def __init__(self, client: LLMClient, config: dict):
        self.client = client
        self.config = config

    def plan(self, critic_output: str, session: Session) -> list[dict]:
        """
        Ask the LLM to produce a fix plan from the Critic's output.
        Returns a list of {"action": ..., "filename": ..., "reason": ...} dicts.
        Only actions referencing allowed files are returned.

        Phase 1.7 fix: Each issue is annotated with a guessed target file
        based on keyword analysis (CSS border → styles.css, etc.)
        so the LLM cannot map issues to the wrong file.
        """
        allowed_paths = [
            os.path.join(os.path.abspath(session.output_dir), f)
            for f in session.file_list
        ]

        # Pre-annotate issues with guessed target files
        file_hints = ""
        issue_lines = critic_output.strip().split('\n')
        for i, line in enumerate(issue_lines, 1):
            if line.strip() and not line.strip().startswith('#'):
                guessed = _guess_file_for_issue(line, session.file_list)
                hint = f" → **{guessed}**" if guessed else ""
                file_hints += f"  Issue {i}: {line.strip()}{hint}\n"

        # If no file hints could be guessed, fall back to plain text
        context_text = (
            f"Allowed files:\n{json.dumps(allowed_paths, indent=2)}\n\n"
            f"Problems to fix (with suggested target files):\n{file_hints}\n\n"
            f"Full context:\n{critic_output}\n\n"
            "Produce the fix plan JSON now. "
            "IMPORTANT: Use the suggested target files above — do NOT guess a different file."
        )

        messages = [
            {"role": "system", "content": PLANNER},
            {"role": "user", "content": context_text},
        ]

        raw = self.client.call(messages, label="PLANNER", max_tokens=600)

        # Strip markdown fences if present
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()

        try:
            plan = json.loads(clean)
        except Exception:
            print("  ⚠️  Could not parse planner output as JSON, skipping cycle.")
            return []

        if not isinstance(plan, list):
            return []

        # Filter and validate: override wrong file choices
        valid = []
        for step in plan:
            fname = os.path.basename(step.get("filename", ""))
            reason = step.get("reason", "")

            if fname not in session.file_list:
                print(f"  ⚠️  Planner referenced unknown file: {fname}, skipped.")
                continue

            # Post-process validation: check if file choice matches issue keywords
            guessed = _guess_file_for_issue(reason, session.file_list)
            if guessed and guessed != fname:
                # The issue keywords point to a different file — override
                print(f"  🔀 Planner chose {fname}, but issue keywords point to {guessed} — overriding.")
                fname = guessed
                step["filename"] = os.path.join(
                    os.path.abspath(session.output_dir), fname
                )

            valid.append(step)

        print(f"  📝 Plan: {len(valid)} file(s) to fix")
        return valid
