"""
Planner agent — converts Critic output into a minimal fix plan.

The plan is a JSON array of at most 3 actions, each referencing one file.
Multiple problems in the same file are merged into a single action.
"""

import json
import os
import re

from core.llm import LLMClient
from core.session import Session
from agent.prompts import PLANNER


class Planner:
    def __init__(self, client: LLMClient, config: dict):
        self.client = client
        self.config = config

    def plan(self, critic_output: str, session: Session) -> list[dict]:
        """
        Ask the LLM to produce a fix plan from the Critic's output.
        Returns a list of {"action": ..., "filename": ..., "reason": ...} dicts.
        Only actions referencing allowed files are returned.
        """
        allowed_paths = [
            os.path.join(os.path.abspath(session.output_dir), f)
            for f in session.file_list
        ]

        messages = [
            {"role": "system", "content": PLANNER},
            {
                "role": "user",
                "content": (
                    f"Allowed files:\n{json.dumps(allowed_paths, indent=2)}\n\n"
                    f"Problems reported by the Critic:\n{critic_output}\n\n"
                    "Produce the fix plan JSON now."
                ),
            },
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

        # Filter out any actions referencing files not in the allowed list
        valid = []
        for step in plan:
            fname = os.path.basename(step.get("filename", ""))
            if fname in session.file_list:
                valid.append(step)
            else:
                print(f"  ⚠️  Planner referenced unknown file: {fname}, skipped.")

        print(f"  📝 Plan: {len(valid)} file(s) to fix")
        return valid
