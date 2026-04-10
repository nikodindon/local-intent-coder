"""
Architect agent — converts a natural language prompt into a structured spec.
"""

import os
import re

from core.llm import LLMClient
from agent.prompts import ARCHITECT


class Architect:
    def __init__(self, client: LLMClient, config: dict):
        self.client = client
        self.config = config

    def build_spec(self, prompt: str, output_dir: str) -> str:
        abs_output = os.path.abspath(output_dir)

        user_msg = (
            f"User intent: {prompt}\n\n"
            f"Target directory: {abs_output}\n\n"
            "Produce the project spec now."
        )

        messages = [
            {"role": "system", "content": ARCHITECT},
            {"role": "user", "content": user_msg},
        ]

        spec_md = self.client.call(messages, label="ARCHITECT", max_tokens=1500)
        return spec_md

    @staticmethod
    def parse_spec(spec_md: str) -> dict:
        """Parse spec with multiple robust strategies."""
        result = {
            "file_list": [],
            "file_roles": {},
            "features": [],
        }

        # Strategy 1: Standard with common dashes
        patterns = [
            r"-\s*`([^`]+\.[a-zA-Z0-9]+)`\s*[—–-—\s]+(.+?)(?:\n|$)",
            r"-\s*`([^`]+\.[a-zA-Z0-9]+)`",
            r"`([^`]+\.[a-zA-Z0-9]+)`\s*[—–-—\s]+(.+?)(?:\n|$)",
        ]

        for pattern in patterns:
            for m in re.finditer(pattern, spec_md, re.MULTILINE | re.IGNORECASE):
                fname = m.group(1).strip()
                if fname and fname not in result["file_list"]:
                    result["file_list"].append(fname)
                    role = m.group(2).strip() if len(m.groups()) > 1 else "File from spec"
                    result["file_roles"][fname] = role

        # Strategy 2: Very aggressive fallback - any .html, .css, .js in backticks
        if not result["file_list"]:
            for m in re.finditer(r"`([^`\r\n]+?\.(html|css|js))`", spec_md, re.IGNORECASE):
                fname = m.group(1).strip()
                if fname and fname not in result["file_list"]:
                    result["file_list"].append(fname)
                    result["file_roles"][fname] = "Generated file"

        # Extract features
        for m in re.finditer(r"^\s*\d+\.\s+(.+?)(?:\n|$)", spec_md, re.MULTILINE):
            result["features"].append(m.group(1).strip())

        return result