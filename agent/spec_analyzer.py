"""
Spec Analyzer — extracts artifact metadata from a spec.md file.

v2 (2026-04-11): Replaces hardcoded game-type detection with spec-derived
metadata. All agents can query this to adapt their behavior without needing
hardcoded assumptions about what kind of artifact is being built.

Usage:
    from agent.spec_analyzer import SpecAnalyzer
    analyzer = SpecAnalyzer(spec_md)
    print(analyzer.artifact_type)     # 'side_by_side_game'
    print(analyzer.controls)          # ['mouse_horizontal']
    print(analyzer.has_win_condition) # True
"""

import re
from dataclasses import dataclass, field


@dataclass
class SpecMetadata:
    """Structured metadata extracted from a project spec."""

    # High-level artifact type
    artifact_type: str = "unknown"  # e.g., 'side_by_side_game', 'top_down_game', 'board_game', 'web_app', 'dashboard'

    # Input methods mentioned
    controls: list[str] = field(default_factory=list)  # e.g., ['mouse_horizontal', 'keyboard_arrows', 'click']

    # Game state
    has_win_condition: bool = False
    has_score_tracking: bool = False
    has_ai_opponent: bool = False
    has_multiplayer: bool = False
    has_audio: bool = False

    # Visual elements expected
    expected_elements: list[str] = field(default_factory=list)

    # Win condition details
    win_condition: str = ""  # e.g., 'first_to_7', 'survival', 'time_limit'

    # File structure
    file_list: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary for debugging/logging."""
        lines = [
            f"Type: {self.artifact_type}",
            f"Controls: {', '.join(self.controls) if self.controls else 'not specified'}",
            f"Win condition: {self.win_condition if self.win_condition else 'none'}",
            f"Score tracking: {'yes' if self.has_score_tracking else 'no'}",
            f"AI opponent: {'yes' if self.has_ai_opponent else 'no'}",
            f"Audio: {'yes' if self.has_audio else 'no'}",
            f"Expected elements: {', '.join(self.expected_elements) if self.expected_elements else 'none'}",
        ]
        return "\n  ".join(lines)


class SpecAnalyzer:
    """
    Extract structured metadata from a project spec Markdown string.

    This is the central source of truth for artifact type detection.
    All agents should use this instead of hardcoded assumptions.
    """

    def __init__(self, spec_md: str):
        self._spec = spec_md
        self._features_text = self._extract_section("Features")
        self._constraints_text = self._extract_section("Constraints")
        self._visual_text = self._extract_section("Visual Guidelines")
        self._metadata = self._analyze()

    @property
    def metadata(self) -> SpecMetadata:
        return self._metadata

    @property
    def artifact_type(self) -> str:
        return self._metadata.artifact_type

    @property
    def controls(self) -> list[str]:
        return self._metadata.controls

    @property
    def has_win_condition(self) -> bool:
        return self._metadata.has_win_condition

    @property
    def expected_elements(self) -> list[str]:
        return self._metadata.expected_elements

    def _extract_section(self, section_name: str) -> str:
        """Extract text under a ## Section heading."""
        match = re.search(
            rf"## {section_name}\n(.*?)(?=##|$)", self._spec, re.DOTALL
        )
        return match.group(1).strip() if match else ""

    def _analyze(self) -> SpecMetadata:
        """Run all analyzers and return structured metadata."""
        meta = SpecMetadata()

        # Combine all text for broad analysis
        all_text = (
            self._features_text + " " + self._constraints_text + " " + self._visual_text
        ).lower()

        # ─── Artifact type detection ───
        meta.artifact_type = self._detect_type(all_text)

        # ─── Controls detection ───
        meta.controls = self._detect_controls(all_text)

        # ─── Game state detection ───
        meta.has_win_condition = self._detect_win_condition(all_text)
        meta.has_score_tracking = any(
            kw in all_text for kw in ["score", "point", "tracking", "first to"]
        )
        meta.has_ai_opponent = any(
            kw in all_text for kw in ["cpu", "ai ", "computer", "bot", "opponent"]
        )
        meta.has_multiplayer = any(
            kw in all_text
            for kw in ["two player", "multiplayer", "pvp", "vs player"]
        )
        meta.has_audio = any(
            kw in all_text
            for kw in ["audio", "sound", "beep", "audiocontext", "oscillator"]
        )

        # ─── Win condition details ───
        meta.win_condition = self._detect_win_details(all_text)

        # ─── Expected elements ───
        meta.expected_elements = self._detect_elements(all_text)

        # ─── File list ───
        meta.file_list = self._detect_files()

        return meta

    def _detect_type(self, text: str) -> str:
        """Detect the high-level artifact type from spec text."""
        # Side-by-side games (Blobby Volley, Pong doubles)
        if any(
            kw in text
            for kw in [
                "side-by-side",
                "side by side",
                "left side",
                "right side",
                "player 1 on the left",
                "player 2 on the right",
                "volley",
            ]
        ):
            return "side_by_side_game"

        # Top-down / falling block games (Tetris)
        if any(
            kw in text
            for kw in ["falling", "tetris", "top-down", "top down", "grid game"]
        ):
            return "falling_block_game"

        # Board games (Tic-Tac-Toe, Connect 4, Checkers)
        if any(
            kw in text
            for kw in [
                "board game",
                "tic-tac-toe",
                "morpion",
                "connect 4",
                "checkers",
                "grid",
            ]
        ):
            return "board_game"

        # Snake / grid movement games
        if any(kw in text for kw in ["snake", "maze", "grid movement"]):
            return "grid_game"

        # Web apps (to-do, counter, dashboard)
        if any(
            kw in text
            for kw in [
                "task",
                "todo",
                "to-do",
                "counter",
                "increment",
                "dashboard",
                "form",
                "input",
            ]
        ):
            return "web_app"

        return "unknown"

    def _detect_controls(self, text: str) -> list[str]:
        """Detect input methods from spec text."""
        controls = []

        if "mouse" in text:
            if "horizontal" in text:
                controls.append("mouse_horizontal")
            elif "vertical" in text:
                controls.append("mouse_vertical")
            else:
                controls.append("mouse")

        if any(kw in text for kw in ["keyboard", "arrow key", "key press", "keydown"]):
            controls.append("keyboard")

        if any(kw in text for kw in ["click", "tap", "touch"]):
            controls.append("click")

        if any(kw in text for kw in ["drag", "swipe"]):
            controls.append("drag")

        return controls

    def _detect_win_condition(self, text: str) -> bool:
        """Detect if the artifact has a win/lose condition."""
        return any(
            kw in text
            for kw in [
                "win",
                "lose",
                "victory",
                "defeat",
                "game over",
                "first to",
                "reaches",
                "winner",
            ]
        )

    def _detect_win_details(self, text: str) -> str:
        """Extract details about the win condition."""
        if "first to 7" in text or "first to seven" in text:
            return "first_to_7"
        if "first to" in text:
            match = re.search(r"first to (\d+)", text)
            if match:
                return f"first_to_{match.group(1)}"
        if "time" in text and ("limit" in text or "survive" in text):
            return "time_survival"
        if "high score" in text or "best score" in text:
            return "high_score"
        return ""

    def _detect_elements(self, text: str) -> list[str]:
        """Detect expected UI elements from spec text."""
        elements = []

        if any(kw in text for kw in ["score", "tracking", "points"]):
            elements.append("score display")

        if any(kw in text for kw in ["player", "opponent", "cpu", "ai"]):
            elements.append("player indicators")

        if any(kw in text for kw in ["net", "barrier", "divider"]):
            elements.append("net or barrier")

        if any(kw in text for kw in ["status", "turn", "state"]):
            elements.append("status indicator")

        if any(kw in text for kw in ["ball", "piece", "projectile"]):
            elements.append("game object")

        if any(kw in text for kw in ["button", "reset", "restart"]):
            elements.append("action button")

        if any(kw in text for kw in ["title", "heading"]):
            elements.append("page title")

        return elements

    def _detect_files(self) -> list[str]:
        """Extract file list from spec."""
        files = []
        files_match = re.search(r"## Files\n(.*?)(?=##|$)", self._spec, re.DOTALL)
        if files_match:
            for line in files_match.group(1).strip().split("\n"):
                # Match `- filename.ext — role`
                file_match = re.match(r"[-*]\s+`([^`]+)`", line.strip())
                if file_match:
                    files.append(file_match.group(1))
        return files
