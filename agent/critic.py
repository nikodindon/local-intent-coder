"""
Critic agent — reviews the full project and lists only blocking issues.

v2 (2026-04-11): Added static cross-file coherence analysis before LLM review.
Checks for DOM/Canvas mismatches, missing selectors, broken script includes, etc.
"""

import os
import re
from core.llm import LLMClient
from core.session import Session
from agent.prompts import CRITIC


def _static_analysis(session: Session) -> list[str]:
    """
    Run static analysis checks across all files to find coherence issues
    that the LLM might miss. Returns a list of blocking issues found.
    """
    issues = []

    # Read all file contents
    contents = {}
    for fname in session.file_list:
        path = os.path.join(session.output_dir, fname)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                contents[fname] = f.read()

    html_content = contents.get("index.html", "")
    css_content = contents.get("styles.css", "")
    js_files = {k: v for k, v in contents.items() if k.endswith(".js")}
    js_content = "\n".join(js_files.values())

    if not html_content or not js_content:
        return issues  # Can't cross-check without both files

    # ─── CHECK 1: Canvas vs DOM mismatch ───
    has_canvas_call = re.search(r"getContext\s*\(\s*['\"]2d['\"]\s*\)", js_content)
    has_canvas_element = bool(re.search(r"<canvas\b", html_content))
    has_game_container_div = bool(re.search(r"<div\s+[^>]*id=['\"]game-container['\"]", html_content))

    if has_canvas_call and not has_canvas_element:
        if has_game_container_div:
            issues.append(
                f"BREAKING: game.js uses getContext('2d') (Canvas API) but index.html "
                f"has <div id='game-container'> instead of <canvas id='game-container'>. "
                f"This will crash: div.getContext('2d') returns null. "
                f"Either add a <canvas> element in HTML or switch to DOM-based rendering."
            )
        else:
            issues.append(
                f"BREAKING: game.js uses getContext('2d') but no <canvas> element exists in HTML. "
                f"The game will not render. Add a <canvas> element or switch to DOM rendering."
            )

    # ─── CHECK 2: Missing DOM elements referenced in JS ───
    js_element_refs = re.findall(
        r"getElementById\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", js_content
    )
    for elem_id in js_element_refs:
        # Skip IDs that might be created dynamically via createElement
        if elem_id in ("game-container",):
            continue
        if not re.search(rf"""id=['"]{re.escape(elem_id)}['"]""", html_content):
            # Check if it's created via createElement
            if f"createElement" in js_content and elem_id in js_content:
                continue
            issues.append(
                f"BREAKING: game.js calls getElementById('{elem_id}') but no element "
                f"with id='{elem_id}' exists in index.html. The element will be null."
            )

    # ─── CHECK 3: Missing CSS classes referenced in JS ───
    js_class_refs = re.findall(
        r"querySelectorAll?\s*\(\s*['\"]\.([^'\"]+)['\"]", js_content
    )
    for cls in js_class_refs:
        if not re.search(rf"""\.{re.escape(cls)}\b""", css_content):
            # Check if it's in HTML as class
            if not re.search(rf"""class=['\"][^'\"]*\b{re.escape(cls)}\b""", html_content):
                issues.append(
                    f"WARNING: game.js references .{cls} but no CSS rule or HTML element "
                    f"uses this class. Element won't be styled or found."
                )

    # ─── CHECK 4: Script src files that don't exist ───
    script_srcs = re.findall(r"""src=['"]([^'"]+\.js)['"]""", html_content)
    for src in script_srcs:
        src_basename = os.path.basename(src)
        if src_basename not in js_files:
            issues.append(
                f"BREAKING: index.html includes <script src='{src}'> but "
                f"{src_basename} does not exist in the output directory."
            )

    # ─── CHECK 5: Event listeners present? ───
    has_event_listener = bool(re.search(r"addEventListener\s*\(", js_content))
    has_keyboard_control = bool(re.search(r"(keydown|keyup|keypress|ArrowUp|ArrowDown|ArrowLeft|ArrowRight)", js_content))
    has_mouse_control = bool(re.search(r"(mousemove|click|mousedown|clientX|clientY|pageX|pageY)", js_content))
    has_any_control = has_keyboard_control or has_mouse_control

    if not has_event_listener and not has_any_control:
        issues.append(
            f"BREAKING: No input event listeners found in any JS file. "
            f"The game/app has no user interaction — it's a static animation at best."
        )

    # ─── CHECK 5b: Control type mismatch (spec says mouse, JS uses keyboard or vice versa) ───
    if session.spec_md:
        spec_lower = session.spec_md.lower()
        if "mouse" in spec_lower and "horizontal" in spec_lower:
            if has_keyboard_control and not has_mouse_control:
                issues.append(
                    f"BREAKING: Spec requires mouse horizontal movement but JS only has keyboard "
                    f"controls (Arrow keys). User won't be able to play with the mouse as specified."
                )
        if "mouse" in spec_lower and not has_mouse_control and not has_keyboard_control:
            issues.append(
                f"BREAKING: Spec requires mouse controls but no mouse event listeners "
                f"(mousemove, click, clientX) found in any JS file."
            )

    # ─── CHECK 6: Game loop present? ───
    has_game_loop = bool(re.search(r"(requestAnimationFrame|setInterval|setTimeout.*loop)", js_content))
    if not has_game_loop and has_canvas_call:
        issues.append(
            f"BREAKING: Canvas rendering without a game loop (no requestAnimationFrame). "
            f"Nothing will animate."
        )

    # ─── CHECK 6b: Gravity missing when spec requires it ───
    if session.spec_md and "gravity" in session.spec_md.lower():
        has_gravity = bool(re.search(r"\bgravit", js_content, re.IGNORECASE))
        has_acceleration = bool(re.search(r"(vy|speedY|dy|accelY)\s*\+=", js_content))
        if not has_gravity and not has_acceleration:
            issues.append(
                f"BREAKING: Spec requires gravity physics but no gravity implementation found "
                f"in JS. Ball/objects won't fall or arc naturally."
            )

    # ─── CHECK 7: AudioContext initialized correctly? ───
    if "AudioContext" in js_content or "webkitAudioContext" in js_content:
        # Check if audio is created on user interaction (browsers block auto-play)
        has_user_init_audio = bool(re.search(
            r"(addEventListener|onclick|onstart|onInit|onUserGesture).*AudioContext",
            js_content, re.DOTALL
        ))
        # Or check if it's created at top level (will fail in Chrome)
        has_top_level_audio = bool(re.search(
            r"^(const|let|var)\s+\w*[Aa]udio.*=.*new\s+AudioContext",
            js_content, re.MULTILINE
        ))
        if has_top_level_audio and not has_user_init_audio:
            issues.append(
                f"WARNING: AudioContext is created at top-level scope. Modern browsers block "
                f"auto-playing audio without user interaction. Wrap AudioContext creation "
                f"in a click/key event handler."
            )

    # ─── CHECK 8: CPU/AI opponent has no logic? ───
    if session.spec_md:
        has_ai = bool(re.search(r"\b(cpu|ai|opponent|computer|bot|player 2)\b", session.spec_md.lower()))
        if has_ai:
            # Check for actual AI movement logic (not just position reads for collision)
            # Look for: player2.y = ... (assignment in a function/update loop)
            has_ai_assignment = bool(re.search(
                r"(player2|cpu|opponent|ai)\s*\.\s*(y|x)\s*[+]=\s*-?\d+",
                js_content, re.IGNORECASE
            ))
            if not has_ai_assignment:
                # Also check for update functions that move the opponent
                has_ai_update_fn = bool(re.search(
                    r"function\s+(cpu|opponent|ai|player2|computer)[A-Za-z]*.*\{.*\.(y|x)\s*=",
                    js_content, re.IGNORECASE | re.DOTALL
                ))
                if not has_ai_update_fn:
                    # Check if player2 position changes at all (not just collision read)
                    has_ai_tracking = bool(re.search(
                        r"(player2|cpu|opponent|ai)\s*\.\s*(y|x)\s*=\s*(ball|target|mouse|event)",
                        js_content, re.IGNORECASE
                    ))
                    if not has_ai_tracking:
                        issues.append(
                            f"BREAKING: Spec requires AI/CPU opponent but no AI movement logic found. "
                            f"Player 2/opponent position is never updated — it will be static."
                        )

    return issues


class Critic:
    def __init__(self, client: LLMClient, config: dict):
        self.client = client
        self.config = config

    def review(self, session: Session) -> str:
        """Review the project and return blocking issues only."""
        features = "\n".join(f"- {f}" for f in session.file_list)

        # Check for missing files
        missing = [f for f in session.file_list
                  if not os.path.exists(os.path.join(session.output_dir, f))]

        if missing:
            missing_str = "\n".join(f"  - {f}" for f in missing)
            extra = f"\n\nCRITICAL: The following files are missing on disk:\n{missing_str}"
        else:
            extra = "\n\nAll files listed in the spec exist on disk."

        # Extract features from spec if available
        spec_features = ""
        if session.spec_md:
            feature_section = re.search(r'## Features\n(.*?)(?=##|$)', session.spec_md, re.DOTALL)
            if feature_section:
                spec_features = f"\n\nREQUIRED FEATURES FROM SPEC:\n{feature_section.group(1).strip()}"

        # ─── v2: Run static cross-file coherence analysis ───
        static_issues = _static_analysis(session)
        static_context = ""
        if static_issues:
            static_context = "\n\nSTATIC ANALYSIS FINDINGS (DO NOT IGNORE — these are blocking bugs):\n"
            for i, issue in enumerate(static_issues, 1):
                static_context += f"{i}. {issue}\n"
            print(f"  🔍 Static analysis found {len(static_issues)} issue(s)")
            for issue in static_issues:
                print(f"    ⛔ {issue[:120]}...")

        snapshot = session.snapshot()

        # Add critic history to avoid repetition
        history_context = ""
        if session.critic_history:
            history_context = "\n\nPrevious review cycles already covered these issues (do NOT repeat):\n"
            for i, past_review in enumerate(session.critic_history[-2:], 1):  # Only show last 2
                if past_review.strip() and "ALL_COMPLETE" not in past_review.upper():
                    history_context += f"\nCycle {i}:\n{past_review[:300]}"

        user_prompt = (
            f"Project intent: {session.prompt}\n\n"
            f"Required files according to spec:\n{features}\n"
            f"Files present on disk: {', '.join(session.file_list)}\n"
            f"{extra}\n"
            f"{spec_features}\n"
            f"{static_context}"
            f"{history_context}\n"
            f"Here is the current state of the project:\n{snapshot}\n\n"
            "You are a strict code reviewer.\n"
            "Analyze if the project fulfills the original user intent and is functional.\n"
            "List ONLY the blocking issues that prevent the project from working as intended.\n"
            "Be concrete and specific (mention file + problem).\n"
            "If the project is reasonably complete and works according to the intent, reply with exactly:\n"
            "ALL_COMPLETE"
        )

        messages = [
            {"role": "system", "content": CRITIC},
            {"role": "user", "content": user_prompt},
        ]

        output = self.client.call(messages, label="CRITIC", max_tokens=900)
        session.critic_history.append(output.strip())
        return output.strip()

    @staticmethod
    def is_complete(critic_output: str) -> bool:
        """Check if Critic output indicates completion."""
        # Look for explicit VERDICT: ALL_COMPLETE or standalone ALL_COMPLETE
        if "VERDICT: ALL_COMPLETE" in critic_output.upper():
            return True
        if critic_output.strip().upper() == "ALL_COMPLETE":
            return True
        return False

    @staticmethod
    def is_repetitive(session: Session, threshold: int = 2) -> bool:
        """Detect if the critic is stuck in a loop."""
        if len(session.critic_history) < threshold + 1:
            return False
        
        # Check if last N reviews are identical
        recent = session.critic_history[-(threshold + 1):]
        return len(set(recent)) == 1 and recent[0].strip() != ""